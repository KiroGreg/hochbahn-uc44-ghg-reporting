"""Run history + resume.

`list_runs()` powers the history picker. `resume_run()` rebuilds a past run
entirely from the DB — the invoices DataFrame from `sample.raw`, the model
results from the result tables, the decisions/audit-log from `decision_event` —
rehydrates the in-memory `SessionState` so the existing dashboard/review
endpoints keep working unchanged, and returns the combined payload the frontend
needs to restore the UI. No LLM call is made.
"""
from __future__ import annotations

import uuid
from typing import Optional

import pandas as pd
from sqlalchemy import func

from ..core.data import attach_catalog_to_invoices
from ..core.db import SessionLocal
from ..core.state import get_state
from ..models.orm import (
    DecisionEvent,
    PlausibilityResult,
    PredictionResult,
    Run,
    Sample,
)
from ..schemas.models import (
    ChangeLogRecord,
    ComparisonItem,
    ComparisonResult,
    DecisionState,
    PlausibilityRow,
    PlausibilityRunResponse,
    PlausibilityStats,
    PredictionRow,
    PredictionRunResponse,
    PredictionStats,
    RunDetail,
    RunStatus,
    RunSummary,
    UploadSummary,
)

_VALID_CONF = {"hoch", "mittel", "niedrig", "unknown", "error", "not_assessable"}


def _conf(value) -> str:
    v = (str(value).strip() if value is not None else "") or "unknown"
    return v if v in _VALID_CONF else "unknown"


def _f(value) -> Optional[float]:
    return None if value is None else round(float(value), 2)


def _s(value) -> str:
    return "" if value is None else str(value).strip()


def list_runs() -> list[RunSummary]:
    """All runs, newest first, with lightweight counts for the picker."""
    with SessionLocal() as s:
        out: list[RunSummary] = []
        for r in s.query(Run).order_by(Run.created_at.desc()).all():
            sample_count = (
                s.query(func.count(Sample.id)).filter(Sample.run_id == r.id).scalar()
            ) or 0
            decision_count = (
                s.query(func.count(DecisionEvent.id))
                .join(Sample, Sample.id == DecisionEvent.sample_id)
                .filter(Sample.run_id == r.id)
                .scalar()
            ) or 0
            has_plaus = (
                s.query(PlausibilityResult.id)
                .join(Sample, Sample.id == PlausibilityResult.sample_id)
                .filter(Sample.run_id == r.id)
                .first()
                is not None
            )
            has_pred = (
                s.query(PredictionResult.id)
                .join(Sample, Sample.id == PredictionResult.sample_id)
                .filter(Sample.run_id == r.id)
                .first()
                is not None
            )
            out.append(
                RunSummary(
                    id=str(r.id),
                    created_at=r.created_at,
                    filename=r.filename,
                    source=r.source,
                    status=r.status,
                    row_count=r.row_count,
                    sample_count=int(sample_count),
                    decision_count=int(decision_count),
                    has_plausibility=has_plaus,
                    has_prediction=has_pred,
                )
            )
        return out


def get_status(run_id_str: str) -> Optional[RunStatus]:
    """Lightweight pollable progress, all derived from DB counts."""
    try:
        run_uuid = uuid.UUID(str(run_id_str))
    except (ValueError, AttributeError, TypeError):
        return None
    with SessionLocal() as s:
        run = s.query(Run).filter(Run.id == run_uuid).one_or_none()
        if run is None:
            return None
        sample_count = (
            s.query(func.count(Sample.id)).filter(Sample.run_id == run.id).scalar()
        ) or 0
        plaus_done = (
            s.query(func.count(func.distinct(PlausibilityResult.sample_id)))
            .join(Sample, Sample.id == PlausibilityResult.sample_id)
            .filter(Sample.run_id == run.id)
            .scalar()
        ) or 0
        pred_done = (
            s.query(func.count(func.distinct(PredictionResult.sample_id)))
            .join(Sample, Sample.id == PredictionResult.sample_id)
            .filter(Sample.run_id == run.id)
            .scalar()
        ) or 0
        return RunStatus(
            id=str(run.id),
            status=run.status,
            stage=run.stage,
            error=run.error,
            sample_count=int(sample_count),
            plaus_total=int(run.plaus_total or 0),
            plaus_done=int(plaus_done),
            pred_total=int(run.pred_total or 0),
            pred_done=int(pred_done),
            started_at=run.started_at,
            finished_at=run.finished_at,
        )


