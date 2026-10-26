"""Upload endpoint."""
from __future__ import annotations

import io

from fastapi import APIRouter, File, HTTPException, UploadFile

import logging

from ..core.data import clean_cols, load_invoices
from ..core.paths import DEFAULT_INVOICES
from ..core.state import get_state, reset
from ..schemas.models import UploadSummary
from ..services import persistence

import pandas as pd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])


# Columns the downstream pipeline absolutely needs. `Warengruppe` is the
# merge key against the dimension catalog; without it the plausibility
# run can't join and every other stage breaks. Validating at upload time
# means we return a clean 400 instead of a stack-trace-500 later.
REQUIRED_COLUMNS = ("Warengruppe", "Bestelltext")


def _summarize(df: pd.DataFrame, filename: str, source: str) -> UploadSummary:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Die Datei enthält keine Spalte(n) {', '.join(missing)}. "
                f"Pflichtspalten: {', '.join(REQUIRED_COLUMNS)}. "
                f"Vorhandene Spalten: {', '.join(str(c) for c in df.columns)}"
            ),
        )

    state = get_state()
    state.invoices = df
    state.invoices_filename = filename
    state.plausibility_df = None
    state.prediction_df = None
    state.user_decisions.clear()
    state.run_id = None

    # Write-through: persist the run + samples. Never let a DB hiccup break
    # the upload — the in-memory flow stays authoritative for the live session.
    try:
        state.run_id = persistence.create_run(df, filename=filename, source=source)
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist run for upload %s", filename)

    wg_count = int(df["Warengruppe"].nunique())
    return UploadSummary(
        filename=filename,
        row_count=int(len(df)),
        column_count=int(df.shape[1]),
        detected_columns=[str(c) for c in df.columns],
        warengruppe_count=wg_count,
    )


@router.post("/file", response_model=UploadSummary, summary="Upload an invoice Excel file")
async def upload_file(file: UploadFile = File(...)) -> UploadSummary:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx / .xls files are supported.")
    raw = await file.read()
    try:
        df = clean_cols(pd.read_excel(io.BytesIO(raw)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Excel parse error: {exc}") from exc
    return _summarize(df, file.filename, source="upload")


@router.post(
    "/sample",
    response_model=UploadSummary,
    summary="Load the bundled HHA sample invoice file (5000 rows).",
)
def load_sample() -> UploadSummary:
    if not DEFAULT_INVOICES.exists():
        raise HTTPException(status_code=404, detail=f"Sample not found at {DEFAULT_INVOICES}")
    df = load_invoices(DEFAULT_INVOICES)
    return _summarize(df, DEFAULT_INVOICES.name, source="sample")


@router.post("/reset", summary="Drop the in-memory session state.")
def reset_session() -> dict:
    reset()
    return {"ok": True}
