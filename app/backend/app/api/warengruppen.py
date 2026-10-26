"""Warengruppen catalog CRUD endpoints.

Master data for the Warengruppen catalog (name, description, inclusive/exclusive
examples) plus per-year emission factors — the DB-backed replacement for the dim
Excel files. Mutations invalidate the cached prompt catalog (handled in the
service) so the prediction/plausibility models and the dashboard pick up edits.
"""
from __future__ import annotations

import io
import logging

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..core.data import clean_cols
from ..schemas.models import (
    BulkActiveRequest,
    BulkActiveResult,
    BulkDeleteRequest,
    BulkDeleteResult,
    ImportResult,
    WarengruppeRow,
    WarengruppeUpsertRequest,
)
from ..services import warengruppen as svc

router = APIRouter(prefix="/api/warengruppen", tags=["warengruppen"])

logger = logging.getLogger(__name__)


@router.get("", response_model=list[WarengruppeRow], summary="List all Warengruppen.")
def list_warengruppen() -> list[WarengruppeRow]:
    return svc.list_all()


@router.get(
    "/{wg_id}",
    response_model=WarengruppeRow,
    summary="Get a single Warengruppe by its wg_id.",
)
def get_warengruppe(wg_id: str) -> WarengruppeRow:
    row = svc.get(wg_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Warengruppe '{wg_id}' nicht gefunden.")
    return row


@router.post(
    "",
    response_model=WarengruppeRow,
    status_code=201,
    summary="Create a Warengruppe (generates a wg_id if none is given).",
)
def create_warengruppe(payload: WarengruppeUpsertRequest) -> WarengruppeRow:
    try:
        return svc.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.put(
    "/{wg_id}",
    response_model=WarengruppeRow,
    summary="Update a Warengruppe (wg_id is immutable).",
)
def update_warengruppe(wg_id: str, payload: WarengruppeUpsertRequest) -> WarengruppeRow:
    row = svc.update(wg_id, payload)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Warengruppe '{wg_id}' nicht gefunden.")
    return row


@router.delete(
    "/{wg_id}",
    summary="Delete a Warengruppe and its emission factors (blocked if referenced).",
)
def delete_warengruppe(wg_id: str) -> dict:
    try:
        deleted = svc.delete(wg_id)
    except svc.WarengruppeReferencedError as exc:
        # Historical pairing exists — refuse the hard delete, steer to deactivate.
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Warengruppe '{wg_id}' nicht gefunden.")
    return {"ok": True}


@router.post(
    "/bulk-delete",
    response_model=BulkDeleteResult,
    summary="Delete several Warengruppen at once by their wg_ids (skips referenced).",
)
def bulk_delete_warengruppen(payload: BulkDeleteRequest) -> BulkDeleteResult:
    return svc.bulk_delete(payload.wg_ids)


@router.post(
    "/{wg_id}/deactivate",
    response_model=WarengruppeRow,
    summary="Deactivate a Warengruppe (hidden from the LLM, kept for history).",
)
def deactivate_warengruppe(wg_id: str) -> WarengruppeRow:
    row = svc.set_active(wg_id, aktiv=False)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Warengruppe '{wg_id}' nicht gefunden.")
    return row


@router.post(
    "/{wg_id}/activate",
    response_model=WarengruppeRow,
    summary="Re-activate a Warengruppe (offered to the LLM again).",
)
def activate_warengruppe(wg_id: str) -> WarengruppeRow:
    row = svc.set_active(wg_id, aktiv=True)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Warengruppe '{wg_id}' nicht gefunden.")
    return row


@router.post(
    "/bulk-set-active",
    response_model=BulkActiveResult,
    summary="Activate or deactivate several Warengruppen at once by their wg_ids.",
)
def bulk_set_active_warengruppen(payload: BulkActiveRequest) -> BulkActiveResult:
    return svc.bulk_set_active(payload.wg_ids, aktiv=payload.aktiv)


@router.post(
    "/import",
    response_model=ImportResult,
    summary="Bulk-import Warengruppen from an XLSX/CSV upload (upsert by wg_id).",
)
async def import_warengruppen(file: UploadFile = File(...)) -> ImportResult:
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(
            status_code=400, detail="Nur .xlsx / .xls / .csv Dateien werden unterstützt."
        )
    raw = await file.read()
    try:
        if name.endswith(".csv"):
            # sep=None lets the python engine sniff the separator (',' vs ';').
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Datei konnte nicht gelesen werden: {exc}") from exc

    df = clean_cols(df)
    if "wg_name" not in {str(c).strip().lower() for c in df.columns} \
            and "name" not in {str(c).strip().lower() for c in df.columns}:
        raise HTTPException(
            status_code=400,
            detail="Pflichtspalte 'wg_name' (oder 'name') fehlt in der Datei.",
        )
    return svc.import_rows(df)
