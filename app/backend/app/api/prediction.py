"""Prediction / regrouping endpoints (model 2)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..core.state import get_state
from ..schemas.models import (
    CatalogEntry,
    DecisionRequest,
    PredictionRunResponse,
    RunOptions,
)
from ..services import persistence
from ..services import prediction as svc
from ..core.data import catalog_to_entries

router = APIRouter(prefix="/api/prediction", tags=["prediction"])

logger = logging.getLogger(__name__)


@router.get(
    "/catalog",
    response_model=list[CatalogEntry],
    summary="Return the Warengruppe catalog the prediction model picks from.",
)
def catalog() -> list[CatalogEntry]:
    raw = catalog_to_entries(svc.get_catalog())
    return [CatalogEntry(**r) for r in raw]


@router.post(
    "/run",
    response_model=PredictionRunResponse,
    summary="Run prediction model 2 over the entries flagged implausible by model 1.",
)
def run(options: RunOptions) -> PredictionRunResponse:
    state = get_state()
    if state.invoices is None:
        raise HTTPException(status_code=400, detail="No invoices uploaded.")
    if state.plausibility_df is None:
        raise HTTPException(
            status_code=400,
            detail="No plausibility result. Run /api/plausibility/run first.",
        )

    flagged = state.plausibility_df[
        state.plausibility_df["plausibilitaet"] == "implausibel"
    ]
    if flagged.empty:
        # Nothing to do — return an empty result.
        return PredictionRunResponse(
            stats={
                "total": 0, "regrouped_high_med": 0, "low_confidence": 0,
                "no_ef": 0, "confirmed": 0,
            },
            rows=[],
            cost_usd=0.0,
            api_calls=0,
            cache_hits=0,
        )

    result = svc.run(flagged, options.max_rows)

    # Persist as a dataframe so the dashboard can use it.
    df = flagged.copy()
    df["predicted_warengruppe"] = None
    df["confidence"] = None
    df["reason"] = None
    for r in result.rows:
        df.at[r.row_index, "predicted_warengruppe"] = r.suggested_wg_name
        df.at[r.row_index, "confidence"] = r.confidence
        df.at[r.row_index, "reason"] = r.reason
    state.prediction_df = df

    # Write-through: persist model-2 results against the active run.
    try:
        persistence.save_predictions(state.run_id, result.rows)
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist prediction results")

    return result


@router.post(
    "/decision",
    summary="Record the user's decision on a single regrouping suggestion.",
)
def decision(req: DecisionRequest) -> dict:
    state = get_state()
    state.user_decisions[req.row_index] = {
        "stage": "prediction",
        "decision": req.decision,
        "new_wg_name": req.new_wg_name,
    }
    try:
        persistence.save_decision(
            state.run_id,
            req.row_index,
            req.decision,
            new_wg_name=req.new_wg_name,
            old_value=req.old_value,
            stage="regrouping",
        )
        from ..services import memory
        memory.upsert_sample(state.run_id, req.row_index)
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist prediction decision")
    return {"ok": True}


@router.delete(
    "/decision/{row_index}",
    summary="Undo a single decision (back to pending) without touching the others.",
)
def clear_decision(row_index: int) -> dict:
    state = get_state()
    state.user_decisions.pop(row_index, None)
    return {"ok": True}
