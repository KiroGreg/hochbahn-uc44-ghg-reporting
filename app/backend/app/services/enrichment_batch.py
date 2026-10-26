"""Background orchestration for bulk Warengruppen enrichment.

Mirrors ``services/orchestrator.py``: ``start_batch`` launches a **daemon thread**
decoupled from the request, which enriches the selected Warengruppen one by one
and **persists each proposal immediately** — so the wizard derives live progress
straight from the DB (``done = COUNT(proposal)`` over ``batch.total``) and the
review queue survives closing the tab. Accepting a proposal writes through the
normal ``warengruppen.update()`` path (which resets the catalog cache).

The single-WG (atomic) path does not come through here — it runs synchronously in
the router and persists nothing until the user saves.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from ..core.db import SessionLocal
from ..models.orm import EnrichmentBatch, EnrichmentProposal, Warengruppe
from ..schemas.models import (
    EnrichBatchDetail,
    EnrichBatchStatus,
    EnrichContent,
    EnrichPlan,
    EnrichProposal,
    EnrichSuggestion,
    FieldAnnotations,
    WarengruppeUpsertRequest,
)
from . import enrichment
from . import warengruppen as wg_svc

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_running: set[str] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value) -> Optional[uuid.UUID]:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def is_running(batch_id: str) -> bool:
    with _lock:
        return str(batch_id) in _running


# --- schema mapping ---------------------------------------------------------

def _plan_of(pr: EnrichmentProposal) -> EnrichPlan:
    return EnrichPlan(**pr.plan) if pr.plan else EnrichPlan()


def _proposal_to_schema(pr: EnrichmentProposal) -> EnrichProposal:
    plan = _plan_of(pr)
    return EnrichProposal(
        id=str(pr.id),
        batch_id=str(pr.batch_id),
        wg_id=pr.wg_id,
        wg_name=pr.wg_name,
        plan=plan,
        current=EnrichContent(
            beschreibung=pr.current_beschreibung,
            examples_enthalten=list(pr.current_examples_enthalten or []),
            examples_nicht_enthalten=list(pr.current_examples_nicht_enthalten or []),
        ),
        suggestion=EnrichSuggestion(
            beschreibung=pr.proposed_beschreibung,
            examples_enthalten=list(pr.proposed_examples_enthalten or []),
            examples_nicht_enthalten=list(pr.proposed_examples_nicht_enthalten or []),
            konfidenz=pr.konfidenz,
            anmerkung=pr.anmerkung,
            status=pr.status_llm,
            diff_kurz=pr.diff_kurz,
            plan=plan,
            history_used=bool(pr.history_used),
            prompt_tokens=pr.prompt_tokens or 0,
            completion_tokens=pr.completion_tokens or 0,
            cost_usd=float(pr.cost_usd) if pr.cost_usd is not None else None,
        ),
        state=pr.state,
        applied=bool(pr.applied),
        history_used=bool(pr.history_used),
    )


def _status_of(session, batch: EnrichmentBatch) -> EnrichBatchStatus:
    done = (
        session.query(func.count(EnrichmentProposal.id))
        .filter(EnrichmentProposal.batch_id == batch.id)
        .scalar()
    ) or 0
    return EnrichBatchStatus(
        id=str(batch.id),
        status=batch.status,
        total=batch.total or 0,
        done=int(done),
        error=batch.error,
        use_history=bool(batch.use_history),
        started_at=batch.started_at,
        finished_at=batch.finished_at,
        cost_usd=float(batch.cost_usd) if batch.cost_usd is not None else None,
        created_at=batch.created_at,
    )


# --- launch + run -----------------------------------------------------------

def start_batch(
    wg_ids: list[str], plan: Optional[EnrichPlan], use_history: bool
) -> str:
    """Create a batch row for the valid selection and launch the daemon thread.

    Raises ValueError when none of the given wg_ids exist.
    """
    seen: set[str] = set()
    wanted = [w for w in (str(x).strip() for x in wg_ids) if w and not (w in seen or seen.add(w))]
    with SessionLocal() as session:
        found = (
            session.query(Warengruppe.wg_id)
            .filter(Warengruppe.wg_id.in_(wanted))
            .all()
        )
        valid = [r[0] for r in found]
        if not valid:
            raise ValueError("Keine gültigen Warengruppen ausgewählt.")
        batch = EnrichmentBatch(
            status="running",
            total=len(valid),
            use_history=bool(use_history),
            plan=(plan.model_dump() if plan else None),
            model_name=enrichment.MODEL,
            started_at=_now(),
        )
        session.add(batch)
        session.commit()
        batch_id = str(batch.id)

    with _lock:
        _running.add(batch_id)
    threading.Thread(
        target=_run_batch, args=(batch_id, valid, plan, bool(use_history)), daemon=True
    ).start()
    return batch_id


def _fail(batch_id: str, message: str) -> None:
    with SessionLocal() as session:
        batch = session.get(EnrichmentBatch, _uuid(batch_id))
        if batch is not None:
            batch.status = "failed"
            batch.error = message[:500]
            batch.finished_at = _now()
            session.commit()


def _run_batch(
    batch_id: str, wg_ids: list[str], plan: Optional[EnrichPlan], use_history: bool
) -> None:
    bid = _uuid(batch_id)
    try:
        for wg_id in wg_ids:
            # Load the current content fresh per WG (it may have changed).
            with SessionLocal() as session:
                wg = (
                    session.query(Warengruppe)
                    .filter(Warengruppe.wg_id == wg_id)
                    .one_or_none()
                )
                if wg is None:
                    continue
                wg_name = wg.wg_name
                content = EnrichContent(
                    beschreibung=wg.beschreibung,
                    examples_enthalten=list(wg.examples_enthalten or []),
                    examples_nicht_enthalten=list(wg.examples_nicht_enthalten or []),
                )

            eff_plan = plan or enrichment.derive_plan(content)
            history = wg_svc.history_signal(wg_id, wg_name) if use_history else None

            try:
                sug = enrichment.enrich_one(wg_name, content, eff_plan, history)
                err = None
            except enrichment.EnrichmentConfigError:
                raise  # no key → the whole batch cannot proceed
            except enrichment.EnrichmentError as exc:  # per-WG failure → error row
                logger.warning("Enrichment failed for %s: %s", wg_id, exc)
                sug = None
                err = str(exc)

            with SessionLocal() as session:
                if sug is not None:
                    pr = EnrichmentProposal(
                        batch_id=bid,
                        wg_id=wg_id,
                        wg_name=wg_name,
                        plan=eff_plan.model_dump(),
                        current_beschreibung=content.beschreibung,
                        current_examples_enthalten=content.examples_enthalten,
                        current_examples_nicht_enthalten=content.examples_nicht_enthalten,
                        proposed_beschreibung=sug.beschreibung,
                        proposed_examples_enthalten=sug.examples_enthalten,
                        proposed_examples_nicht_enthalten=sug.examples_nicht_enthalten,
                        konfidenz=sug.konfidenz,
                        anmerkung=sug.anmerkung,
                        status_llm=sug.status,
                        diff_kurz=sug.diff_kurz,
                        history_used=sug.history_used,
                        state="pending",
                        prompt_tokens=sug.prompt_tokens,
                        completion_tokens=sug.completion_tokens,
                        cost_usd=sug.cost_usd,
                    )
                else:
                    pr = EnrichmentProposal(
                        batch_id=bid,
                        wg_id=wg_id,
                        wg_name=wg_name,
                        plan=eff_plan.model_dump(),
                        current_beschreibung=content.beschreibung,
                        current_examples_enthalten=content.examples_enthalten,
                        current_examples_nicht_enthalten=content.examples_nicht_enthalten,
                        proposed_beschreibung=content.beschreibung,
                        proposed_examples_enthalten=content.examples_enthalten,
                        proposed_examples_nicht_enthalten=content.examples_nicht_enthalten,
                        konfidenz=None,
                        anmerkung=err,
                        status_llm="fehler",
                        history_used=bool(history and (history.top_influx or history.top_outflux)),
                        state="rejected",
                    )
                session.add(pr)
                batch = session.get(EnrichmentBatch, bid)
                if batch is not None and sug is not None:
                    batch.cost_usd = float(batch.cost_usd or 0) + float(sug.cost_usd or 0)
                    batch.api_calls = int(batch.api_calls or 0) + 1
                session.commit()

        with SessionLocal() as session:
            batch = session.get(EnrichmentBatch, bid)
            if batch is not None:
                batch.status = "done"
                batch.finished_at = _now()
                session.commit()
        logger.info("Enrichment batch %s done", batch_id)
    except enrichment.EnrichmentConfigError as exc:
        _fail(batch_id, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Enrichment batch %s failed", batch_id)
        _fail(batch_id, str(exc))
    finally:
        with _lock:
            _running.discard(batch_id)


# --- read -------------------------------------------------------------------

def get_status(batch_id: str) -> Optional[EnrichBatchStatus]:
    bid = _uuid(batch_id)
    if bid is None:
        return None
    with SessionLocal() as session:
        batch = session.get(EnrichmentBatch, bid)
        return _status_of(session, batch) if batch is not None else None


def get_detail(batch_id: str) -> Optional[EnrichBatchDetail]:
    bid = _uuid(batch_id)
    if bid is None:
        return None
    with SessionLocal() as session:
        batch = session.get(EnrichmentBatch, bid)
        if batch is None:
            return None
        proposals = (
            session.query(EnrichmentProposal)
            .filter(EnrichmentProposal.batch_id == bid)
            .order_by(EnrichmentProposal.created_at)
            .all()
        )
        return EnrichBatchDetail(
            status=_status_of(session, batch),
            proposals=[_proposal_to_schema(p) for p in proposals],
        )


def list_batches(limit: int = 50) -> list[EnrichBatchStatus]:
    with SessionLocal() as session:
        batches = (
            session.query(EnrichmentBatch)
            .order_by(EnrichmentBatch.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_status_of(session, b) for b in batches]


# --- proposal actions -------------------------------------------------------

def _final_content(pr: EnrichmentProposal, override: Optional[EnrichContent]) -> EnrichContent:
    if override is not None:
        return override
    return EnrichContent(
        beschreibung=pr.proposed_beschreibung,
        examples_enthalten=list(pr.proposed_examples_enthalten or []),
        examples_nicht_enthalten=list(pr.proposed_examples_nicht_enthalten or []),
    )


def apply_proposal(
    proposal_id: str, override: Optional[EnrichContent] = None
) -> Optional[EnrichProposal]:
    """Write the proposal (or the edited override) to its Warengruppe.

    Emission factors and the name are preserved from the live row — only the
    enrichment fields change. Returns None if the proposal id is unknown; raises
    ValueError if the Warengruppe no longer exists.
    """
    pid = _uuid(proposal_id)
    if pid is None:
        return None
    with SessionLocal() as session:
        pr = session.get(EnrichmentProposal, pid)
        if pr is None:
            return None
        wg_id = pr.wg_id
        content = _final_content(pr, override)

    row = wg_svc.get(wg_id)
    if row is None:
        raise ValueError(f"Warengruppe '{wg_id}' existiert nicht mehr.")

    wg_svc.update(
        wg_id,
        WarengruppeUpsertRequest(
            wg_id=wg_id,
            wg_name=row.wg_name,
            beschreibung=content.beschreibung or None,
            examples_enthalten=list(content.examples_enthalten or []),
            examples_nicht_enthalten=list(content.examples_nicht_enthalten or []),
            emissionsfaktoren=row.emissionsfaktoren,
        ),
    )

    with SessionLocal() as session:
        pr = session.get(EnrichmentProposal, pid)
        # Persist any edited values so the queue shows what was applied.
        if override is not None:
            pr.proposed_beschreibung = content.beschreibung or None
            pr.proposed_examples_enthalten = list(content.examples_enthalten or [])
            pr.proposed_examples_nicht_enthalten = list(content.examples_nicht_enthalten or [])
        pr.state = "accepted"
        pr.applied = True
        pr.applied_at = _now()
        session.commit()
        return _proposal_to_schema(pr)


def reject_proposal(proposal_id: str) -> Optional[EnrichProposal]:
    pid = _uuid(proposal_id)
    if pid is None:
        return None
    with SessionLocal() as session:
        pr = session.get(EnrichmentProposal, pid)
        if pr is None:
            return None
        pr.state = "rejected"
        pr.applied = False
        session.commit()
        return _proposal_to_schema(pr)


def refine_proposal(
    proposal_id: str,
    annotations: FieldAnnotations,
    override: Optional[EnrichContent] = None,
) -> Optional[EnrichProposal]:
    """Re-run the LLM to incorporate annotations; update the proposal in place."""
    pid = _uuid(proposal_id)
    if pid is None:
        return None
    with SessionLocal() as session:
        pr = session.get(EnrichmentProposal, pid)
        if pr is None:
            return None
        wg_id, wg_name = pr.wg_id, pr.wg_name
        plan = _plan_of(pr)
        use_history = bool(pr.history_used)
        current = _final_content(pr, override)

    history = wg_svc.history_signal(wg_id, wg_name) if use_history else None
    sug = enrichment.refine_one(wg_name, current, annotations, plan, history)

    with SessionLocal() as session:
        pr = session.get(EnrichmentProposal, pid)
        if pr is None:
            return None
        pr.proposed_beschreibung = sug.beschreibung
        pr.proposed_examples_enthalten = sug.examples_enthalten
        pr.proposed_examples_nicht_enthalten = sug.examples_nicht_enthalten
        pr.konfidenz = sug.konfidenz
        pr.anmerkung = sug.anmerkung
        pr.status_llm = sug.status
        pr.diff_kurz = sug.diff_kurz
        pr.state = "pending"
        batch = session.get(EnrichmentBatch, pr.batch_id)
        if batch is not None and sug.cost_usd:
            batch.cost_usd = float(batch.cost_usd or 0) + float(sug.cost_usd or 0)
            batch.api_calls = int(batch.api_calls or 0) + 1
        session.commit()
        return _proposal_to_schema(pr)
