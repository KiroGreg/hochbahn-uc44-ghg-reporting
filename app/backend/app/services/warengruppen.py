"""Warengruppen catalog — CRUD service and DB-backed catalog source.

This service replaces the three source Excel files as the *live* origin of the
Warengruppen catalog for the web app:

* CRUD (`list_all`/`get`/`create`/`update`/`delete`) over the `warengruppe` +
  `emissionsfaktor` tables.
* `to_catalog()` rebuilds the in-memory `WarengruppenCatalog`/`CatalogEntry`
  objects the prediction/plausibility models already consume — so swapping the
  source from Excel to DB leaves all downstream prompt logic untouched.
* `ef_lookup()` returns the {wg_id -> emission factor} map the dashboard uses.
* `seed_from_excel()` does the one-time import (overlay + EF Excel → DB), driven
  by `scripts/seed_warengruppen.py`. The standalone CLI models keep reading Excel.

Until the table is seeded the catalog/EF helpers transparently **fall back to
the source Excel**, so the app keeps working out-of-the-box; once seeded the DB
is authoritative.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from sqlalchemy import func, or_

from ..core.data import clean_cols
from ..core.db import SessionLocal
from ..core.paths import DATA_DIR
# Importing model_loader first puts `Use Case/models/` on sys.path and pulls in
# the shared catalog module, so the private-helper import below resolves.
from ..core.model_loader import WarengruppenCatalog
from _shared.catalog import (  # noqa: E402
    VALID_VARIANTS,
    CatalogEntry,
    _is_blank,
    _split_bullets,
)
from ..models.orm import (
    CorrectionMemory,
    DecisionEvent,
    Emissionsfaktor,
    Sample,
    Warengruppe,
)
from ..schemas.models import (
    BulkActiveResult,
    BulkDeleteResult,
    EmissionsfaktorRow,
    HistoryItem,
    HistorySignal,
    ImportResult,
    WarengruppeRow,
    WarengruppeUpsertRequest,
)

logger = logging.getLogger(__name__)

# Seed sources (subset of the three dim Excel files; master is not needed).
OVERLAY_FILE = "dimWarengruppen_enriched_overlay.xlsx"
EF_FILE = "fak_Emissionsfaktoren_Warengruppen_spend-based_hashed.xlsx"


# --- helpers ----------------------------------------------------------------

def _str(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _dedup_ef(efs: list[EmissionsfaktorRow]) -> list[EmissionsfaktorRow]:
    """Collapse duplicate years (last wins) to respect the unique constraint."""
    by_year: dict[int, float] = {}
    for e in efs:
        by_year[int(e.jahr)] = float(e.wert)
    return [EmissionsfaktorRow(jahr=y, wert=w) for y, w in sorted(by_year.items())]


# Default delimiter for the list cells in a bulk import (chosen because it does
# not clash with the CSV column separator `,`/`;`).
IMPORT_LIST_SEP = "|"

# Canonical import field -> accepted (normalised, lower-cased) column headers.
# Order in the file is irrelevant; columns are matched by name via these aliases.
_IMPORT_ALIASES: dict[str, tuple[str, ...]] = {
    "wg_id": ("wg_id",),
    "wg_name": ("wg_name", "name"),
    "beschreibung": ("beschreibung",),
    "beispiele_enthalten": ("beispiele_enthalten",),
    "beispiele_nicht_enthalten": ("beispiele_nicht_enthalten",),
}


def _split_delimited(value, sep: str = IMPORT_LIST_SEP) -> list[str]:
    """Split one import cell into a list at `sep`; trim items, drop blanks."""
    if _is_blank(value):
        return []
    return [part.strip() for part in str(value).split(sep) if part.strip()]


def _num(value) -> Optional[float]:
    """Parse a number, tolerating a German decimal comma; None if not numeric."""
    if _is_blank(value):
        return None
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    if s.count(",") == 1 and "." not in s:  # e.g. "0,1234"
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return None
    return None


def _build_colmap(columns) -> dict[str, object]:
    """Map each canonical import field to the actual column label present.

    Matching is case-insensitive over the (already whitespace-normalised by
    `clean_cols`) headers, so the column order in the file does not matter.
    """
    lookup = {str(c).strip().lower(): c for c in columns}
    out: dict[str, object] = {}
    for field, aliases in _IMPORT_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                out[field] = lookup[alias]
                break
    return out


def _to_row(wg: Warengruppe) -> WarengruppeRow:
    return WarengruppeRow(
        id=str(wg.id),
        wg_id=wg.wg_id,
        wg_name=wg.wg_name,
        beschreibung=wg.beschreibung,
        examples_enthalten=list(wg.examples_enthalten or []),
        examples_nicht_enthalten=list(wg.examples_nicht_enthalten or []),
        emissionsfaktoren=[
            EmissionsfaktorRow(jahr=int(e.jahr), wert=float(e.wert))
            for e in sorted(wg.emissionsfaktoren, key=lambda e: e.jahr)
        ],
        aktiv=bool(wg.aktiv),
        created_at=wg.created_at,
        updated_at=wg.updated_at,
    )


# --- CRUD -------------------------------------------------------------------

def list_all() -> list[WarengruppeRow]:
    with SessionLocal() as session:
        wgs = session.query(Warengruppe).order_by(Warengruppe.wg_name).all()
        return [_to_row(w) for w in wgs]


def get(wg_id: str) -> Optional[WarengruppeRow]:
    with SessionLocal() as session:
        wg = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id == wg_id)
            .one_or_none()
        )
        return _to_row(wg) if wg is not None else None


def create(payload: WarengruppeUpsertRequest) -> WarengruppeRow:
    with SessionLocal() as session:
        wg_id = (payload.wg_id or "").strip() or f"new-{uuid.uuid4()}"
        existing = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id == wg_id)
            .one_or_none()
        )
        if existing is not None:
            raise ValueError(f"Warengruppe '{wg_id}' existiert bereits.")
        wg = Warengruppe(
            wg_id=wg_id,
            wg_name=payload.wg_name.strip(),
            beschreibung=(payload.beschreibung or None),
            examples_enthalten=list(payload.examples_enthalten or []),
            examples_nicht_enthalten=list(payload.examples_nicht_enthalten or []),
        )
        for e in _dedup_ef(payload.emissionsfaktoren):
            wg.emissionsfaktoren.append(Emissionsfaktor(jahr=e.jahr, wert=e.wert))
        session.add(wg)
        session.commit()
        row = _to_row(wg)
    invalidate_catalog_caches()
    return row


def update(wg_id: str, payload: WarengruppeUpsertRequest) -> Optional[WarengruppeRow]:
    with SessionLocal() as session:
        wg = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id == wg_id)
            .one_or_none()
        )
        if wg is None:
            return None
        # wg_id is the immutable business key (referenced by invoices); ignore
        # any wg_id in the payload.
        wg.wg_name = payload.wg_name.strip()
        wg.beschreibung = payload.beschreibung or None
        wg.examples_enthalten = list(payload.examples_enthalten or [])
        wg.examples_nicht_enthalten = list(payload.examples_nicht_enthalten or [])
        wg.emissionsfaktoren.clear()
        session.flush()
        for e in _dedup_ef(payload.emissionsfaktoren):
            wg.emissionsfaktoren.append(Emissionsfaktor(jahr=e.jahr, wert=e.wert))
        session.commit()
        row = _to_row(wg)
    invalidate_catalog_caches()
    return row


# --- delete protection: the historical-reference seam -----------------------
#
# Warengruppen are referenced across the app by *value* (their wg_id or wg_name),
# not by a foreign key. A hard delete would silently break the audit trail, so it
# is refused while any such value reference exists and the user is steered to
# deactivation instead. All value-match specifics live in `historical_references`
# below — the single place the planned FK migration has to touch.
# See TODOS.md → 'FK-Migrationspfad'.


@dataclass(frozen=True)
class WgReferences:
    """How often a Warengruppe's wg_id/wg_name still appears in historical data.

    NOTE (technical debt / FK migration path): references are stored as string
    VALUES (wg_id OR wg_name), not foreign keys. `historical_references` is the
    single place that computes this by value-matching. When the schema gains real
    FKs to `warengruppe.id`, replace ONLY the query bodies there with FK counts —
    the callers (`delete`/`bulk_delete`) and this shape stay unchanged.
    """

    sample_original: int
    decision_event: int
    correction_memory: int

    @property
    def total(self) -> int:
        return self.sample_original + self.decision_event + self.correction_memory

    @property
    def is_referenced(self) -> bool:
        return self.total > 0


class WarengruppeReferencedError(Exception):
    """Raised when a hard delete is refused because historical pairing exists.

    The router maps this to HTTP 409. The message is user-facing (German).
    """

    def __init__(self, wg_id: str, refs: WgReferences) -> None:
        self.wg_id = wg_id
        self.refs = refs
        super().__init__(
            f"Warengruppe '{wg_id}' kann nicht gelöscht werden — sie ist in "
            f"{refs.total} historischen Einträgen referenziert (Uploads: "
            f"{refs.sample_original}, Entscheidungen: {refs.decision_event}, "
            f"Lerngedächtnis: {refs.correction_memory}). Bitte stattdessen "
            "deaktivieren."
        )


def historical_references(session, wg_id: str, wg_name: str) -> WgReferences:
    """Count value-references to a Warengruppe across the historical tables.

    Matches against BOTH the wg_id and the wg_name, because the value columns
    hold a mix of the two depending on where they were written:

    * ``sample.wg_id_original``                     — original upload
    * ``decision_event.old_value`` / ``new_value``  — manual remap audit trail
    * ``correction_memory.predicted_wg`` / ``corrected_wg`` — learning memory

    ``prediction_result`` is intentionally NOT counted: an unconfirmed model
    suggestion is not a historical pairing.

    This is the FK-migration seam (see `WgReferences`): swap the value-`in_`
    filters below for FK-based counts once real foreign keys exist.
    """
    keys = [k for k in {wg_id, wg_name} if k]  # de-dupe, drop empties
    if not keys:
        return WgReferences(0, 0, 0)

    sample_n = (
        session.query(func.count(Sample.id))
        .filter(Sample.wg_id_original.in_(keys))
        .scalar()
    ) or 0
    decision_n = (
        session.query(func.count(DecisionEvent.id))
        .filter(
            or_(
                DecisionEvent.old_value.in_(keys),
                DecisionEvent.new_value.in_(keys),
            )
        )
        .scalar()
    ) or 0
    memory_n = (
        session.query(func.count(CorrectionMemory.id))
        .filter(
            or_(
                CorrectionMemory.predicted_wg.in_(keys),
                CorrectionMemory.corrected_wg.in_(keys),
            )
        )
        .scalar()
    ) or 0
    return WgReferences(sample_n, decision_n, memory_n)


def delete(wg_id: str) -> bool:
    """Hard-delete a Warengruppe (and its emission factors) if unreferenced.

    Returns False when the id is unknown. Raises `WarengruppeReferencedError`
    when historical pairing exists — the caller maps that to HTTP 409 and the
    user is steered to deactivation instead.
    """
    with SessionLocal() as session:
        wg = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id == wg_id)
            .one_or_none()
        )
        if wg is None:
            return False
        refs = historical_references(session, wg.wg_id, wg.wg_name)
        if refs.is_referenced:
            raise WarengruppeReferencedError(wg.wg_id, refs)
        session.delete(wg)
        session.commit()
    invalidate_catalog_caches()
    return True


def bulk_delete(wg_ids: list[str]) -> BulkDeleteResult:
    """Delete several Warengruppen by wg_id in one transaction.

    Emission factors go with them via the cascade. Unknown ids are reported in
    `not_found`; ids still referenced by historical data are kept and reported in
    `blocked` (deactivate those instead) rather than failing the whole call. The
    catalog cache is reset exactly once.
    """
    seen: set[str] = set()
    wanted: list[str] = []
    for x in wg_ids:
        w = str(x).strip()
        if w and w not in seen:
            seen.add(w)
            wanted.append(w)
    if not wanted:
        return BulkDeleteResult(deleted=0, not_found=[], blocked=[])

    with SessionLocal() as session:
        found = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id.in_(wanted))
            .all()
        )
        found_ids = {str(wg.wg_id) for wg in found}
        blocked: list[str] = []
        deleted = 0
        for wg in found:
            if historical_references(session, wg.wg_id, wg.wg_name).is_referenced:
                blocked.append(str(wg.wg_id))
                continue
            session.delete(wg)
            deleted += 1
        session.commit()

    not_found = [w for w in wanted if w not in found_ids]
    invalidate_catalog_caches()
    return BulkDeleteResult(deleted=deleted, not_found=not_found, blocked=blocked)


# --- activate / deactivate (soft delete) ------------------------------------

def set_active(wg_id: str, aktiv: bool) -> Optional[WarengruppeRow]:
    """Flip a single Warengruppe's active flag; None if the id is unknown.

    Deactivating drops it from the prompt catalog (`to_catalog` filters on
    `aktiv`) so the LLM stops suggesting it; `ef_lookup` keeps it for historical
    emission calculation. `invalidate_catalog_caches` makes the change effective
    for the next model run immediately.
    """
    with SessionLocal() as session:
        wg = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id == wg_id)
            .one_or_none()
        )
        if wg is None:
            return None
        wg.aktiv = bool(aktiv)
        session.commit()
        row = _to_row(wg)
    invalidate_catalog_caches()
    return row


def bulk_set_active(wg_ids: list[str], aktiv: bool) -> BulkActiveResult:
    """Activate/deactivate several Warengruppen at once; cache reset once.

    Unknown ids are reported in `not_found` rather than failing the whole call.
    """
    seen: set[str] = set()
    wanted: list[str] = []
    for x in wg_ids:
        w = str(x).strip()
        if w and w not in seen:
            seen.add(w)
            wanted.append(w)
    if not wanted:
        return BulkActiveResult(updated=0, not_found=[])

    with SessionLocal() as session:
        found = (
            session.query(Warengruppe)
            .filter(Warengruppe.wg_id.in_(wanted))
            .all()
        )
        found_ids = {str(wg.wg_id) for wg in found}
        for wg in found:
            wg.aktiv = bool(aktiv)
        session.commit()

    not_found = [w for w in wanted if w not in found_ids]
    invalidate_catalog_caches()
    return BulkActiveResult(updated=len(found_ids), not_found=not_found)


# --- enrichment history signal ----------------------------------------------
#
# Aggregates the *manual* remap flows for a Warengruppe as an enrichment hint —
# complementary to "learn from history" (which retrieves single past cases at
# inference time). Here we only READ decision_event/sample by value (the same
# value-match seam as historical_references) and generalise the pattern:
#
#   influx  (decision_event.new_value == WG) → its description/examples_enthalten
#           miss these cases → broaden them.
#   outflux (decision_event.old_value == WG) → the model over-included → sharpen
#           examples_nicht_enthalten / the scope boundary.
#
# Only manual remaps count (decision in 'regroup'/'new_wg'); 'ok'/'reject' are
# not flows. This never writes to the memory tables, so learn-from-history is
# untouched.

_REMAP_DECISIONS = ("regroup", "new_wg")


def _flux_count(session, keys: list[str], column) -> int:
    return int(
        session.query(func.count(DecisionEvent.id))
        .filter(column.in_(keys), DecisionEvent.decision.in_(_REMAP_DECISIONS))
        .scalar()
        or 0
    )


def _flux_items(session, keys: list[str], column, top_k: int) -> list[HistoryItem]:
    rows = (
        session.query(
            Sample.bestelltext,
            func.count(DecisionEvent.id),
            func.coalesce(func.sum(Sample.betrag_eur), 0),
        )
        .join(DecisionEvent, DecisionEvent.sample_id == Sample.id)
        .filter(
            column.in_(keys),
            DecisionEvent.decision.in_(_REMAP_DECISIONS),
            Sample.bestelltext.isnot(None),
        )
        .group_by(Sample.bestelltext)
        .order_by(func.count(DecisionEvent.id).desc())
        .limit(top_k)
        .all()
    )
    out: list[HistoryItem] = []
    for text_val, n, b in rows:
        text = str(text_val).strip()
        if text:
            out.append(HistoryItem(text=text, count=int(n), betrag_eur=float(b or 0)))
    return out


def history_signal(wg_id: str, wg_name: Optional[str] = None, top_k: int = 10) -> HistorySignal:
    """Manual in-/out-flux for one Warengruppe (counts + top Bestelltexte).

    Matches by value against BOTH wg_id and wg_name (the value columns hold a
    mix), mirroring `historical_references`. `wg_name` is resolved from the DB
    when omitted.
    """
    with SessionLocal() as session:
        if wg_name is None:
            wg = (
                session.query(Warengruppe)
                .filter(Warengruppe.wg_id == wg_id)
                .one_or_none()
            )
            wg_name = wg.wg_name if wg is not None else None
        keys = [k for k in {wg_id, wg_name} if k]
        if not keys:
            return HistorySignal(wg_id=wg_id or "")
        return HistorySignal(
            wg_id=wg_id,
            influx_count=_flux_count(session, keys, DecisionEvent.new_value),
            outflux_count=_flux_count(session, keys, DecisionEvent.old_value),
            top_influx=_flux_items(session, keys, DecisionEvent.new_value, top_k),
            top_outflux=_flux_items(session, keys, DecisionEvent.old_value, top_k),
        )


def history_signals_all() -> dict[str, dict[str, int]]:
    """{wg_id -> {'influx': n, 'outflux': m}} for the whole catalog in two queries.

    Powers the wizard's selection badges. Manual-remap values are grouped once
    each, then folded back to their Warengruppe by value-matching (a value equals
    a wg_id OR a wg_name), so this stays two GROUP BYs plus a Python fold.
    """
    with SessionLocal() as session:
        wgs = session.query(Warengruppe.wg_id, Warengruppe.wg_name).all()
        val_to_id: dict[str, str] = {}
        out: dict[str, dict[str, int]] = {}
        for wid, wname in wgs:
            wid = str(wid)
            out[wid] = {"influx": 0, "outflux": 0}
            val_to_id[wid] = wid
            if wname:
                val_to_id.setdefault(str(wname).strip(), wid)

        def _fold(column, bucket: str) -> None:
            rows = (
                session.query(column, func.count(DecisionEvent.id))
                .filter(DecisionEvent.decision.in_(_REMAP_DECISIONS), column.isnot(None))
                .group_by(column)
                .all()
            )
            for val, n in rows:
                wid = val_to_id.get(str(val).strip())
                if wid:
                    out[wid][bucket] += int(n)

        _fold(DecisionEvent.new_value, "influx")
        _fold(DecisionEvent.old_value, "outflux")
        return out


def _ef_year_from_header(c) -> Optional[int]:
    """Emissionsfaktor-Jahr aus einem Spalten-Header 'e_<jahr>' (case-insensitiv), sonst None."""
    s = str(c).strip()
    if s[:2].lower() == "e_" and s[2:].isdigit():
        return int(s[2:])
    return None


def import_rows(df: pd.DataFrame) -> ImportResult:
    """Upsert Warengruppen from a parsed import sheet (column order agnostic).

    Columns are matched by name (see `_IMPORT_ALIASES`), so their order in the
    file does not matter. List fields use the pipe delimiter; a column header of
    the form `e_<jahr>` (e.g. `e_2024`) is read as an emission-factor year. Rows
    are upserted by wg_id: an existing id is updated, a given-but-new id is
    created with exactly that id, and an empty id yields a generated one
    ('new-<uuid>'). `wg_name` is required. Existing rows not mentioned in the
    file are left untouched. The catalog cache is reset once at the end.
    """
    colmap = _build_colmap(df.columns)
    year_cols = [c for c in df.columns if _ef_year_from_header(c) is not None]
    result = ImportResult()

    def _cell(row, field: str) -> str:
        col = colmap.get(field)
        return _str(row.get(col)) if col is not None else ""

    with SessionLocal() as session:
        for pos, (_, r) in enumerate(df.iterrows(), start=2):  # row 1 is the header
            name = _cell(r, "wg_name")
            if not name:
                # Skip fully blank rows silently; flag rows that carry data but no name.
                if any(_str(r.get(c)) for c in df.columns):
                    result.errors.append(f"Zeile {pos}: 'wg_name' fehlt — übersprungen.")
                    result.skipped += 1
                continue

            wg_id = _cell(r, "wg_id")
            beschreibung = _cell(r, "beschreibung") or None
            ex_in = _split_delimited(r.get(colmap["beispiele_enthalten"])) \
                if "beispiele_enthalten" in colmap else []
            ex_ex = _split_delimited(r.get(colmap["beispiele_nicht_enthalten"])) \
                if "beispiele_nicht_enthalten" in colmap else []

            efs: list[EmissionsfaktorRow] = []
            for c in year_cols:
                v = r.get(c)
                if _is_blank(v):
                    continue
                w = _num(v)
                if w is None:
                    result.errors.append(
                        f"Zeile {pos}: Emissionsfaktor '{c}' ist keine Zahl — ignoriert."
                    )
                    continue
                efs.append(EmissionsfaktorRow(jahr=_ef_year_from_header(c), wert=w))
            efs = _dedup_ef(efs)

            existing = None
            if wg_id:
                existing = (
                    session.query(Warengruppe)
                    .filter(Warengruppe.wg_id == wg_id)
                    .one_or_none()
                )

            if existing is not None:
                existing.wg_name = name
                existing.beschreibung = beschreibung
                existing.examples_enthalten = ex_in
                existing.examples_nicht_enthalten = ex_ex
                existing.emissionsfaktoren.clear()
                session.flush()
                for e in efs:
                    existing.emissionsfaktoren.append(Emissionsfaktor(jahr=e.jahr, wert=e.wert))
                result.updated += 1
            else:
                wg = Warengruppe(
                    wg_id=wg_id or f"new-{uuid.uuid4()}",
                    wg_name=name,
                    beschreibung=beschreibung,
                    examples_enthalten=ex_in,
                    examples_nicht_enthalten=ex_ex,
                )
                for e in efs:
                    wg.emissionsfaktoren.append(Emissionsfaktor(jahr=e.jahr, wert=e.wert))
                session.add(wg)
                result.created += 1
        session.commit()

    invalidate_catalog_caches()
    return result


# --- catalog source (consumed by prediction/plausibility) -------------------

def to_catalog(catalog_cfg: dict) -> WarengruppenCatalog:
    """Rebuild the in-memory catalog from the DB, honouring the variant config.

    The variant (from a model's config.yml) controls only whether the
    inclusive/exclusive examples are fed to the LLM — exactly as the Excel
    loader does. Falls back to the Excel catalog while the table is unseeded.
    """
    variant = catalog_cfg.get("variant")
    if variant not in VALID_VARIANTS:
        raise ValueError(
            f"catalog.variant must be one of {VALID_VARIANTS}, got {variant!r}."
        )
    include_in = variant in ("overlay_inclusive", "overlay_full")
    include_ex = variant == "overlay_full"

    with SessionLocal() as session:
        total = session.query(func.count(Warengruppe.id)).scalar() or 0
        # Only active Warengruppen are offered to the LLM as a suggestion target;
        # deactivated ones stay in the DB for history but drop out of the prompt.
        wgs = (
            session.query(Warengruppe)
            .filter(Warengruppe.aktiv.is_(True))
            .order_by(Warengruppe.wg_id)
            .all()
        )
        rows = [
            CatalogEntry(
                wg_id=str(wg.wg_id),
                name=str(wg.wg_name).strip(),
                description=(wg.beschreibung or None),
                examples_enthalten=list(wg.examples_enthalten or []) if include_in else [],
                examples_nicht_enthalten=(
                    list(wg.examples_nicht_enthalten or []) if include_ex else []
                ),
                status=None,
                konfidenz=None,
            )
            for wg in wgs
        ]

    # Fall back to the Excel catalog only while the table is genuinely unseeded.
    # A seeded-but-all-deactivated table stays authoritative (empty prompt), so
    # we key the fallback on the total count, not on the active-filtered rows.
    if total == 0:
        logger.warning(
            "warengruppe table is empty — falling back to the Excel catalog. "
            "Run scripts/seed_warengruppen.py to import it into the DB."
        )
        from ..core.data import build_catalog
        return build_catalog(catalog_cfg)

    return WarengruppenCatalog(
        rows=rows,
        variant=variant,
        overlay_hash="",
        overlay_modell=None,
        overlay_datum_generierung=None,
        description_max_chars=catalog_cfg.get("description_max_chars"),
        examples_max_inclusive=int(catalog_cfg.get("examples_max_inclusive", 4)),
        examples_max_exclusive=int(catalog_cfg.get("examples_max_exclusive", 2)),
    )


def available_years() -> list[int]:
    """Return the available emission-factor years from the DB or Excel fallback."""
    with SessionLocal() as session:
        wgs = session.query(Warengruppe).all()
        years: set[int] = set()
        if not wgs:
            ef_map = _read_ef_per_year(DATA_DIR / EF_FILE)
            for entry_years in ef_map.values():
                years.update(entry_years.keys())
            return sorted(years)
        for wg in wgs:
            for ef in wg.emissionsfaktoren:
                years.add(int(ef.jahr))
        return sorted(years)


def ef_lookup(jahr: Optional[int] = None) -> dict[str, float]:
    """{wg_id -> emission factor} for the given year, else the most recent one.

    Falls back to the EF Excel while the table is unseeded.
    """
    with SessionLocal() as session:
        wgs = session.query(Warengruppe).all()
        if not wgs:
            return _ef_lookup_excel(jahr)
        out: dict[str, float] = {}
        for wg in wgs:
            efs = list(wg.emissionsfaktoren)
            if not efs:
                continue
            chosen = None
            if jahr is not None:
                chosen = next((e for e in efs if int(e.jahr) == jahr), None)
            if chosen is None:
                chosen = max(efs, key=lambda e: e.jahr)
            out[str(wg.wg_id)] = float(chosen.wert)
        return out


# --- seeding ----------------------------------------------------------------

def _read_ef_per_year(path) -> dict[str, dict[int, float]]:
    """{wg_id -> {jahr -> wert}} from the EF Excel, over all year columns."""
    df = clean_cols(pd.read_excel(path))
    if "Warengruppennummer" in df.columns:
        df = df.rename(columns={"Warengruppennummer": "Warengruppe"})
    if "Warengruppe" not in df.columns:
        return {}
    year_cols = [c for c in df.columns if str(c).isdigit()]
    out: dict[str, dict[int, float]] = {}
    for _, r in df.iterrows():
        wg = _str(r.get("Warengruppe"))
        if not wg:
            continue
        years: dict[int, float] = {}
        for c in year_cols:
            v = r.get(c)
            if v is None or pd.isna(v):
                continue
            try:
                years[int(str(c))] = float(v)
            except (TypeError, ValueError):
                continue
        if years:
            out[wg] = years
    return out


def _ef_lookup_excel(jahr: Optional[int] = None) -> dict[str, float]:
    ef_map = _read_ef_per_year(DATA_DIR / EF_FILE)
    out: dict[str, float] = {}
    for wg, years in ef_map.items():
        if not years:
            continue
        y = jahr if (jahr is not None and jahr in years) else max(years)
        out[wg] = float(years[y])
    return out


def seed_from_excel(force: bool = False) -> dict:
    """One-time import of the catalog (overlay) + emission factors (EF Excel).

    Idempotent guard: refuses to run on a non-empty table unless `force=True`,
    in which case it clears and reloads. Returns counts. Master is not read.
    """
    ef_map = _read_ef_per_year(DATA_DIR / EF_FILE)
    overlay = clean_cols(pd.read_excel(DATA_DIR / OVERLAY_FILE))

    with SessionLocal() as session:
        existing = session.query(Warengruppe).count()
        if existing and not force:
            raise RuntimeError(
                f"warengruppe table already has {existing} rows. "
                "Re-run with force=True to clear and reload."
            )
        if existing and force:
            session.query(Emissionsfaktor).delete()
            session.query(Warengruppe).delete()
            session.commit()

        created = 0
        ef_rows = 0
        for _, r in overlay.iterrows():
            wg_id = _str(r.get("wg_id"))
            name = _str(r.get("wg_name"))
            if not wg_id or not name:
                continue

            desc_llm = r.get("wg_desc_llm")
            desc_existing = r.get("wg_desc_existing")
            if not _is_blank(desc_llm):
                beschreibung = str(desc_llm).strip()
            elif not _is_blank(desc_existing):
                beschreibung = str(desc_existing).strip()
            else:
                beschreibung = None

            wg = Warengruppe(
                wg_id=wg_id,
                wg_name=name,
                beschreibung=beschreibung,
                examples_enthalten=_split_bullets(r.get("wg_examples_enthalten_llm")),
                examples_nicht_enthalten=_split_bullets(
                    r.get("wg_examples_nicht_enthalten_llm")
                ),
            )
            for jahr, wert in sorted(ef_map.get(wg_id, {}).items()):
                wg.emissionsfaktoren.append(Emissionsfaktor(jahr=jahr, wert=wert))
                ef_rows += 1
            session.add(wg)
            created += 1
        session.commit()

    invalidate_catalog_caches()
    return {"warengruppen": created, "emissionsfaktoren": ef_rows}


# --- cache invalidation -----------------------------------------------------

def invalidate_catalog_caches() -> None:
    """Drop the cached catalogs so the next model run / dashboard read sees edits.

    Prediction/plausibility memoise the catalog in a module global and template
    it into the model; nulling it forces `_ensure_model()` to rebuild from the
    DB and re-prepare the prompt. The dashboard reads `ef_lookup()` fresh per
    request, so it needs no separate cache reset.
    """
    for mod in ("prediction", "plausibility"):
        try:
            svc = __import__(f"{__package__}.{mod}", fromlist=[mod])
            svc._catalog = None
        except Exception:  # noqa: BLE001
            logger.exception("Could not reset %s catalog cache", mod)
