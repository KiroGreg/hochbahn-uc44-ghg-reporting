"""Plausibility-check endpoints (model 1)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..core.data import attach_catalog_to_invoices
from ..core.state import get_state
from ..schemas.models import (
    DecisionRequest,
    PlausibilityRunResponse,
    RunOptions,
)
from ..services import persistence
from ..services import plausibility as svc

router = APIRouter(prefix="/api/plausibility", tags=["plausibility"])

logger = logging.getLogger(__name__)


@router.post(
    "/run",
    response_model=PlausibilityRunResponse,
    summary="Run plausibility model 1 over the uploaded invoices.",
)
def run(options: RunOptions) -> PlausibilityRunResponse:
    state = get_state()
    if state.invoices is None:
        raise HTTPException(status_code=400, detail="No invoices uploaded. Call /api/upload first.")
    result = svc.run(state.invoices, options.max_rows)
    # Persist a dataframe-shaped copy for downstream stages. The
    # `plausibilitaet` enum drives the filter for the regrouping run.
    # Enrich with catalog columns (notably `wg_name`) so the regrouping
    # stage can show the original Warengruppe ("WG Bisher"). This mirrors
    # the merge the plausibility service does internally; the 1:1 left
    # merge on `Warengruppe` preserves row order and index, so the
    # `df.at[r.row_index, ...]` writes below stay aligned.
    df = attach_catalog_to_invoices(state.invoices, svc.get_catalog())
    df["plausibilitaet"] = None
    df["confidence"] = None
    df["reason"] = None
    for r in result.rows:
        df.at[r.row_index, "plausibilitaet"] = r.plausibilitaet
        df.at[r.row_index, "confidence"] = r.confidence
        df.at[r.row_index, "reason"] = r.reason
    state.plausibility_df = df

    # Write-through: persist model-1 results against the active run.
    try:
        persistence.save_plausibility(state.run_id, result.rows)
        model_name = str(svc.get_config().get("llm", {}).get("model", "")) or None
        persistence.update_run_usage(
            state.run_id, model_name, result.cost_usd, result.api_calls
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist plausibility results")

    return result


@router.post(
    "/decision",
    summary="Record the user's decision on a single plausibility row.",
)
def decision(req: DecisionRequest) -> dict:
    state = get_state()
    state.user_decisions[req.row_index] = {
        "stage": "plausibility",
        "decision": req.decision,
    }
    try:
        persistence.save_decision(
            state.run_id,
            req.row_index,
            req.decision,
            new_wg_name=req.new_wg_name,
            old_value=req.old_value,
            stage="plausibility",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist plausibility decision")
    return {"ok": True}
