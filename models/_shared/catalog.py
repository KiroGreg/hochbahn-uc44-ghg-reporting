"""Warengruppen catalog loader shared by both LLM models.

Loads the dim master and optionally merges the LLM-enriched overlay
(`Use Case/dimWarengruppen_enriched_overlay.xlsx`). Master is never
mutated -- the overlay is joined in-memory on `wg_id`. The resulting
`WarengruppenCatalog` carries the audit metadata that both models write
into their output Excel for CSRD purposes.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


VALID_VARIANTS = ("baseline", "overlay_desc", "overlay_inclusive", "overlay_full")
ON_MISSING_OPTIONS = ("error", "warn", "fallback_master")

# Leading enumeration prefix an LLM tends to echo from the numbered catalog
# ("12. Name", "12) Name"). Names never legitimately start with a number.
_ENUM_PREFIX = re.compile(r"^\s*\d{1,3}[.)]\s*")
# All unicode dash variants (figure/en/em/minus/…) → plain hyphen-minus.
_DASH_CHARS = {ord(c): "-" for c in "‐‑‒–—―−"}
# Inner punctuation an LLM freely adds or drops when echoing a catalog name:
# the catalog itself is inconsistent ("DL, Wartung …" next to "DL Wartung …"),
# so the model regularly answers with the dominant spelling and a comma-only
# mismatch used to drop the suggestion entirely. Commas/semicolons/colons/
# periods carry no category meaning → folded to spaces in the lookup key.
# Slashes DO separate alternatives ("PKW/LKW") and are kept, but lose
# surrounding whitespace so "PKW / LKW" still matches.
_INNER_PUNCT = re.compile(r"[,;:.]+")
_SLASH_WS = re.compile(r"\s*/\s*")


def clean_wg_name(value: object) -> str:
    """Display-canonical Warengruppe name (whitespace-clean, content untouched).

    The master Excel carries embedded newlines, double spaces and edge
    whitespace in a fifth of its names. Cleaning happens once here at load
    time, so the same clean string flows everywhere a name surfaces: the
    dropdown options, ``resolve()`` results, prompt rendering and the
    dashboard id<->name maps. Unlike ``normalize_wg_key`` this keeps casing,
    dashes and punctuation — it is a display form, not a lookup key.
    """
    if value is None:
        return ""
    s = str(value).replace("\n", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", s).strip()


def normalize_wg_key(value: object) -> str:
    """Canonical lookup key for matching a Warengruppe name to the catalog.

    Collapses the deviations an LLM answer (or a stray catalog cell) commonly
    carries — unicode/dash/whitespace noise, a leading enumeration prefix
    ("12. "), inner and edge punctuation (",;:." → space; slash spacing),
    casing, and ß→ss (via ``casefold``) — WITHOUT merging genuinely distinct
    categories. Verified collision-free across the 192-entry master catalog,
    so the same key is safe to apply to both the model's answer and the
    catalog option list.
    """
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.translate(_DASH_CHARS)
    s = s.replace("\n", " ").replace("\t", " ")
    s = _ENUM_PREFIX.sub("", s)
    s = _INNER_PUNCT.sub(" ", s)
    s = _SLASH_WS.sub("/", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip().strip("\"'").strip()
    return s.casefold()


def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize whitespace in column names (newlines, multi-spaces, edges)."""
    df.columns = [
        re.sub(r"\s+", " ", str(c).replace("\n", " ")).strip() for c in df.columns
    ]
    return df


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return not str(value).strip()


def _split_bullets(value: object) -> list[str]:
    """Overlay stores examples as `- item\\n- item`. Return as list of strings."""
    if _is_blank(value):
        return []
    items: list[str] = []
    for line in str(value).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        elif line.startswith("-"):
            line = line[1:].strip()
        if line:
            items.append(line)
    return items


def _bullet_string(items: list[str]) -> str:
    """Inverse of _split_bullets: join into `- item\\n- item` for prompts."""
    return "\n".join(f"- {it}" for it in items)


@dataclass
class CatalogEntry:
    wg_id: str                   # internal merge key, never sent to the LLM
    name: str
    description: str | None
    examples_enthalten: list[str]
    examples_nicht_enthalten: list[str]
    # Overlay-only fields. None on baseline.
    status: str | None
    konfidenz: int | None


