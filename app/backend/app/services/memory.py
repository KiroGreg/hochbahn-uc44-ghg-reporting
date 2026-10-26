"""Correction-memory extraction (Step A — deterministic, no LLM/embeddings).

Materialises the 'current truth' per sample into `correction_memory`:
the model's prediction + the human correction (if any) + the resulting
`outcome`. Source: `prediction_result.suggested_wg_name` (model) + the newest
`decision_event` (human). The `feature_key` is built from `sample.raw` via the
canonical, model-mirroring builder.

Truth discipline (critical): only confirmed cases become positive examples
downstream — `reassigned` (truth = corrected_wg) and `accepted`
(truth = predicted_wg). `rejected` is a negative signal; `unreviewed` is unknown.
"""
from __future__ import annotations

import uuid
from typing import Optional

from ..core.db import SessionLocal
from ..core.features import feature_key_from_raw
from ..models.orm import (
    CorrectionMemory,
    DecisionEvent,
    PredictionResult,
    Sample,
)

# Outcomes that carry a usable signal for retrieval (positive or negative).
CONFIRMED_OUTCOMES = ("reassigned", "accepted", "rejected")


def _derive(ev: Optional[DecisionEvent]) -> tuple[str, Optional[str]]:
    """(outcome, corrected_wg) from the newest decision event for a sample."""
    if ev is None:
        return ("unreviewed", None)
    d = ev.decision
    if d in ("new_wg", "regroup"):
        return ("reassigned", ev.new_value)
    if d == "ok":
        return ("accepted", None)
    if d == "reject":
        return ("rejected", None)
    return ("unreviewed", None)


def _upsert(session, sample: Sample, run_id, predicted_wg, outcome, corrected_wg) -> None:
    row = (
        session.query(CorrectionMemory)
        .filter(CorrectionMemory.sample_id == sample.id)
        .one_or_none()
    )
    fkey = feature_key_from_raw(sample.raw)
    if row is None:
        session.add(
            CorrectionMemory(
                sample_id=sample.id,
                run_id=run_id,
                feature_key=fkey,
                predicted_wg=predicted_wg,
                corrected_wg=corrected_wg,
                outcome=outcome,
            )
        )
    else:
        row.run_id = run_id
        row.feature_key = fkey
        row.predicted_wg = predicted_wg
        row.corrected_wg = corrected_wg
        row.outcome = outcome


def _coerce_uuid(value):
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def refresh_run(run_id) -> int:
    """Rebuild correction_memory for every predicted sample in a run.

    Returns the number of rows written. Only samples that have a prediction are
    included (the memory is about predictions).
    """
    run_uuid = _coerce_uuid(run_id)
    if run_uuid is None:
        return 0
    with SessionLocal() as s:
        samples = {
            sm.id: sm
            for sm in s.query(Sample).filter(Sample.run_id == run_uuid).all()
        }
        if not samples:
            return 0
        latest_pred = {}
        for p in (
            s.query(PredictionResult)
            .join(Sample, Sample.id == PredictionResult.sample_id)
            .filter(Sample.run_id == run_uuid)
            .order_by(PredictionResult.created_at)
            .all()
        ):
            latest_pred[p.sample_id] = p  # last wins
        latest_dec = {}
        for d in (
            s.query(DecisionEvent)
            .join(Sample, Sample.id == DecisionEvent.sample_id)
            .filter(Sample.run_id == run_uuid)
            .order_by(DecisionEvent.created_at)
            .all()
        ):
            latest_dec[d.sample_id] = d  # last wins

        n = 0
        for sid, pred in latest_pred.items():
            sample = samples.get(sid)
            if sample is None:
                continue
            outcome, corrected = _derive(latest_dec.get(sid))
            _upsert(s, sample, run_uuid, pred.suggested_wg_name, outcome, corrected)
            n += 1
        s.commit()
        return n


