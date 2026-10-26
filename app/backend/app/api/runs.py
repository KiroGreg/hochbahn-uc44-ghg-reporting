"""Run history + resume endpoints.

`GET /api/runs` lists past Läufe for the history picker; `GET /api/runs/{id}`
rebuilds one from the DB, makes it the active run, and returns everything the
frontend needs to continue where the user left off (no LLM re-run).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..schemas.models import ComparisonResult, RunDetail, RunOptions, RunStatus, RunSummary
from ..services import orchestrator
from ..services import runs as svc

router = APIRouter(prefix="/api/runs", tags=["runs"])

logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=list[RunSummary],
    summary="List persisted runs (history), newest first.",
)
def list_runs() -> list[RunSummary]:
    return svc.list_runs()


@router.post(
    "/analyze",
    response_model=RunStatus,
    summary="Start the two-stage analysis for the active run in the background.",
)
def analyze(options: RunOptions) -> RunStatus:
    augment = {
        "enable_hints": options.enable_hints,
        "top_n": options.hint_top_n,
        "threshold": options.hint_threshold,
        "memo_threshold": options.memo_threshold,
    }
    try:
        run_id = orchestrator.start_analysis(options.max_rows, augment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status = svc.get_status(str(run_id))
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return status


@router.get(
    "/{run_id}/status",
    response_model=RunStatus,
    summary="Poll a run's progress (derived live from the DB).",
)
def run_status(run_id: str) -> RunStatus:
    status = svc.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return status


@router.get(
    "/{run_id}/compare",
    response_model=ComparisonResult,
    summary="Diff baseline vs. memory predictions for a run (spot-check changes).",
)
def compare(run_id: str) -> ComparisonResult:
    result = svc.compare_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return result


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="Resume a run: rebuild it from the DB and make it the active run.",
)
def get_run(run_id: str) -> RunDetail:
    detail = svc.resume_run(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found or has no samples.")
    return detail