def compare_run(run_id_str: str) -> Optional[ComparisonResult]:
    """Diff baseline vs. memory predictions per sample, for human spot-checking.

    Uses the `source` tag on prediction_result: the newest 'baseline' vs the
    newest 'memory'/'memoized' per sample. Surfaces only the samples where the
    memory-assisted run *changed* the prediction.
    """
    try:
        run_uuid = uuid.UUID(str(run_id_str))
    except (ValueError, AttributeError, TypeError):
        return None
    with SessionLocal() as s:
        run = s.query(Run).filter(Run.id == run_uuid).one_or_none()
        if run is None:
            return None
        samples = {
            sm.id: sm for sm in s.query(Sample).filter(Sample.run_id == run_uuid).all()
        }
        latest_baseline: dict = {}
        latest_memory: dict = {}
        for p in (
            s.query(PredictionResult)
            .join(Sample, Sample.id == PredictionResult.sample_id)
            .filter(Sample.run_id == run_uuid)
            .order_by(PredictionResult.created_at)
            .all()
        ):
            if p.source == "baseline":
                latest_baseline[p.sample_id] = p
            elif p.source in ("memory", "memoized"):
                latest_memory[p.sample_id] = p

        items: list[ComparisonItem] = []
        compared = changed = memoized = 0
        for sid, sm in samples.items():
            b = latest_baseline.get(sid)
            m = latest_memory.get(sid)
            if b is None or m is None:
                continue
            compared += 1
            if (b.suggested_wg_name or "") != (m.suggested_wg_name or ""):
                changed += 1
                if m.source == "memoized":
                    memoized += 1
                items.append(
                    ComparisonItem(
                        row_index=sm.row_index,
                        bestelltext=sm.bestelltext or "—",
                        baseline_wg=b.suggested_wg_name,
                        baseline_confidence=b.confidence,
                        memory_wg=m.suggested_wg_name,
                        memory_confidence=m.confidence,
                        memory_source=m.source,
                    )
                )
        items.sort(key=lambda x: x.row_index)
        return ComparisonResult(
            compared=compared,
            changed=changed,
            memoized=memoized,
            has_baseline=bool(latest_baseline),
            has_memory=bool(latest_memory),
            items=items,
        )


def _latest_by_row(rows) -> dict:
    """rows = iterable of (row_index, orm_obj) ordered oldest→newest → newest wins."""
    latest: dict = {}
    for row_index, obj in rows:
        latest[int(row_index)] = obj
    return latest