def upsert_sample(run_id, row_index: int) -> bool:
    """Refresh the memory row for a single sample (after a decision). Cheap."""
    run_uuid = _coerce_uuid(run_id)
    if run_uuid is None:
        return False
    with SessionLocal() as s:
        sample = (
            s.query(Sample)
            .filter(Sample.run_id == run_uuid, Sample.row_index == int(row_index))
            .one_or_none()
        )
        if sample is None:
            return False
        pred = (
            s.query(PredictionResult)
            .filter(PredictionResult.sample_id == sample.id)
            .order_by(PredictionResult.created_at.desc())
            .first()
        )
        if pred is None:
            return False  # no prediction yet — nothing to remember
        dec = (
            s.query(DecisionEvent)
            .filter(DecisionEvent.sample_id == sample.id)
            .order_by(DecisionEvent.created_at.desc())
            .first()
        )
        outcome, corrected = _derive(dec)
        _upsert(s, sample, run_uuid, pred.suggested_wg_name, outcome, corrected)
        s.commit()
        return True


# --- Embeddings & retrieval (Step B) -----------------------------------------

def embed_pending(limit: int = 1000) -> int:
    """Embed confirmed memory rows that still lack an embedding. Returns count.

    Only confirmed rows (reassigned/accepted/rejected) are embedded — those are
    the only ones retrieval ever uses, so we don't spend on unreviewed guesses.
    """
    from ..services import embeddings

    with SessionLocal() as s:
        rows = (
            s.query(CorrectionMemory)
            .filter(
                CorrectionMemory.embedding.is_(None),
                CorrectionMemory.outcome.in_(CONFIRMED_OUTCOMES),
            )
            .limit(limit)
            .all()
        )
        if not rows:
            return 0
        vecs = embeddings.embed_texts([r.feature_key for r in rows])
        for r, v in zip(rows, vecs):
            r.embedding = v
        s.commit()
        return len(rows)


def find_exact_truth(feature_key: str) -> Optional[str]:
    """Memoization: truth of a confirmed row whose feature_key is *identical*.

    Exact match (not cosine) — invoice texts are heavily templated, so cosine
    near-duplicates over-fire; identical feature_key means a literally repeated
    invoice line, which is safe to reuse. Returns the corrected/accepted class
    or None.
    """
    with SessionLocal() as s:
        rows = (
            s.query(CorrectionMemory)
            .filter(
                CorrectionMemory.feature_key == feature_key,
                CorrectionMemory.outcome.in_(("reassigned", "accepted")),
            )
            .order_by(CorrectionMemory.updated_at.desc())
            .all()
        )
    for m in rows:
        truth = m.corrected_wg if m.outcome == "reassigned" else m.predicted_wg
        if truth:
            return truth
    return None


def retrieve(
    query_text: str,
    top_n: int = 6,
    threshold: float = 0.82,
    predicted_wg: Optional[str] = None,
) -> list[dict]:
    """Cosine-nearest confirmed corrections for a query feature string.

    `threshold` is cosine *similarity* (1 - distance). `predicted_wg` optionally
    narrows to cases the model classified the same way (sharpens the
    "you're about to repeat a known mistake" signal).
    """
    from ..services import embeddings

    vec = embeddings.embed_text(query_text)
    with SessionLocal() as s:
        dist = CorrectionMemory.embedding.cosine_distance(vec).label("dist")
        q = (
            s.query(CorrectionMemory, dist)
            .filter(
                CorrectionMemory.embedding.isnot(None),
                CorrectionMemory.outcome.in_(CONFIRMED_OUTCOMES),
            )
        )
        if predicted_wg:
            q = q.filter(CorrectionMemory.predicted_wg == predicted_wg)
        rows = q.order_by(dist).limit(top_n).all()

    out: list[dict] = []
    for m, d in rows:
        sim = 1.0 - float(d)
        if sim < threshold:
            continue
        truth = m.corrected_wg if m.outcome == "reassigned" else (
            m.predicted_wg if m.outcome == "accepted" else None
        )
        out.append(
            {
                "similarity": round(sim, 4),
                "feature_key": m.feature_key,
                "predicted_wg": m.predicted_wg,
                "corrected_wg": m.corrected_wg,
                "outcome": m.outcome,
                "truth_wg": truth,
            }
        )
    return out
