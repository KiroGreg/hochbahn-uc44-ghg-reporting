"""Canonical feature representation of an invoice row.

The correction-memory keys on a deterministic, embedding-friendly string built
from **exactly the fields the prediction model sees** — no price, no date, not
the current Warengruppe (those are intentionally excluded from the classifier
payload, see prediction_model/config.yml + model.py::_extract). Keeping this in
sync with the model's `_extract` guarantees the memory keys on the same
information the model actually reasons over.
"""
from __future__ import annotations

from typing import Optional

# Mirrors prediction_model/config.yml -> input_columns (alias -> Excel column).
INPUT_COLUMNS = {
    "bestelltext": "Bestelltext",
    "bezeichnung": "Bezeichnung",
    "objektbezeichnung": "Objektbezeichnung",
    "zusatz_1": "Bezeichnung.1",
    "zusatz_2": "Bezeichnung.2",
    "menge": "Menge erfaßt gesamt",
    "einheit": "GebuchteMengeneinh",
}


def _s(raw: dict, alias: str) -> str:
    """Mirror model.py::_extract: missing/NaN/empty -> '-', else stripped str."""
    col = INPUT_COLUMNS.get(alias)
    if col is None:
        return "-"
    val = raw.get(col)
    if val is None:
        return "-"
    # JSON-safe raw already turned NaN into None, but guard floats just in case.
    if isinstance(val, float) and val != val:  # NaN
        return "-"
    return str(val).strip() or "-"


def build_feature_payload(raw: Optional[dict]) -> dict:
    """Build the per-row payload exactly as the model would from `sample.raw`."""
    raw = raw or {}
    zusatz = " | ".join(
        v for v in (_s(raw, "zusatz_1"), _s(raw, "zusatz_2")) if v != "-"
    ) or "-"
    return {
        "bestelltext": _s(raw, "bestelltext"),
        "bezeichnung": _s(raw, "bezeichnung"),
        "objektbezeichnung": _s(raw, "objektbezeichnung"),
        "zusatz": zusatz,
        "menge": _s(raw, "menge"),
        "einheit": _s(raw, "einheit"),
    }


# Stable domain framing so the embedding model reads the terse, abbreviation-heavy
# fields in the right context (procurement invoice lines of a public transport
# operator). The prefix is constant across items, so it cancels out in cosine
# ranking — its job is to anchor the *interpretation*, not to distinguish rows.
_FRAMING = (
    "Beschaffungs-Rechnungsposition eines öffentlichen Nahverkehrsunternehmens "
    "(Hamburger Hochbahn)."
)


def feature_key(payload: dict) -> str:
    """Deterministic, embedding-friendly text.

    A coherent description rather than a bare key:value dump: domain framing +
    only the *present* fields woven in as clauses (missing fields are omitted,
    not rendered as '-', to avoid noise). `Bezeichnung` is dropped when it just
    duplicates `Bestelltext` (common in the data).
    """
    bestell = payload["bestelltext"]
    obj = payload["objektbezeichnung"]
    bez = payload["bezeichnung"]
    zus = payload["zusatz"]
    menge = payload["menge"]
    einheit = payload["einheit"]

    parts = [_FRAMING]
    parts.append(f"Bestelltext: {bestell}." if bestell != "-" else "Ohne Bestelltext.")
    if obj != "-":
        parts.append(f"Objektbezeichnung: {obj}.")
    if bez != "-" and bez != bestell:
        parts.append(f"Bezeichnung: {bez}.")
    if zus != "-":
        parts.append(f"Weitere Angaben: {zus}.")
    if menge != "-":
        unit = "" if einheit == "-" else f" {einheit}"
        parts.append(f"Bestellmenge: {menge}{unit}.")
    return " ".join(parts)


def feature_key_from_raw(raw: Optional[dict]) -> str:
    return feature_key(build_feature_payload(raw))