def resume_run(run_id_str: str) -> Optional[RunDetail]:
    """Rebuild a run from the DB, rehydrate SessionState, return the payload."""
    from ..services import plausibility as plaus_svc  # lazy: triggers model/catalog load

    try:
        run_uuid = uuid.UUID(str(run_id_str))
    except (ValueError, AttributeError, TypeError):
        return None

    with SessionLocal() as s:
        run = s.query(Run).filter(Run.id == run_uuid).one_or_none()
        if run is None:
            return None

        samples = (
            s.query(Sample)
            .filter(Sample.run_id == run.id)
            .order_by(Sample.row_index)
            .all()
        )
        if not samples:
            return None

        latest_plaus = _latest_by_row(
            s.query(Sample.row_index, PlausibilityResult)
            .join(PlausibilityResult, PlausibilityResult.sample_id == Sample.id)
            .filter(Sample.run_id == run.id)
            .order_by(PlausibilityResult.created_at)
            .all()
        )
        latest_pred = _latest_by_row(
            s.query(Sample.row_index, PredictionResult)
            .join(PredictionResult, PredictionResult.sample_id == Sample.id)
            .filter(Sample.run_id == run.id)
            .order_by(PredictionResult.created_at)
            .all()
        )
        latest_dec = _latest_by_row(
            s.query(Sample.row_index, DecisionEvent)
            .join(DecisionEvent, DecisionEvent.sample_id == Sample.id)
            .filter(Sample.run_id == run.id)
            .order_by(DecisionEvent.created_at)
            .all()
        )
        all_events = (
            s.query(Sample.row_index, DecisionEvent)
            .join(DecisionEvent, DecisionEvent.sample_id == Sample.id)
            .filter(Sample.run_id == run.id)
            .order_by(DecisionEvent.created_at)
            .all()
        )

        # --- reconstruct the invoices DataFrame from the stored raw rows ------
        # row_index is positional (0..n-1), so indexing by it == a RangeIndex,
        # which keeps the catalog merge + dashboard alignment consistent with
        # the live path.
        records = [sm.raw or {} for sm in samples]
        index = [sm.row_index for sm in samples]
        invoices = pd.DataFrame(records, index=index)

        catalog = plaus_svc.get_catalog()

        # --- rehydrate plausibility_df / prediction_df for the dashboard ------
        plaus_df = None
        pred_df = None
        if latest_plaus:
            plaus_df = attach_catalog_to_invoices(invoices, catalog)
            for col in ("plausibilitaet", "confidence", "reason"):
                plaus_df[col] = None
            for ridx, pr in latest_plaus.items():
                if ridx in plaus_df.index:
                    plaus_df.at[ridx, "plausibilitaet"] = pr.plausibilitaet
                    plaus_df.at[ridx, "confidence"] = pr.confidence
                    plaus_df.at[ridx, "reason"] = pr.reason
            if latest_pred:
                pred_df = plaus_df[plaus_df["plausibilitaet"] == "implausibel"].copy()
                for col in ("predicted_warengruppe", "confidence", "reason"):
                    pred_df[col] = None
                for ridx, pr in latest_pred.items():
                    if ridx in pred_df.index:
                        pred_df.at[ridx, "predicted_warengruppe"] = pr.suggested_wg_name
                        pred_df.at[ridx, "confidence"] = pr.confidence
                        pred_df.at[ridx, "reason"] = pr.reason

        user_decisions = {
            ridx: {
                "stage": ev.stage or "regrouping",
                "decision": ev.decision,
                "new_wg_name": ev.new_value,
            }
            for ridx, ev in latest_dec.items()
        }

        # --- swap the active run into in-memory state ------------------------
        st = get_state()
        st.invoices = invoices
        st.invoices_filename = run.filename
        st.plausibility_df = plaus_df
        st.prediction_df = pred_df
        st.user_decisions = user_decisions
        st.run_id = run.id

        # --- build the response payload --------------------------------------
        upload = UploadSummary(
            filename=run.filename or "",
            row_count=int(len(invoices)),
            column_count=int(invoices.shape[1]),
            detected_columns=[str(c) for c in invoices.columns],
            warengruppe_count=(
                int(invoices["Warengruppe"].nunique())
                if "Warengruppe" in invoices.columns
                else 0
            ),
        )

        plausibility = _build_plausibility(samples, latest_plaus, latest_dec, run) if latest_plaus else None
        prediction = _build_prediction(samples, latest_pred, latest_dec, run) if latest_pred else None

        decisions = [
            DecisionState(
                row_index=ridx,
                decision=ev.decision,
                selected_wg=ev.new_value,
                stage=ev.stage,
            )
            for ridx, ev in latest_dec.items()
            if ev.decision in {"ok", "reject", "regroup", "new_wg"}
        ]
        change_log = [
            ChangeLogRecord(
                timestamp=ev.created_at.isoformat() if ev.created_at else "",
                stage=ev.stage or "regrouping",
                row_index=int(ridx),
                field_changed=ev.field_changed or "",
                old_value=_s(ev.old_value),
                new_value=_s(ev.new_value),
                user_action=ev.user_action or "",
            )
            for ridx, ev in all_events
        ]

        return RunDetail(
            run=_summary(run, samples, latest_plaus, latest_pred, latest_dec),
            upload=upload,
            plausibility=plausibility,
            prediction=prediction,
            decisions=decisions,
            change_log=change_log,
        )


