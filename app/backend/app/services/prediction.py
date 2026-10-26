"""Service layer wrapping the existing PredictionModel.

The pulled-in main branch switched `prepare_catalog()` from a list of
dicts to a `WarengruppenCatalog`, and the prompt is now templated
against the variant chosen in `prediction_model/config.yml`
(`catalog: variant: ...`).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..core.data import amount_series
from ..core.model_loader import (
    PREDICTION_CONFIG_PATH,
    PredictionModel,
    WarengruppenCatalog,
    load_pred_config,
)
from ..core.paths import ENV_FILE
from . import warengruppen
from ..schemas.models import (
    PredictionRow,
    PredictionRunResponse,
    PredictionStats,
)

_model: Optional[PredictionModel] = None
_config: Optional[dict] = None
_catalog: Optional[WarengruppenCatalog] = None


def _ensure_model() -> tuple[PredictionModel, WarengruppenCatalog]:
    global _model, _config, _catalog
    if _model is None:
        _config = load_pred_config(PREDICTION_CONFIG_PATH)
        _model = PredictionModel(config=_config, env_path=ENV_FILE)
    if _catalog is None:
        assert _config is not None
        _catalog = warengruppen.to_catalog(_config["catalog"])
        _model.prepare_catalog(_catalog)
    return _model, _catalog


def get_config() -> dict:
    _ensure_model()
    assert _config is not None
    return _config


def get_model() -> PredictionModel:
    return _ensure_model()[0]


def get_catalog() -> WarengruppenCatalog:
    return _ensure_model()[1]


def run(
    implausible_df: pd.DataFrame,
    max_rows: Optional[int],
    hint_provider=None,
) -> PredictionRunResponse:
    model, _ = _ensure_model()

    workers = int(_config.get("concurrency", {}).get("workers", 1)) if _config else 1
    result = model.predict(
        implausible_df,
        max_rows=max_rows,
        workers=workers,
        progress=False,
        hint_provider=hint_provider,
    )

    processed = result[result["confidence"].notna()]

    amounts = amount_series(processed)
    bestell_col = model.columns.get("bestelltext")
    obj_col = model.columns.get("objektbezeichnung")

    def _s(val) -> str:
        if val is None or (not isinstance(val, str) and pd.isna(val)):
            return ""
        return str(val).strip()

    def _amount_at(idx) -> Optional[float]:
        val = amounts.get(idx)
        if val is None or pd.isna(val):
            return None
        return round(float(val), 2)

    rows: list[PredictionRow] = []
    regrouped_hm = 0
    low_conf = 0
    no_ef = 0  # Not derivable from the dim table alone — kept at 0 for now.

    for idx, row in processed.iterrows():
        suggested = row.get("predicted_warengruppe")
        suggested = None if pd.isna(suggested) else str(suggested)
        confidence = _s(row.get("confidence")) or "unknown"

        bestell = _s(row.get(bestell_col)) if bestell_col else ""
        objbz = _s(row.get(obj_col)) if obj_col else ""
        used_fallback = (not bestell) and bool(objbz)

        if suggested and confidence in {"hoch", "mittel"}:
            regrouped_hm += 1
        if confidence == "niedrig":
            low_conf += 1

        if bestell:
            label = bestell
        elif objbz:
            label = f"[Objektbez: {objbz}]"
        else:
            label = "—"
        rows.append(
            PredictionRow(
                row_index=int(idx),
                bestelltext=label,
                current_wg_name=(
                    _s(row.get("wg_name")) or _s(row.get("Warengruppe")) or None
                ),
                suggested_wg_name=suggested,
                betrag_eur=_amount_at(idx),
                confidence=confidence if confidence in {
                    "hoch", "mittel", "niedrig", "unknown", "error", "not_assessable",
                } else "unknown",
                reason=_s(row.get("reason")),
                objektbez_signal=used_fallback,
                ef_missing=False,
                decision=None,
            )
        )

    stats = PredictionStats(
        total=len(rows),
        regrouped_high_med=regrouped_hm,
        low_confidence=low_conf,
        no_ef=no_ef,
        confirmed=0,
    )
    return PredictionRunResponse(
        stats=stats,
        rows=rows,
        cost_usd=round(model.usage.cost_usd, 4),
        api_calls=model.usage.calls,
        cache_hits=model.usage.cache_hits,
    )
