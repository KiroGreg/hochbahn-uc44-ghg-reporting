"""Write-through persistence: mirror the live flow into the DB.

The in-memory `SessionState` still drives the active run's computation; these
helpers persist each stage's output so runs, model results and the historised
manual decisions survive a container restart and become queryable.

Every function opens its own short-lived `Session` and commits, so the API
endpoints stay decoupled from the ORM session lifecycle. Failures here must
never break the live flow — callers wrap these in best-effort try/except.
"""
from __future__ import annotations

import math
import uuid
from typing import Optional

import pandas as pd

from ..core.data import amount_series
from ..core.db import SessionLocal
from ..models.orm import (
    DecisionEvent,
    PlausibilityResult,
    PredictionResult,
    Run,
    Sample,
)
from ..schemas.models import PlausibilityRow, PredictionRow


def _json_safe(value):
    """Coerce a cell to something JSON-serialisable (NaN/NaT → None)."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value
    # numpy scalars, Timestamps, etc.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def _str_or_none(value) -> Optional[str]:
    s = _json_safe(value)
    if s is None:
        return None
    s = str(s).strip()
    return s or None


def create_run(
    invoices: pd.DataFrame,
    filename: str,
    source: str,
) -> uuid.UUID:
    """Persist a new Run plus one Sample per invoice row. Returns the run id.

    `row_index` is the positional Pandas index — the same key every backend
    stage uses to align results back onto rows.
    """
    amounts = amount_series(invoices)
    run_id = uuid.uuid4()
    with SessionLocal() as session:
        run = Run(
            id=run_id,
            filename=filename,
            source=source,
            row_count=int(len(invoices)),
            column_count=int(invoices.shape[1]),
            status="uploaded",
        )
        session.add(run)

        samples: list[Sample] = []
        for pos, (idx, row) in enumerate(invoices.iterrows()):
            amt = amounts.get(idx)
            samples.append(
                Sample(
                    run_id=run_id,
                    row_index=int(idx) if isinstance(idx, (int,)) else pos,
                    bestelltext=_str_or_none(row.get("Bestelltext")),
                    wg_id_original=_str_or_none(row.get("Warengruppe")),
                    betrag_eur=None if amt is None or pd.isna(amt) else round(float(amt), 2),
                    raw={str(k): _json_safe(v) for k, v in row.items()},
                )
            )
        session.add_all(samples)
        session.commit()
    return run_id


def _sample_id_by_row(session, run_id: uuid.UUID) -> dict[int, uuid.UUID]:
    rows = (
        session.query(Sample.row_index, Sample.id)
        .filter(Sample.run_id == run_id)
        .all()
    )
    return {int(r): sid for r, sid in rows}


def save_plausibility(run_id: uuid.UUID, rows: list[PlausibilityRow]) -> None:
    """Insert one PlausibilityResult per processed row; backfill sample inputs."""
    if run_id is None:
        return
    with SessionLocal() as session:
        by_row = _sample_id_by_row(session, run_id)
        for r in rows:
            sid = by_row.get(int(r.row_index))
            if sid is None:
                continue
            # Backfill catalog-derived sample fields now that we have them.
            sample = session.get(Sample, sid)
            if sample is not None:
                if r.objektbezeichnung:
                    sample.objektbezeichnung = r.objektbezeichnung
                if r.kostenart:
                    sample.kostenart = r.kostenart
                if r.wg_name and not sample.wg_name_original:
                    sample.wg_name_original = r.wg_name
            session.add(
                PlausibilityResult(
                    sample_id=sid,
                    plausibilitaet=r.plausibilitaet,
                    confidence=r.confidence,
                    reason=r.reason,
                    signale_pro=list(r.unterstuetzende_signale or []),
                    signale_contra=list(r.widersprechende_signale or []),
                    objektbez_fallback=bool(
                        (not r.bestelltext or r.bestelltext.startswith("[kein"))
                        and r.objektbezeichnung
                    ),
                )
            )
        # Note: run.status is owned by the orchestrator (running→done); the
        # per-chunk writes must not touch it.
        session.commit()


def save_predictions(run_id: uuid.UUID, rows: list[PredictionRow]) -> None:
    """Insert one PredictionResult per predicted row."""
    if run_id is None:
        return
    with SessionLocal() as session:
        by_row = _sample_id_by_row(session, run_id)
        for r in rows:
            sid = by_row.get(int(r.row_index))
            if sid is None:
                continue
            session.add(
                PredictionResult(
                    sample_id=sid,
                    suggested_wg_name=r.suggested_wg_name,
                    confidence=r.confidence,
                    reason=r.reason,
                    objektbez_signal=bool(r.objektbez_signal),
                    ef_missing=bool(r.ef_missing),
                    source=getattr(r, "source", None),
                )
            )
        # run.status is owned by the orchestrator; do not overwrite it here.
        session.commit()


def save_decision(
    run_id: uuid.UUID,
    row_index: int,
    decision: str,
    new_wg_name: Optional[str] = None,
    old_value: Optional[str] = None,
    stage: str = "regrouping",
) -> None:
    """Append a historised decision/remapping event for one sample."""
    if run_id is None:
        return
    user_action = {
        "ok": "accept",
        "reject": "reject",
        "regroup": "manual_wg_change",
        "new_wg": "manual_wg_change",
    }.get(decision, decision)
    field_changed = "wg_name" if decision in {"regroup", "new_wg"} else "decision"
    with SessionLocal() as session:
        by_row = _sample_id_by_row(session, run_id)
        sid = by_row.get(int(row_index))
        if sid is None:
            return
        session.add(
            DecisionEvent(
                sample_id=sid,
                stage=stage,
                user_action=user_action,
                decision=decision,
                field_changed=field_changed,
                old_value=old_value,
                new_value=new_wg_name,
            )
        )
        session.commit()


def update_run_usage(
    run_id: uuid.UUID, model_name: Optional[str], cost_usd: float, api_calls: int
) -> None:
    if run_id is None:
        return
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        if model_name:
            run.model_name = model_name
        run.cost_usd = round(float(cost_usd), 4)
        run.api_calls = int(api_calls)
        session.commit()


_UNSET = object()


def update_run_progress(
    run_id: uuid.UUID,
    *,
    status=_UNSET,
    stage=_UNSET,
    error=_UNSET,
    plaus_total=_UNSET,
    pred_total=_UNSET,
    started_at=_UNSET,
    finished_at=_UNSET,
) -> None:
    """Patch the run's lifecycle fields. Only passed kwargs are written."""
    if run_id is None:
        return
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        if status is not _UNSET:
            run.status = status
        if stage is not _UNSET:
            run.stage = stage
        if error is not _UNSET:
            run.error = error
        if plaus_total is not _UNSET:
            run.plaus_total = plaus_total
        if pred_total is not _UNSET:
            run.pred_total = pred_total
        if started_at is not _UNSET:
            run.started_at = started_at
        if finished_at is not _UNSET:
            run.finished_at = finished_at
        session.commit()