def _summary(run, samples, latest_plaus, latest_pred, latest_dec) -> RunSummary:
    return RunSummary(
        id=str(run.id),
        created_at=run.created_at,
        filename=run.filename,
        source=run.source,
        status=run.status,
        row_count=run.row_count,
        sample_count=len(samples),
        decision_count=len(latest_dec),
        has_plausibility=bool(latest_plaus),
        has_prediction=bool(latest_pred),
    )


def _build_plausibility(samples, latest_plaus, latest_dec, run) -> PlausibilityRunResponse:
    rows: list[PlausibilityRow] = []
    plausible = implausible = unklar = not_assessable = low_conf = obj_fallback = 0
    for sm in samples:
        pr = latest_plaus.get(sm.row_index)
        if pr is None:
            continue
        conf = _conf(pr.confidence)
        dec_ev = latest_dec.get(sm.row_index)
        if pr.plausibilitaet == "plausibel":
            plausible += 1
        elif pr.plausibilitaet == "implausibel":
            implausible += 1
        elif pr.plausibilitaet == "unklar":
            unklar += 1
        if conf == "not_assessable":
            not_assessable += 1
        if conf == "niedrig":
            low_conf += 1
        if pr.objektbez_fallback:
            obj_fallback += 1
        rows.append(
            PlausibilityRow(
                row_index=sm.row_index,
                bestelltext=sm.bestelltext or "[kein Bestelltext]",
                objektbezeichnung=sm.objektbezeichnung or "",
                wg_id=sm.wg_id_original,
                wg_name=sm.wg_name_original,
                kostenart=sm.kostenart,
                betrag_eur=_f(sm.betrag_eur),
                plausibilitaet=(
                    pr.plausibilitaet
                    if pr.plausibilitaet in {"plausibel", "implausibel", "unklar"}
                    else None
                ),
                confidence=conf,
                unterstuetzende_signale=list(pr.signale_pro or []),
                widersprechende_signale=list(pr.signale_contra or []),
                reason=_s(pr.reason),
                decision=dec_ev.decision if dec_ev else None,
            )
        )
    stats = PlausibilityStats(
        total=len(rows),
        plausible=plausible,
        implausible=implausible,
        unklar=unklar,
        not_assessable=not_assessable,
        low_confidence=low_conf,
        objektbez_fallback=obj_fallback,
    )
    return PlausibilityRunResponse(
        stats=stats,
        rows=rows,
        cost_usd=float(run.cost_usd or 0.0),
        api_calls=int(run.api_calls or 0),
        cache_hits=0,
    )


def _build_prediction(samples, latest_pred, latest_dec, run) -> PredictionRunResponse:
    rows: list[PredictionRow] = []
    regrouped_hm = low_conf = 0
    for sm in samples:
        pr = latest_pred.get(sm.row_index)
        if pr is None:
            continue
        conf = _conf(pr.confidence)
        dec_ev = latest_dec.get(sm.row_index)
        if pr.suggested_wg_name and conf in {"hoch", "mittel"}:
            regrouped_hm += 1
        if conf == "niedrig":
            low_conf += 1
        rows.append(
            PredictionRow(
                row_index=sm.row_index,
                bestelltext=sm.bestelltext or "—",
                current_wg_name=sm.wg_name_original or sm.wg_id_original or None,
                suggested_wg_name=pr.suggested_wg_name,
                betrag_eur=_f(sm.betrag_eur),
                confidence=conf,
                reason=_s(pr.reason),
                objektbez_signal=bool(pr.objektbez_signal),
                ef_missing=bool(pr.ef_missing),
                decision=dec_ev.decision if dec_ev else None,
            )
        )
    stats = PredictionStats(
        total=len(rows),
        regrouped_high_med=regrouped_hm,
        low_confidence=low_conf,
        no_ef=0,
        confirmed=0,
    )
    return PredictionRunResponse(
        stats=stats,
        rows=rows,
        cost_usd=0.0,
        api_calls=0,
        cache_hits=0,
    )
