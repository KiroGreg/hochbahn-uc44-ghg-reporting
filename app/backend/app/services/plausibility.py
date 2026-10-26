"""Service layer wrapping the existing PlausibilityModel.

After the main-branch pull the model:
- Returns a `plausibilitaet: str` enum (was `plausible: bool`).
- Adds `unterstuetzende_signale`, `widersprechende_signale` columns.
- Requires a `WarengruppenCatalog` via `prepare_catalog()` before any
  call (the system prompt is templated against the catalog).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..core.data import amount_series, attach_catalog_to_invoices
from ..core.model_loader import (
    PLAUSIBILITY_CONFIG_PATH,
    PlausibilityModel,
    WarengruppenCatalog,
    load_plaus_config,
)
from ..core.paths import ENV_FILE
from . import warengruppen
from ..schemas.models import (
    PlausibilityRow,
    PlausibilityRunResponse,
    PlausibilityStats,
)

_model: Optional[PlausibilityModel] = None
_config: Optional[dict] = None
_catalog: Optional[WarengruppenCatalog] = None


def _ensure_model() -> tuple[PlausibilityModel, WarengruppenCatalog]:
    global _model, _config, _catalog
    if _model is None:
        _config = load_plaus_config(PLAUSIBILITY_CONFIG_PATH)
        _model = PlausibilityModel(config=_config, env_path=ENV_FILE)
    if _catalog is None:
        assert _config is not None
        _catalog = warengruppen.to_catalog(_config["catalog"])
        _model.prepare_catalog(_catalog)
    return _model, _catalog


def get_config() -> dict:
    _ensure_model()
    assert _config is not None
    return _config


def get_model() -> PlausibilityModel:
    return _ensure_model()[0]


def get_catalog() -> WarengruppenCatalog:
    return _ensure_model()[1]


def _coerce_signals(value) -> list[str]:
    """Model joins signals with ' | ' before writing to the dataframe."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return []
    s = str(value).strip()
    if not s:
        return []
    return [p.strip() for p in s.split("|") if p.strip()]


def _amount_at(amounts: pd.Series, idx) -> Optional[float]:
    """Look up the row's EUR amount, returning None where it is missing/NaN."""
    val = amounts.get(idx)
    if val is None or pd.isna(val):
        return None
    return round(float(val), 2)


def run(invoices: pd.DataFrame, max_rows: Optional[int]) -> PlausibilityRunResponse:
    model, catalog = _ensure_model()
    enriched = attach_catalog_to_invoices(invoices, catalog)

    workers = int(_config.get("concurrency", {}).get("workers", 1)) if _config else 1
    result = model.predict(enriched, max_rows=max_rows, workers=workers, progress=False)

    # `model.predict` keeps the full dataframe but only fills the first
    # `max_rows` rows. Restrict the response to actually-processed rows.
    processed = result[
        result["plausibilitaet"].notna() | result["confidence"].notna()
    ]

    amounts = amount_series(processed)
    bestelltext_col = model.columns.get("bestelltext")
    obj_col = model.columns.get("objektbezeichnung")

    def _s(val) -> str:
        if val is None or (not isinstance(val, str) and pd.isna(val)):
            return ""
        return str(val).strip()

    rows: list[PlausibilityRow] = []
    plausible = implausible = unklar = not_assessable = low_conf = obj_fallback = 0

    for idx, row in processed.iterrows():
        plaus_raw = _s(row.get("plausibilitaet")) or None
        confidence = _s(row.get("confidence")) or "unknown"

        bestell = _s(row.get(bestelltext_col)) if bestelltext_col else ""
        objbz = _s(row.get(obj_col)) if obj_col else ""
        used_fallback = (not bestell) and bool(objbz)

        if plaus_raw == "plausibel":
            plausible += 1
        elif plaus_raw == "implausibel":
            implausible += 1
        elif plaus_raw == "unklar":
            unklar += 1
        if confidence == "not_assessable":
            not_assessable += 1
        if confidence == "niedrig":
            low_conf += 1
        if used_fallback:
            obj_fallback += 1

        rows.append(
            PlausibilityRow(
                row_index=int(idx),
                bestelltext=bestell or "[kein Bestelltext]",
                objektbezeichnung=objbz,
                wg_id=_s(row.get("Warengruppe")) or None,
                wg_name=_s(row.get("wg_name")) or None,
                kostenart=_s(row.get("Kostenartenbezeichn.")) or None,
                betrag_eur=_amount_at(amounts, idx),
                plausibilitaet=plaus_raw if plaus_raw in {
                    "plausibel", "implausibel", "unklar"
                } else None,
                confidence=confidence if confidence in {
                    "hoch", "mittel", "niedrig", "unknown", "error", "not_assessable",
                } else "unknown",
                unterstuetzende_signale=_coerce_signals(
                    row.get("unterstuetzende_signale")
                ),
                widersprechende_signale=_coerce_signals(
                    row.get("widersprechende_signale")
                ),
                reason=_s(row.get("reason")),
                decision=None,
            )
        )

    stats = PlausibilityStats(
        total=len(rows),
        plausible=plausible,
        implausible=implausible,
        unklar=unklar,
        not_assessable=not_assessable,
        low_confidence=low_conf,
        objektbez_fallback=obj_fallback,
    )
    return PlausibilityRunResponse(
        stats=stats,
        rows=rows,
        cost_usd=round(model.usage.cost_usd, 4),
        api_calls=model.usage.calls,
        cache_hits=model.usage.cache_hits,
    )
