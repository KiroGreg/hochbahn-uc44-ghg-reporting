"""LLM enrichment endpoints for the Warengruppen catalog.

Atomic (synchronous, nothing persisted until the user saves via the normal
Warengruppen PUT): ``/preview``, ``/refine``, ``/history-signal(s)``.
Bulk (background daemon, persisted proposals): ``/batch...`` + ``/proposal/...``.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..schemas.models import (
    BulkEnrichRequest,
    EnrichApplyRequest,
    EnrichBatchDetail,
    EnrichBatchStatus,
    EnrichProposal,
    EnrichRefineRequest,
    EnrichRequest,
    EnrichSuggestion,
    HistorySignal,
    ProposalRefineRequest,
)
from ..services import enrichment
from ..services import enrichment_batch as batch_svc
from ..services import warengruppen as wg_svc

router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])

logger = logging.getLogger(__name__)


def _history_for(use_history: bool, wg_id: Optional[str], wg_name: str) -> Optional[HistorySignal]:
    """Fetch the history signal only when requested and the WG is saved (has an id)."""
    if not use_history or not wg_id:
        return None
    return wg_svc.history_signal(wg_id, wg_name)


def _config_or_error(exc: enrichment.EnrichmentError) -> HTTPException:
    """503 for a missing key (recoverable config issue), 502 for other LLM errors."""
    status = 503 if isinstance(exc, enrichment.EnrichmentConfigError) else 502
    return HTTPException(status_code=status, detail=str(exc))


# --- atomic (single Warengruppe, ephemeral) ---------------------------------

@router.post("/preview", response_model=EnrichSuggestion, summary="Generate a proposal (atomic, not saved).")
def preview(req: EnrichRequest) -> EnrichSuggestion:
    history = _history_for(req.use_history, req.wg_id, req.wg_name)
    try:
        return enrichment.enrich_one(req.wg_name, req.content, req.plan, history)
    except enrichment.EnrichmentError as exc:
        raise _config_or_error(exc) from exc


@router.post("/refine", response_model=EnrichSuggestion, summary="Incorporate annotations (atomic).")
def refine(req: EnrichRefineRequest) -> EnrichSuggestion:
    history = _history_for(req.use_history, req.wg_id, req.wg_name)
    try:
        return enrichment.refine_one(req.wg_name, req.current, req.annotations, req.plan, history)
    except enrichment.EnrichmentError as exc:
        raise _config_or_error(exc) from exc


@router.get(
    "/history-signal/{wg_id}",
    response_model=HistorySignal,
    summary="Manual in-/out-flux (correction history) for one Warengruppe.",
)
def history_signal(wg_id: str) -> HistorySignal:
    return wg_svc.history_signal(wg_id)


@router.get(
    "/history-signals",
    response_model=dict[str, dict[str, int]],
    summary="In-/out-flux counts for every Warengruppe (wizard selection badges).",
)
def history_signals() -> dict[str, dict[str, int]]:
    return wg_svc.history_signals_all()


# --- bulk (background batch, persisted) -------------------------------------

@router.post("/batch", response_model=EnrichBatchStatus, summary="Start a bulk enrichment batch (background).")
def start_batch(req: BulkEnrichRequest) -> EnrichBatchStatus:
    try:
        batch_id = batch_svc.start_batch(req.wg_ids, req.plan, req.use_history)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    status = batch_svc.get_status(batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return status


@router.get("/batch", response_model=list[EnrichBatchStatus], summary="List enrichment batches (newest first).")
def list_batches() -> list[EnrichBatchStatus]:
    return batch_svc.list_batches()


@router.get("/batch/{batch_id}/status", response_model=EnrichBatchStatus, summary="Poll a batch's progress.")
def batch_status(batch_id: str) -> EnrichBatchStatus:
    status = batch_svc.get_status(batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return status


@router.get("/batch/{batch_id}", response_model=EnrichBatchDetail, summary="Batch status + proposals (review queue).")
def batch_detail(batch_id: str) -> EnrichBatchDetail:
    detail = batch_svc.get_detail(batch_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return detail


@router.post("/proposal/{proposal_id}/apply", response_model=EnrichProposal, summary="Apply a proposal to its Warengruppe.")
def apply_proposal(proposal_id: str, req: EnrichApplyRequest) -> EnrichProposal:
    try:
        pr = batch_svc.apply_proposal(proposal_id, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if pr is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return pr


@router.post("/proposal/{proposal_id}/reject", response_model=EnrichProposal, summary="Reject a proposal.")
def reject_proposal(proposal_id: str) -> EnrichProposal:
    pr = batch_svc.reject_proposal(proposal_id)
    if pr is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return pr


@router.post("/proposal/{proposal_id}/refine", response_model=EnrichProposal, summary="Refine a proposal with annotations.")
def refine_proposal(proposal_id: str, req: ProposalRefineRequest) -> EnrichProposal:
    try:
        pr = batch_svc.refine_proposal(proposal_id, req.annotations, req.content)
    except enrichment.EnrichmentError as exc:
        raise _config_or_error(exc) from exc
    if pr is None:
        raise HTTPException(status_code=404, detail="Proposal not found.")
    return pr