@dataclass
class WarengruppenCatalog:
    rows: list[CatalogEntry]
    variant: str
    overlay_hash: str            # "" on baseline
    overlay_modell: str | None
    overlay_datum_generierung: str | None
    description_max_chars: int | None
    examples_max_inclusive: int
    examples_max_exclusive: int
    # normalized key -> canonical stored name; built in __post_init__.
    _by_norm: dict[str, str] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        # First entry wins on the (currently non-existent) chance two names
        # normalize to the same key -- keeps resolve() deterministic.
        for e in self.rows:
            self._by_norm.setdefault(normalize_wg_key(e.name), e.name)

    def names(self) -> set[str]:
        return {e.name for e in self.rows}

    def resolve(self, name: object) -> str | None:
        """Map a possibly-noisy name to its exact catalog entry name, else None.

        Tolerant of the deviations described in ``normalize_wg_key`` (leading
        enumeration prefix, whitespace/dash noise, casing, ß/ss). Returns the
        canonical stored name — i.e. exactly the string shown in the dropdown —
        so a resolved suggestion always pre-selects cleanly in the UI.
        """
        key = normalize_wg_key(name)
        if not key:
            return None
        return self._by_norm.get(key)

    def lookup(self, wg_name: str) -> CatalogEntry | None:
        if not wg_name:
            return None
        for e in self.rows:
            if e.name == wg_name:
                return e
        return None

    def _trim_desc(self, desc: str) -> str:
        d = desc.replace("\n", " ").strip()
        if self.description_max_chars is not None and len(d) > self.description_max_chars:
            d = d[: self.description_max_chars].rstrip()
        return d

    def render_for_prediction(self) -> str:
        """Numbered single-line catalog string for the prediction prompt.

        Layout per entry:
            `123. Name — Description. ENTHÄLT: a; b; c. NICHT: x; y.`
        """
        lines: list[str] = []
        for i, e in enumerate(self.rows, 1):
            line = f"{i:3}. {e.name}"
            if e.description:
                line += f" — {self._trim_desc(e.description)}"
            if e.examples_enthalten:
                items = e.examples_enthalten[: self.examples_max_inclusive]
                line += " ENTHÄLT: " + "; ".join(items) + "."
            if e.examples_nicht_enthalten:
                items = e.examples_nicht_enthalten[: self.examples_max_exclusive]
                line += " NICHT: " + "; ".join(items) + "."
            lines.append(line)
        return "\n".join(lines)

    def catalog_hash(self) -> str:
        """Stable hash over the rendered prediction catalog (variant-aware)."""
        return hashlib.sha256(
            self.render_for_prediction().encode("utf-8")
        ).hexdigest()[:16]

    @property
    def has_examples_enthalten(self) -> bool:
        return any(e.examples_enthalten for e in self.rows)

    @property
    def has_examples_nicht_enthalten(self) -> bool:
        return any(e.examples_nicht_enthalten for e in self.rows)

    @property
    def has_any_examples(self) -> bool:
        return self.has_examples_enthalten or self.has_examples_nicht_enthalten

    def as_invoice_merge_frame(self) -> pd.DataFrame:
        """DataFrame for merging into invoices on `Warengruppe` (= wg_id).

        Column names are stable -- they are the keys consumed by
        `plausibility_model/config.yml` `input_columns`. Examples come back as
        bullet-line strings (`"- a\\n- b"`) so they render directly in the
        user_template.
        """
        return pd.DataFrame(
            [
                {
                    "Warengruppe": entry.wg_id,
                    "wg_name": entry.name,
                    "wg_description": entry.description or "",
                    "wg_examples_enthalten": _bullet_string(
                        entry.examples_enthalten[: self.examples_max_inclusive]
                    ),
                    "wg_examples_nicht_enthalten": _bullet_string(
                        entry.examples_nicht_enthalten[: self.examples_max_exclusive]
                    ),
                    "wg_status_overlay": entry.status,
                    "wg_konfidenz_overlay": entry.konfidenz,
                }
                for entry in self.rows
            ]
        )


def _load_master(master_path: Path) -> pd.DataFrame:
    df = _clean_cols(pd.read_excel(master_path))
    df = df.rename(
        columns={
            "WG Nr.": "wg_id",
            "Warengruppenbezeichnung": "wg_name",
            "Genauere Beschreibung der Warengruppe": "wg_desc_master",
        }
    )
    keep = [c for c in ("wg_id", "wg_name", "wg_desc_master") if c in df.columns]
    df = df[keep].dropna(subset=["wg_name"]).reset_index(drop=True)
    return df


def _load_overlay(overlay_path: Path) -> pd.DataFrame:
    return pd.read_excel(overlay_path)


