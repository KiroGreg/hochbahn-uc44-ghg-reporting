"""Excel + catalog helpers.

The pulled-in main branch moved Warengruppen catalog construction
into `_shared/catalog.py` (master Excel + LLM-enriched overlay merged
in-memory by variant). We expose thin wrappers so the API/services
don't have to deal with the underlying merge logic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from .model_loader import WarengruppenCatalog, load_warengruppen
from .paths import DATA_DIR

# Candidate EUR/amount columns in the invoice Excel, most-specific first.
# Shared by the dashboard aggregation and the per-row plausibility/prediction
# responses so the notion of "the amount column" stays in one place.
AMOUNT_COLUMNS = ("Wert/KWähr", "Nettobetrag", "Bruttobetrag", "Wert", "Betrag")


def clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [
        re.sub(r"\s+", " ", str(c).replace("\n", " ")).strip() for c in df.columns
    ]
    return df


def amount_column(df: pd.DataFrame) -> Optional[str]:
    """Return the first amount/EUR column present in the frame, or None."""
    for c in AMOUNT_COLUMNS:
        if c in df.columns:
            return c
    return None


def amount_series(df: pd.DataFrame) -> pd.Series:
    """Per-row numeric EUR amount (NaN where the column is missing or unparseable)."""
    col = amount_column(df)
    if col is None:
        return pd.Series(float("nan"), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def load_invoices(path: Path) -> pd.DataFrame:
    return clean_cols(pd.read_excel(path))


def build_catalog(catalog_cfg: dict) -> WarengruppenCatalog:
    """Build the catalog according to the variant in the model's config.yml."""
    return load_warengruppen(DATA_DIR, catalog_cfg)


def attach_catalog_to_invoices(
    invoices: pd.DataFrame, catalog: WarengruppenCatalog
) -> pd.DataFrame:
    """Merge catalog-derived columns (wg_name, wg_description, examples) into invoices.

    Mirrors plausibility_model/run.py: a left merge on `Warengruppe`. The
    extra columns become the inputs the plausibility prompt expects.

    `DataFrame.merge` resets the index to a fresh RangeIndex. For the full-frame
    path that happens to match the original RangeIndex, but when callers merge a
    *chunk* (e.g. the background orchestrator) the reset would relabel rows
    0..n-1 and break `row_index` alignment. Since the catalog is 1:1 on
    `Warengruppe` and the left merge preserves row order, we restore the
    original index so `row_index` stays the true positional index.
    """
    merged = invoices.merge(catalog.as_invoice_merge_frame(), on="Warengruppe", how="left")
    if len(merged) == len(invoices):
        merged.index = invoices.index
    return merged


def catalog_to_entries(catalog: WarengruppenCatalog) -> list[dict]:
    """Flatten the catalog for the JSON `/catalog` endpoint."""
    return [{"name": e.name, "description": e.description} for e in catalog.rows]
