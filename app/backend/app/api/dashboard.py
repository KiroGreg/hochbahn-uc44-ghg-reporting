"""Dashboard / KPI endpoint."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from ..core.state import get_state
from ..schemas.models import BudgetStats, DashboardResponse
from ..services import dashboard as svc
from ..services import plausibility as plaus_svc

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Aggregate KPIs, funnel and Top-WG ranking for the dashboard view.",
)
def dashboard(jahr: Optional[int] = Query(default=None, description="Jahr für die Emissionsfaktoren")) -> DashboardResponse:
    return svc.build(get_state(), jahr=jahr)


@router.get(
    "/budget",
    response_model=BudgetStats,
    summary="Combined token spend across both models.",
)
def budget() -> BudgetStats:
    cfg = plaus_svc.get_config()
    from ..services import prediction as pr

    p_model = plaus_svc.get_model()
    pr_cost = 0.0
    pr_calls = 0
    pr_cache = 0
    if pr._model is not None:
        pr_cost = pr._model.usage.cost_usd
        pr_calls = pr._model.usage.calls
        pr_cache = pr._model.usage.cache_hits

    return svc.budget(
        cfg,
        plaus_usage_cost=p_model.usage.cost_usd,
        pred_usage_cost=pr_cost,
        plaus_calls=p_model.usage.calls,
        pred_calls=pr_calls,
        plaus_cache=p_model.usage.cache_hits,
        pred_cache=pr_cache,
    )