def _hash_overlay(df: pd.DataFrame) -> str:
    cols = [
        "wg_id",
        "wg_desc_llm",
        "wg_examples_enthalten_llm",
        "wg_examples_nicht_enthalten_llm",
    ]
    sub = df[[c for c in cols if c in df.columns]].copy()
    sub = sub.sort_values("wg_id").reset_index(drop=True)
    blob = sub.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_warengruppen(data_dir: Path | str, catalog_cfg: dict) -> WarengruppenCatalog:
    """Load the Warengruppen catalog according to the given variant config.

    `catalog_cfg` is the `catalog:` block of a model's `config.yml`. Required
    field: `variant` (one of `baseline`, `overlay_desc`, `overlay_inclusive`,
    `overlay_full`). The legacy `include_descriptions` switch is intentionally
    not supported -- migration is a one-time edit.
    """
    data_dir = Path(data_dir)
    variant = catalog_cfg.get("variant")
    if variant not in VALID_VARIANTS:
        raise ValueError(
            f"catalog.variant must be one of {VALID_VARIANTS}, got {variant!r}. "
            "Set `catalog.variant` in your config.yml; the legacy "
            "`include_descriptions` field is no longer supported."
        )

    master_path = data_dir / catalog_cfg.get(
        "master_path", "dimWarengruppen_hashed.xlsx"
    )
    overlay_path = data_dir / catalog_cfg.get(
        "overlay_path", "dimWarengruppen_enriched_overlay.xlsx"
    )
    on_missing = catalog_cfg.get("on_missing_overlay", "warn")
    if on_missing not in ON_MISSING_OPTIONS:
        raise ValueError(
            f"on_missing_overlay must be one of {ON_MISSING_OPTIONS}, got {on_missing!r}"
        )

    description_max_chars = catalog_cfg.get("description_max_chars")
    examples_max_inclusive = int(catalog_cfg.get("examples_max_inclusive", 4))
    examples_max_exclusive = int(catalog_cfg.get("examples_max_exclusive", 2))

    master = _load_master(master_path)

    overlay_hash = ""
    overlay_modell: str | None = None
    overlay_datum: str | None = None

    if variant == "baseline":
        merged = master.copy()
        merged["wg_desc_llm"] = pd.NA
        merged["wg_examples_enthalten_llm"] = pd.NA
        merged["wg_examples_nicht_enthalten_llm"] = pd.NA
        merged["status"] = pd.NA
        merged["konfidenz_llm"] = pd.NA
    else:
        overlay = _load_overlay(overlay_path)
        overlay_hash = _hash_overlay(overlay)[:16]

        if "modell" in overlay.columns:
            mvals = overlay["modell"].dropna()
            if not mvals.empty:
                overlay_modell = str(mvals.iloc[0])
        if "datum_generierung" in overlay.columns:
            dvals = overlay["datum_generierung"].dropna()
            if not dvals.empty:
                overlay_datum = str(dvals.iloc[0])

        # Drop overlay's wg_name -- master name is canonical to avoid suffix collisions.
        overlay_for_merge = overlay.drop(columns=["wg_name"], errors="ignore")
        merged = master.merge(overlay_for_merge, on="wg_id", how="outer", indicator=True)
        master_only = merged[merged["_merge"] == "left_only"]["wg_id"].tolist()
        overlay_only = merged[merged["_merge"] == "right_only"]["wg_id"].tolist()
        if master_only or overlay_only:
            msg = (
                f"catalog merge mismatch: {len(master_only)} wg_id(s) only in master, "
                f"{len(overlay_only)} only in overlay."
            )
            if on_missing == "error":
                raise RuntimeError(msg)
            if on_missing == "warn":
                warnings.warn(msg, RuntimeWarning, stacklevel=2)
        # Drop overlay-only rows -- without a master name we can't classify into them.
        merged = merged[merged["_merge"] != "right_only"].drop(columns=["_merge"])

    include_in = variant in ("overlay_inclusive", "overlay_full")
    include_ex = variant == "overlay_full"

    rows: list[CatalogEntry] = []
    for _, row in merged.iterrows():
        wg_id = str(row["wg_id"]) if not _is_blank(row.get("wg_id")) else ""
        name = clean_wg_name(row["wg_name"])
        master_desc = row.get("wg_desc_master") if "wg_desc_master" in merged.columns else None

        if variant == "baseline":
            description = None if _is_blank(master_desc) else str(master_desc).strip()
            entry = CatalogEntry(
                wg_id=wg_id,
                name=name,
                description=description,
                examples_enthalten=[],
                examples_nicht_enthalten=[],
                status=None,
                konfidenz=None,
            )
        else:
            llm_desc = row.get("wg_desc_llm")
            if not _is_blank(llm_desc):
                description = str(llm_desc).strip()
            elif not _is_blank(master_desc):
                description = str(master_desc).strip()
            else:
                description = None

            enthalten = (
                _split_bullets(row.get("wg_examples_enthalten_llm")) if include_in else []
            )
            nicht_enthalten = (
                _split_bullets(row.get("wg_examples_nicht_enthalten_llm")) if include_ex else []
            )

            status_val = row.get("status")
            status = None if _is_blank(status_val) else str(status_val).strip()

            konfidenz_val = row.get("konfidenz_llm")
            konfidenz = None if _is_blank(konfidenz_val) else int(konfidenz_val)

            entry = CatalogEntry(
                wg_id=wg_id,
                name=name,
                description=description,
                examples_enthalten=enthalten,
                examples_nicht_enthalten=nicht_enthalten,
                status=status,
                konfidenz=konfidenz,
            )
        rows.append(entry)

    return WarengruppenCatalog(
        rows=rows,
        variant=variant,
        overlay_hash=overlay_hash,
        overlay_modell=overlay_modell,
        overlay_datum_generierung=overlay_datum,
        description_max_chars=description_max_chars,
        examples_max_inclusive=examples_max_inclusive,
        examples_max_exclusive=examples_max_exclusive,
    )
