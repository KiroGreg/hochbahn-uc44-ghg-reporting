"""Server-side run orchestration.

Runs the two-stage analysis (plausibility → prediction) in a background daemon
thread, **decoupled from the browser request**, and persists results
**incrementally per chunk** — so the frontend can derive live progress straight
from the DB (done = COUNT(result rows), total = run.plaus_total / pred_total)
and the user can close the page and come back to a finished (or still-running)
run.

It reuses the existing plausibility/prediction services per chunk, so the
LLM/model logic is untouched; only the granularity of persistence changes.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

import pandas as pd

from ..core.data import attach_catalog_to_invoices
from ..core.state import get_state
from ..services import persistence

logger = logging.getLogger(__name__)

# Rows per model call / DB write. Small enough for frequent progress updates,
# large enough to keep the model's internal worker pool busy.
CHUNK_SIZE = 25

_lock = threading.Lock()
_running: set = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _chunk_delay() -> float:
    """Artificial per-chunk delay (seconds), for demoing long-running analyses.

    Read at call time so it can be toggled via env (UC44_ANALYZE_CHUNK_DELAY)
    without code changes. Defaults to 0 — no slowdown in normal operation.
    """
    try:
        return max(0.0, float(os.getenv("UC44_ANALYZE_CHUNK_DELAY", "0")))
    except ValueError:
        return 0.0


def _chunks(df: pd.DataFrame, size: int):
    for i in range(0, len(df), size):
        yield df.iloc[i : i + size]


def is_running(run_id) -> bool:
    with _lock:
        return run_id in _running


def start_analysis(max_rows, augment: Optional[dict] = None) -> object:
    """Launch the analysis for the active run in a background thread.

    `augment` (or None) carries the correction-memory options
    (enable_hints, top_n, threshold, memo_threshold). Returns the run_id.
    Raises ValueError if there is no active run/data, RuntimeError if an
    analysis for it is already in flight.
    """
    st = get_state()
    if st.run_id is None or st.invoices is None:
        raise ValueError("Kein aktiver Lauf oder keine Daten geladen.")
    run_id = st.run_id
    invoices = st.invoices
    with _lock:
        if run_id in _running:
            raise RuntimeError("Analyse läuft bereits.")
        _running.add(run_id)
    thread = threading.Thread(
        target=_run_analysis, args=(run_id, invoices, max_rows, augment), daemon=True
    )
    thread.start()
    return run_id


def _memo_prediction_row(idx, row, truth_wg):
    """Synthesise a PredictionRow for a memoised (LLM-skipped) row."""
    from ..schemas.models import PredictionRow

    bestell = str(row.get("Bestelltext") or "").strip() or "—"
    current = str(row.get("wg_name") or row.get("Warengruppe") or "").strip() or None
    return PredictionRow(
        row_index=int(idx),
        bestelltext=bestell,
        current_wg_name=current,
        suggested_wg_name=truth_wg,
        betrag_eur=None,
        confidence="hoch",
        reason="Übernahme aus bestätigtem, quasi-identischem Fall (memoized)",
        objektbez_signal=False,
        ef_missing=False,
        source="memoized",
    )


def _predict_chunk(chunk, augment: Optional[dict]) -> list:
    """Predict one chunk. With augment: memoise near-identical rows and inject
    retrieved hints into the rest. Returns a list of PredictionRow."""
    from ..services import prediction as pred_svc

    if not augment or not augment.get("enable_hints"):
        rows = list(pred_svc.run(chunk, max_rows=None).rows)
        for r in rows:
            r.source = "baseline"
        return rows

    from ..services import hints

    memo_rows: list = []
    hint_map: dict = {}
    keep_idx: list = []
    for idx, row in chunk.iterrows():
        truth, xml = hints.augment_row(
            row.to_dict(),
            top_n=int(augment.get("top_n", 6)),
            threshold=float(augment.get("threshold", 0.82)),
            memo_threshold=float(augment.get("memo_threshold", 0.97)),
        )
        if truth:
            memo_rows.append(_memo_prediction_row(idx, row, truth))
        else:
            keep_idx.append(idx)
            if xml:
                hint_map[idx] = xml

    rows = list(memo_rows)
    if keep_idx:
        sub = chunk.loc[keep_idx]
        resp = pred_svc.run(sub, max_rows=None, hint_provider=lambda r: hint_map.get(r.name, ""))
        for r in resp.rows:
            r.source = "memory"
        rows.extend(resp.rows)
    return rows


def _run_analysis(run_id, invoices: pd.DataFrame, max_rows, augment=None) -> None:
    from ..services import plausibility as plaus_svc
    from ..services import prediction as pred_svc

    try:
        persistence.update_run_progress(
            run_id,
            status="running",
            stage="plausibility",
            error=None,
            started_at=_now(),
            finished_at=None,
        )
        catalog = plaus_svc.get_catalog()

        # --- Stage 1: plausibility, chunked + persisted incrementally --------
        inv = invoices.iloc[:max_rows] if max_rows else invoices
        persistence.update_run_progress(run_id, plaus_total=int(len(inv)))

        plaus_rows_all = []
        for chunk in _chunks(inv, CHUNK_SIZE):
            resp = plaus_svc.run(chunk, max_rows=None)
            persistence.save_plausibility(run_id, resp.rows)  # write as we go
            plaus_rows_all.extend(resp.rows)
            time.sleep(_chunk_delay())  # demo-only slowdown (env-gated, default 0)

        plaus_df = attach_catalog_to_invoices(invoices, catalog)
        for col in ("plausibilitaet", "confidence", "reason"):
            plaus_df[col] = None
        for r in plaus_rows_all:
            if r.row_index in plaus_df.index:
                plaus_df.at[r.row_index, "plausibilitaet"] = r.plausibilitaet
                plaus_df.at[r.row_index, "confidence"] = r.confidence
                plaus_df.at[r.row_index, "reason"] = r.reason
        st = get_state()
        if st.run_id == run_id:
            st.plausibility_df = plaus_df

        # --- Stage 2: prediction over the implausible rows -------------------
        persistence.update_run_progress(run_id, stage="prediction")
        flagged = plaus_df[plaus_df["plausibilitaet"] == "implausibel"]
        persistence.update_run_progress(run_id, pred_total=int(len(flagged)))

        if not flagged.empty:
            # Augmented runs read the correction memory — make sure confirmed
            # rows are embedded before retrieval.
            if augment and augment.get("enable_hints"):
                try:
                    from ..services import memory
                    memory.embed_pending()
                except Exception:  # noqa: BLE001
                    logger.exception("embed_pending failed for run %s", run_id)

            pred_df = flagged.copy()
            for col in ("predicted_warengruppe", "confidence", "reason"):
                pred_df[col] = None
            pred_rows_all = []
            for chunk in _chunks(flagged, CHUNK_SIZE):
                rows = _predict_chunk(chunk, augment)
                persistence.save_predictions(run_id, rows)  # write as we go
                pred_rows_all.extend(rows)
                time.sleep(_chunk_delay())  # demo-only slowdown (env-gated, default 0)
            for r in pred_rows_all:
                if r.row_index in pred_df.index:
                    pred_df.at[r.row_index, "predicted_warengruppe"] = r.suggested_wg_name
                    pred_df.at[r.row_index, "confidence"] = r.confidence
                    pred_df.at[r.row_index, "reason"] = r.reason
            if st.run_id == run_id:
                st.prediction_df = pred_df

        # --- cost snapshot ---------------------------------------------------
        try:
            cost = float(plaus_svc.get_model().usage.cost_usd) + float(
                pred_svc.get_model().usage.cost_usd
            )
            calls = int(plaus_svc.get_model().usage.calls) + int(
                pred_svc.get_model().usage.calls
            )
            model_name = str(plaus_svc.get_config().get("llm", {}).get("model", "")) or None
            persistence.update_run_usage(run_id, model_name, cost, calls)
        except Exception:  # noqa: BLE001
            logger.exception("Could not snapshot usage for run %s", run_id)

        # Materialise the correction-memory rows for this run (predicted_wg +
        # outcome; corrected/outcome get refined per-decision during review).
        try:
            from ..services import memory
            memory.refresh_run(run_id)
        except Exception:  # noqa: BLE001
            logger.exception("Could not refresh correction memory for run %s", run_id)

        persistence.update_run_progress(
            run_id, status="done", stage=None, finished_at=_now()
        )
        logger.info("Analysis done for run %s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis failed for run %s", run_id)
        persistence.update_run_progress(
            run_id,
            status="failed",
            stage=None,
            error=str(exc)[:500],
            finished_at=_now(),
        )
    finally:
        with _lock:
            _running.discard(run_id)
