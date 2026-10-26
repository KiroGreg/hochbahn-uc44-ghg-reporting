"""Apply domain-expert review comments to the Warengruppen overlay.

Reads `dimWarengruppen_enriched_overlay_revised.xlsx` (with threaded Excel
comments and red-highlighted rows from the domain review), classifies each
comment by action type, calls the LLM to apply the changes, and writes a new
overlay Excel with visually marked cells for re-review.

Output: `dimWarengruppen_enriched_overlay_v2.xlsx`
- Orange cells   = LLM-modified (Zusatz / Korrektur / Abgrenzung)
- Red rows       = consolidated away (entfällt)
- Light blue rows = open question (Rückfrage) -- needs human decision
- White rows     = unchanged

Usage:
    .venv/bin/python "Use Case/models/scripts/apply_review_comments.py" --dry-run
    .venv/bin/python "Use Case/models/scripts/apply_review_comments.py"
    .venv/bin/python "Use Case/models/scripts/apply_review_comments.py" --model gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import openpyxl
import pandas as pd
from dotenv import load_dotenv
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent       # Use Case/models/scripts/
MODELS_DIR = HERE.parent                     # Use Case/models/
DATA_DIR = MODELS_DIR.parent                 # Use Case/
REPO_ROOT = DATA_DIR.parent                  # repo root

DEFAULT_REVISED = DATA_DIR / "dimWarengruppen_enriched_overlay_revised.xlsx"
DEFAULT_ORIGINAL = DATA_DIR / "dimWarengruppen_enriched_overlay.xlsx"
DEFAULT_OUTPUT = DATA_DIR / "dimWarengruppen_enriched_overlay_v2.xlsx"
DEFAULT_CACHE = HERE / ".cache" / "review_comments_audit.jsonl"


# Columns in the revised Excel start at row 3 (row 1 = C0..C13 sentinel,
# row 2 = real headers). Cell refs in openpyxl comments use Excel row
# numbers, so a comment on data row 3 has cell.row == 3.
REVISED_HEADER_ROW = 2
REVISED_DATA_START = 3

# Bullet-format helpers identical to the catalog loader.
RED_FILL_RGB = "FFFF0000"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    ENTFAELLT = "entfällt"
    ZUSATZ = "zusatz"
    KORREKTUR = "korrektur"
    ABGRENZUNG = "abgrenzung"
    RUECKFRAGE = "rückfrage"


# Priority order for picking the primary action of a Warengruppe with
# multiple comments. Higher value = higher priority.
ACTION_PRIORITY = {
    ActionType.ENTFAELLT: 5,
    ActionType.KORREKTUR: 4,
    ActionType.ZUSATZ: 3,
    ActionType.ABGRENZUNG: 2,
    ActionType.RUECKFRAGE: 1,
}


@dataclass
class ReviewComment:
    wg_name: str
    excel_row: int
    column_name: str          # e.g. "wg_desc_llm"
    text: str                 # cleaned (no Excel boilerplate)
    replies: list[str] = field(default_factory=list)
    is_red_row: bool = False
    action: ActionType | None = None


@dataclass
class WGReviewTask:
    wg_name: str
    excel_row: int
    comments: list[ReviewComment]
    primary_action: ActionType
    # ENTFAELLT: name of the target WG that absorbs this one.
    consolidation_target: str | None = None
    # ABGRENZUNG: related WG to cross-reference (best-effort guess).
    related_wg: str | None = None
    # For consolidation targets: list of source WGs being merged in.
    entfaellt_sources: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: extract comments
# ---------------------------------------------------------------------------

# Strip the Microsoft boilerplate; keep only "Kommentar:" / "Antwort:" bodies.
_BOILERPLATE = (
    "Ihre Version von Excel gestattet Ihnen das Lesen dieses Kommentarthreads"
)


def _strip_comment_boilerplate(raw: str) -> tuple[str, list[str]]:
    """Return (top_level_comment, [replies]) from an Excel threaded comment.

    Threaded comments are serialised as:
        [Kommentarthread]
        <boilerplate ...>
        [Tasks]                       (optional)
        <task note>
        Kommentar:
            <body, possibly multi-line>
        Antwort:
            <body>
        Antwort:
            <body>
    """
    lines = raw.split("\n")
    sections: list[tuple[str, list[str]]] = []
    current_label: str | None = None
    current_body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Kommentar:") or stripped.startswith("Antwort:"):
            if current_label is not None:
                sections.append((current_label, current_body))
            current_label = "kommentar" if stripped.startswith("Kommentar:") else "antwort"
            # Some comments put text on the same line as the label.
            tail = stripped.split(":", 1)[1].strip()
            current_body = [tail] if tail else []
        elif current_label is not None:
            # Indented body line.
            current_body.append(line.strip())
    if current_label is not None:
        sections.append((current_label, current_body))

    top = ""
    replies: list[str] = []
    for label, body in sections:
        text = " ".join(b for b in body if b).strip()
        if label == "kommentar" and not top:
            top = text
        elif label == "antwort":
            replies.append(text)
    return top, replies


def _is_red_filled(cell) -> bool:
    fill = cell.fill
    if not fill or not fill.fgColor or not fill.fgColor.rgb:
        return False
    return str(fill.fgColor.rgb).upper() == RED_FILL_RGB


def extract_comments(path: Path) -> list[ReviewComment]:
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    headers = {
        col: ws.cell(row=REVISED_HEADER_ROW, column=col).value
        for col in range(1, ws.max_column + 1)
    }

    comments: list[ReviewComment] = []
    for row in range(REVISED_DATA_START, ws.max_row + 1):
        wg_name = ws.cell(row=row, column=2).value
        if not wg_name:
            continue
        is_red = _is_red_filled(ws.cell(row=row, column=1))
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            if not cell.comment:
                continue
            top, replies = _strip_comment_boilerplate(cell.comment.text)
            if not top:
                continue
            comments.append(
                ReviewComment(
                    wg_name=str(wg_name).strip(),
                    excel_row=row,
                    column_name=str(headers.get(col, f"col{col}")),
                    text=top,
                    replies=replies,
                    is_red_row=is_red,
                )
            )

    # ENTFAELLT sources may carry no comment but only the red fill -- catch
    # those too so they end up in the output as `status="entfällt"`.
    for row in range(REVISED_DATA_START, ws.max_row + 1):
        if not _is_red_filled(ws.cell(row=row, column=1)):
            continue
        wg_name = str(ws.cell(row=row, column=2).value or "").strip()
        if not wg_name:
            continue
        if any(c.wg_name == wg_name and c.is_red_row for c in comments):
            continue
        comments.append(
            ReviewComment(
                wg_name=wg_name,
                excel_row=row,
                column_name="wg_name",
                text="(rote Markierung ohne Kommentartext)",
                is_red_row=True,
            )
        )
    return comments


# ---------------------------------------------------------------------------
# Step 2: classify action type
# ---------------------------------------------------------------------------

def classify_action(comment: ReviewComment) -> ActionType:
    text = comment.text.lower()
    if comment.is_red_row or "entfällt" in text or "integriert in zeile" in text:
        return ActionType.ENTFAELLT
    if "abgrenzung" in text or "abgleich" in text:
        return ActionType.ABGRENZUNG
    korrektur_triggers = ("korrektur:", "exkl.", "inkl.", "streichen",
                          "nur die", "ohne wartung", "muss deutlich werden",
                          "alle nutzfahrzeuge")
    if any(t in text for t in korrektur_triggers):
        return ActionType.KORREKTUR
    zusatz_triggers = ("zusatz:", "ergänzen", "einfügen", "gehören auch",
                       "bezug zur miete", "dazu, von", "ausschreiben",
                       "bitte beschreibungen", "achtung abgleich")
    if any(t in text for t in zusatz_triggers):
        return ActionType.ZUSATZ
    # Question form / vague feedback -> Rückfrage.
    if ("?" in comment.text
            or "zu allgemein" in text
            or "rückfrage" in text
            or "achtung:" in text):
        return ActionType.RUECKFRAGE
    return ActionType.RUECKFRAGE


# ---------------------------------------------------------------------------
# Step 3: group by Warengruppe, resolve consolidation targets
# ---------------------------------------------------------------------------

# German typographic quotes: „ = „ (low-9 opening), “ = " (closing).
_GERMAN_QUOTE_RE = re.compile("„([^“]+)“")
_ZEILE_RE = re.compile(r"Zeile\s+(\d+)", re.IGNORECASE)


def _resolve_consolidation_target(
    comment: ReviewComment, overlay_df: pd.DataFrame
) -> str | None:
    """Find the WG name the comment refers to as consolidation target."""
    m = _GERMAN_QUOTE_RE.search(comment.text)
    if m:
        return m.group(1).strip()
    m = _ZEILE_RE.search(comment.text)
    if m:
        excel_row = int(m.group(1))
        # Excel row 39 -> data index 39 - REVISED_DATA_START = 36 -- but the
        # revised file ordering differs from the original. Resolve via the
        # revised sheet's row->name mapping below in `_build_row_name_map`.
        return f"__row_{excel_row}__"
    return None


def _build_row_name_map(revised_path: Path) -> dict[int, str]:
    wb = openpyxl.load_workbook(revised_path, read_only=True)
    ws = wb.active
    out: dict[int, str] = {}
    for row in range(REVISED_DATA_START, ws.max_row + 1):
        name = ws.cell(row=row, column=2).value
        if name:
            out[row] = str(name).strip()
    return out


def _resolve_related_wg(
    comment: ReviewComment, overlay_df: pd.DataFrame
) -> str | None:
    """Best-effort: pick a related WG name for ABGRENZUNG."""
    text = comment.text.lower()
    # Hand-curated keyword -> candidate substring map; fall back to a fuzzy
    # search over wg_name values.
    keyword_hints = {
        "naturstein": "naturwerkstein",
        "ingenieursleistung": "ingenieurleistung",
        "ingenieurleistung": "ingenieurleistung",
        "psa": "psa",
        "arbeitskleidung": "arbeitskleidung",
        "aktenvernicht": "aktenvernicht",
    }
    for hint, needle in keyword_hints.items():
        if hint in text:
            for name in overlay_df["wg_name"].astype(str):
                if needle in name.lower() and name.strip() != comment.wg_name:
                    return name
    return None


def group_comments(
    comments: list[ReviewComment],
    overlay_df: pd.DataFrame,
    revised_path: Path,
) -> list[WGReviewTask]:
    by_wg: dict[str, list[ReviewComment]] = {}
    excel_rows: dict[str, int] = {}
    for c in comments:
        if c.action is None:
            c.action = classify_action(c)
        by_wg.setdefault(c.wg_name, []).append(c)
        excel_rows[c.wg_name] = c.excel_row

    row_name_map = _build_row_name_map(revised_path)

    tasks: list[WGReviewTask] = []
    for wg_name, wg_comments in by_wg.items():
        primary = max(wg_comments, key=lambda c: ACTION_PRIORITY[c.action]).action

        consolidation_target = None
        related = None

        if primary == ActionType.ENTFAELLT:
            for c in wg_comments:
                tgt = _resolve_consolidation_target(c, overlay_df)
                if tgt:
                    if tgt.startswith("__row_"):
                        row_num = int(tgt[len("__row_"):-2])
                        tgt = row_name_map.get(row_num)
                    consolidation_target = tgt
                    break

        if primary == ActionType.ABGRENZUNG:
            for c in wg_comments:
                rel = _resolve_related_wg(c, overlay_df)
                if rel:
                    related = rel
                    break
            # No related WG found -- downgrade to Rückfrage so the prompt
            # doesn't fabricate a fake counterpart.
            if related is None:
                primary = ActionType.RUECKFRAGE

        tasks.append(WGReviewTask(
            wg_name=wg_name,
            excel_row=excel_rows[wg_name],
            comments=wg_comments,
            primary_action=primary,
            consolidation_target=consolidation_target,
            related_wg=related,
        ))

    # Reverse-mapping: build entfaellt_sources for each consolidation target.
    target_to_sources: dict[str, list[str]] = {}
    for t in tasks:
        if t.primary_action == ActionType.ENTFAELLT and t.consolidation_target:
            target_to_sources.setdefault(t.consolidation_target, []).append(t.wg_name)

    # If a target already has a task (e.g. Spezialtiefbau has its own ZUSATZ
    # comment), attach the sources to it. Otherwise, create a synthetic task.
    for target_name, sources in target_to_sources.items():
        existing = next((t for t in tasks if t.wg_name == target_name), None)
        if existing:
            existing.entfaellt_sources = sources
            # Consolidation always wins over other actions on the target.
            existing.primary_action = ActionType.ZUSATZ
        else:
            # Synthetic task -- no reviewer comment on the target itself.
            row = next((r for r, n in row_name_map.items() if n == target_name), 0)
            tasks.append(WGReviewTask(
                wg_name=target_name,
                excel_row=row,
                comments=[],
                primary_action=ActionType.ZUSATZ,
                entfaellt_sources=sources,
            ))

    return tasks


# ---------------------------------------------------------------------------
# Step 4: LLM prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
Du bist ein erfahrener Beschaffungs- und Stammdaten-Experte für die
Hamburger Hochbahn AG. Ein Fachgutachter hat das LLM-generierte
Warengruppen-Overlay überprüft und Kommentare hinterlassen. Deine Aufgabe
ist es, die Korrekturanweisungen umzusetzen.

Antworte ausschließlich mit gültigem JSON. Schema:

{
  "beschreibung": "1 bis 4 Sätze in deutscher Sprache",
  "enthalten": ["3 bis 8 konkrete Einschluss-Beispiele"],
  "nicht_enthalten": ["2 bis 5 typische Abgrenzungen"],
  "konfidenz": 0-100,
  "anmerkung": "optional, ein Satz bei Mehrdeutigkeit oder leer",
  "status": "review_korrektur" | "review_zusatz" | "review_abgrenzung" | "review_rueckfrage",
  "diff_kurz": "kurze Beschreibung der vorgenommenen Änderungen"
}

Allgemeine Regeln:
- Sprache Deutsch.
- Erfinde keine konkreten Lieferanten- oder Produktnamen.
- Erfinde keine HOCHBAHN-internen Eigenkürzel (ATG, HADAG, FFG, HHA, BBM,
  SPNV, P+R, U5, U4HoGe), es sei denn, sie stehen im aktuellen Inhalt oder
  im Warengruppen-Namen.
- Setze den Reviewer-Kommentar so getreu wie möglich um.
- Ändere NUR das, was der Reviewer-Kommentar verlangt. Alles andere bleibt
  semantisch unverändert.
""".strip()


SYSTEM_PROMPT_ABGRENZUNG = """
Du bist ein erfahrener Beschaffungs- und Stammdaten-Experte für die
Hamburger Hochbahn AG. Ein Fachgutachter verlangt eine klarere Abgrenzung
zwischen zwei Warengruppen. Schreibe beide so um, dass sie sich
gegenseitig ausschließen.

Antworte ausschließlich mit gültigem JSON. Schema:

{
  "wg_a": {
    "beschreibung": "...",
    "enthalten": [...],
    "nicht_enthalten": [...],
    "konfidenz": 0-100,
    "anmerkung": "...",
    "status": "review_abgrenzung",
    "diff_kurz": "..."
  },
  "wg_b": { ... gleiches Schema ... }
}

Regeln:
- Jede WG referenziert die andere in "nicht_enthalten".
- Keine erfundenen Lieferanten/Produkte, keine erfundenen HOCHBAHN-Kürzel.
- Sprache Deutsch.
""".strip()


def _bullet(items: list[str] | None) -> str:
    if not items:
        return "(keine)"
    return "\n".join(f"- {i}" for i in items)


def _row_for_wg(overlay_df: pd.DataFrame, wg_name: str) -> pd.Series | None:
    matches = overlay_df[overlay_df["wg_name"].astype(str).str.strip() == wg_name]
    if matches.empty:
        return None
    return matches.iloc[0]


def _split_bullets(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    out: list[str] = []
    for line in str(value).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        elif line.startswith("-"):
            line = line[1:].strip()
        if line:
            out.append(line)
    return out


def _format_comments_block(comments: list[ReviewComment]) -> str:
    parts = []
    for c in comments:
        block = f"- [{c.column_name}] {c.text}"
        for r in c.replies:
            block += f"\n  (Antwort: {r})"
        parts.append(block)
    return "\n".join(parts)


def build_user_prompt(
    task: WGReviewTask, overlay_df: pd.DataFrame
) -> str:
    row = _row_for_wg(overlay_df, task.wg_name)
    if row is None:
        raise ValueError(f"WG {task.wg_name!r} nicht im Original-Overlay gefunden")

    cur_desc = row.get("wg_desc_llm") or row.get("wg_desc_existing") or "(keine)"
    cur_in = _split_bullets(row.get("wg_examples_enthalten_llm"))
    cur_ex = _split_bullets(row.get("wg_examples_nicht_enthalten_llm"))

    base = (
        f"Warengruppe: {task.wg_name}\n\n"
        f"Aktuelle Beschreibung:\n{cur_desc}\n\n"
        f"Aktuelle Einschluss-Beispiele:\n{_bullet(cur_in)}\n\n"
        f"Aktuelle Ausschluss-Beispiele:\n{_bullet(cur_ex)}\n\n"
        f"Reviewer-Kommentare:\n{_format_comments_block(task.comments)}\n"
    )

    if task.primary_action == ActionType.ZUSATZ and task.entfaellt_sources:
        # Consolidation target. Pull in source content.
        source_blocks = []
        for src_name in task.entfaellt_sources:
            src_row = _row_for_wg(overlay_df, src_name)
            if src_row is None:
                continue
            src_desc = src_row.get("wg_desc_llm") or "(keine)"
            src_in = _split_bullets(src_row.get("wg_examples_enthalten_llm"))
            source_blocks.append(
                f"{src_name}:\n  Beschreibung: {src_desc}\n"
                f"  Einschluss-Beispiele:\n{_bullet(src_in)}"
            )
        sources_text = "\n\n".join(source_blocks)
        return (
            base
            + "\nDie folgenden Warengruppen werden in diese Warengruppe "
              "konsolidiert (sie entfallen):\n\n"
            + sources_text
            + "\n\nAufgabe: Erstelle eine erweiterte Beschreibung und "
              "Einschluss-Beispiele, die die Inhalte der entfallenden "
              "Warengruppen integriert. Maximal 4-5 Sätze in der "
              "Beschreibung, 6-8 Einschluss-Beispiele. "
              "Wenn die Reviewer-Kommentare oben weitere Korrekturen "
              "(z.B. 'Exkl. X', 'inkl. Y') verlangen, setze diese "
              "zusätzlich um. Setze status = \"review_zusatz\". "
              "Gib alle Felder zurück."
        )

    if task.primary_action == ActionType.ZUSATZ:
        return base + (
            "\nAufgabe: Setze den Zusatz um. Füge die genannten Ergänzungen "
            "hinzu, ohne bestehende korrekte Inhalte zu entfernen. Setze "
            "status = \"review_zusatz\". Gib alle Felder zurück (auch die "
            "unveränderten)."
        )

    if task.primary_action == ActionType.KORREKTUR:
        return base + (
            "\nAufgabe: Korrigiere die Inhalte gemäß den Anweisungen. Wenn "
            "der Kommentar sagt \"Exkl. X\", entferne X aus den Beispielen "
            "und füge es zu nicht_enthalten hinzu. Wenn er sagt \"inkl. Y\", "
            "füge Y zu enthalten hinzu. Behalte alle nicht betroffenen "
            "Inhalte bei. Setze status = \"review_korrektur\"."
        )

    if task.primary_action == ActionType.RUECKFRAGE:
        return base + (
            "\nAufgabe: Der Reviewer hat eine offene Frage oder einen "
            "vagen Verbesserungswunsch. Versuche eine bestmögliche "
            "Verbesserung, aber markiere den Status als "
            "\"review_rueckfrage\" und setze die Konfidenz auf maximal 70. "
            "Eine endgültige Entscheidung muss der Fachgutachter treffen."
        )

    raise ValueError(f"Kein User-Prompt für Aktion {task.primary_action}")


def build_abgrenzung_prompt(
    task: WGReviewTask, overlay_df: pd.DataFrame
) -> str:
    row_a = _row_for_wg(overlay_df, task.wg_name)
    row_b = _row_for_wg(overlay_df, task.related_wg) if task.related_wg else None

    def _fmt(name, row):
        if row is None:
            return f"Warengruppe: {name}\n  (nicht im Overlay gefunden)"
        desc = row.get("wg_desc_llm") or row.get("wg_desc_existing") or "(keine)"
        ins = _split_bullets(row.get("wg_examples_enthalten_llm"))
        exs = _split_bullets(row.get("wg_examples_nicht_enthalten_llm"))
        return (
            f"Warengruppe: {name}\n"
            f"Beschreibung: {desc}\n"
            f"Einschluss-Beispiele:\n{_bullet(ins)}\n"
            f"Ausschluss-Beispiele:\n{_bullet(exs)}"
        )

    a_block = _fmt(task.wg_name, row_a)
    b_block = _fmt(task.related_wg or "(unbekannt)", row_b)
    comments = _format_comments_block(task.comments)
    return (
        f"WG A (Hauptkommentar):\n{a_block}\n\n"
        f"WG B (verwandte Warengruppe):\n{b_block}\n\n"
        f"Reviewer-Kommentare:\n{comments}\n\n"
        "Aufgabe: Erstelle eine klare Abgrenzung. Antworte mit JSON nach "
        "dem Schema {\"wg_a\": {...}, \"wg_b\": {...}}. Beide WGs erhalten "
        "alle Felder. Jede WG referenziert die andere in nicht_enthalten."
    )


# ---------------------------------------------------------------------------
# Step 5: LLM caller + cache
# ---------------------------------------------------------------------------

def _check_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY ist nicht gesetzt. In Use Case/models/.env "
            "setzen oder per Shell exportieren."
        )
    return key


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    out: dict = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                out[rec["cache_key"]] = rec
            except (json.JSONDecodeError, KeyError):
                continue
    return out


def append_cache(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    client=None,
) -> dict:
    if client is None:
        from openai import OpenAI
        _check_api_key()
        client = OpenAI()

    last_err = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            usage = response.usage.model_dump() if response.usage else None
            return {"ok": True, "parsed": parsed, "raw": raw, "usage": usage}
        except json.JSONDecodeError as e:
            last_err = f"JSONDecodeError: {e}; raw={raw[:200]!r}"
            if attempt == 1:
                break
            time.sleep(0.5)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            break
    return {"ok": False, "error": last_err}


# ---------------------------------------------------------------------------
# Step 6: orchestrate processing
# ---------------------------------------------------------------------------

def _processing_order(tasks: list[WGReviewTask]) -> list[WGReviewTask]:
    """Targets first (need source content), then sources, then the rest."""
    order_key = {
        ActionType.ZUSATZ: 0,        # consolidation targets sit in ZUSATZ
        ActionType.KORREKTUR: 1,
        ActionType.ENTFAELLT: 2,     # sources -- no LLM call
        ActionType.ABGRENZUNG: 3,
        ActionType.RUECKFRAGE: 4,
    }
    # Consolidation targets (have entfaellt_sources) go before plain ZUSATZ.
    def k(t):
        base = order_key.get(t.primary_action, 5)
        bonus = 0 if t.entfaellt_sources else 1
        return (base, bonus, t.wg_name)
    return sorted(tasks, key=k)


def process_tasks(
    tasks: list[WGReviewTask],
    overlay_df: pd.DataFrame,
    cache_path: Path,
    model: str,
    temperature: float,
    dry_run: bool,
) -> list[dict]:
    cache = load_cache(cache_path)
    print(f"Cache enthält bereits {len(cache)} Einträge.")

    results: list[dict] = []
    client = None
    for task in _processing_order(tasks):
        # ENTFAELLT sources: no LLM call.
        if task.primary_action == ActionType.ENTFAELLT:
            results.append({
                "wg_name": task.wg_name,
                "action": task.primary_action.value,
                "skip_llm": True,
                "consolidation_target": task.consolidation_target,
                "comments": [c.text for c in task.comments],
            })
            continue

        cache_key = f"{task.wg_name}___{task.primary_action.value}"
        if cache_key in cache:
            print(f"  [skip] {task.wg_name!r} ({task.primary_action.value})")
            results.append(cache[cache_key])
            continue

        is_abgrenzung = task.primary_action == ActionType.ABGRENZUNG
        if is_abgrenzung:
            system_prompt = SYSTEM_PROMPT_ABGRENZUNG
            user_prompt = build_abgrenzung_prompt(task, overlay_df)
        else:
            system_prompt = SYSTEM_PROMPT
            user_prompt = build_user_prompt(task, overlay_df)

        if dry_run:
            print(f"  [dry-run] {task.wg_name!r} ({task.primary_action.value})")
            results.append({
                "cache_key": cache_key,
                "wg_name": task.wg_name,
                "action": task.primary_action.value,
                "dry_run": True,
                "user_prompt_preview": user_prompt[:400],
                "comments": [c.text for c in task.comments],
            })
            continue

        print(f"  [call] {task.wg_name!r} ({task.primary_action.value}) ...", end=" ")
        if client is None:
            from openai import OpenAI
            _check_api_key()
            client = OpenAI()
        result = call_llm(system_prompt, user_prompt, model, temperature, client=client)

        record = {
            "cache_key": cache_key,
            "wg_name": task.wg_name,
            "action": task.primary_action.value,
            "related_wg": task.related_wg,
            "entfaellt_sources": task.entfaellt_sources,
            "comments": [c.text for c in task.comments],
            "modell": model,
            "datum_generierung": datetime.now(timezone.utc).isoformat(),
            "ok": result["ok"],
        }
        if result["ok"]:
            record["llm"] = result["parsed"]
            record["usage"] = result["usage"]
            print("ok")
        else:
            record["error"] = result["error"]
            print(f"FEHLER: {result['error']}")
        append_cache(cache_path, record)
        results.append(record)
        time.sleep(0.3)

    return results


# ---------------------------------------------------------------------------
# Step 7: merge results into DataFrame and export
# ---------------------------------------------------------------------------

def _format_bullets_for_excel(items) -> str:
    if not items:
        return ""
    return "\n".join(f"- {i}" for i in items)


def merge_results(
    original_df: pd.DataFrame, results: list[dict]
) -> tuple[pd.DataFrame, dict[tuple[str, str], str]]:
    """Apply LLM results to the overlay DataFrame.

    Returns the new DataFrame and a change map keyed on
    `(wg_name, column_name)` with the action type as value -- used by the
    Excel exporter to colour modified cells.
    """
    df = original_df.copy()
    df["review_kommentar"] = ""
    df["review_aktion"] = ""

    change_map: dict[tuple[str, str], str] = {}
    now = datetime.now(timezone.utc).isoformat()

    for r in results:
        wg = r["wg_name"]
        action = r["action"]
        mask = df["wg_name"].astype(str).str.strip() == wg
        if not mask.any():
            print(f"  [WARN] WG {wg!r} im Original-Overlay nicht gefunden")
            continue
        idx = df.index[mask][0]

        kommentar_text = " | ".join(r.get("comments", [])) or ""
        df.at[idx, "review_kommentar"] = kommentar_text
        df.at[idx, "review_aktion"] = action
        change_map[(wg, "review_kommentar")] = action
        change_map[(wg, "review_aktion")] = action

        if r.get("skip_llm"):
            # ENTFAELLT source: mark status, keep content for reference.
            df.at[idx, "status"] = "entfällt"
            tgt = r.get("consolidation_target")
            if tgt:
                df.at[idx, "anmerkung_llm"] = f"Konsolidiert in: {tgt}"
            change_map[(wg, "status")] = "entfällt"
            change_map[(wg, "anmerkung_llm")] = "entfällt"
            continue

        if not r.get("ok") or "llm" not in r:
            df.at[idx, "anmerkung_llm"] = f"LLM-Aufruf fehlgeschlagen oder dry-run: {r.get('error', 'dry-run')}"
            continue

        parsed = r["llm"]

        # ABGRENZUNG response has two payloads; index 0 == this WG.
        if action == "abgrenzung" and isinstance(parsed, dict) and "wg_a" in parsed:
            payloads = [(wg, parsed["wg_a"])]
            if r.get("related_wg"):
                payloads.append((r["related_wg"], parsed["wg_b"]))
        else:
            payloads = [(wg, parsed)]

        for target_wg, payload in payloads:
            tmask = df["wg_name"].astype(str).str.strip() == target_wg
            if not tmask.any():
                continue
            tidx = df.index[tmask][0]
            new_desc = payload.get("beschreibung") or ""
            new_in = payload.get("enthalten") or []
            new_ex = payload.get("nicht_enthalten") or []

            if df.at[tidx, "wg_desc_llm"] != new_desc:
                df.at[tidx, "wg_desc_llm"] = new_desc
                change_map[(target_wg, "wg_desc_llm")] = action

            new_in_str = _format_bullets_for_excel(new_in)
            if df.at[tidx, "wg_examples_enthalten_llm"] != new_in_str:
                df.at[tidx, "wg_examples_enthalten_llm"] = new_in_str
                change_map[(target_wg, "wg_examples_enthalten_llm")] = action

            new_ex_str = _format_bullets_for_excel(new_ex)
            if df.at[tidx, "wg_examples_nicht_enthalten_llm"] != new_ex_str:
                df.at[tidx, "wg_examples_nicht_enthalten_llm"] = new_ex_str
                change_map[(target_wg, "wg_examples_nicht_enthalten_llm")] = action

            df.at[tidx, "konfidenz_llm"] = payload.get("konfidenz", df.at[tidx, "konfidenz_llm"])
            df.at[tidx, "anmerkung_llm"] = payload.get("anmerkung") or ""
            df.at[tidx, "status"] = payload.get("status") or f"review_{action}"
            df.at[tidx, "diff_kurz"] = payload.get("diff_kurz") or ""
            df.at[tidx, "modell"] = r.get("modell", "")
            df.at[tidx, "datum_generierung"] = now
            change_map[(target_wg, "status")] = action

            if target_wg != wg and not df.at[tidx, "review_kommentar"]:
                df.at[tidx, "review_kommentar"] = (
                    f"Abgrenzung -- aktualisiert wegen Kommentar an WG: {wg}"
                )
                df.at[tidx, "review_aktion"] = "abgrenzung"
                change_map[(target_wg, "review_kommentar")] = "abgrenzung"
                change_map[(target_wg, "review_aktion")] = "abgrenzung"

    return df, change_map


# Colour palette for the output.
FILL_CHANGED = PatternFill(start_color="FFF4B084", end_color="FFF4B084", fill_type="solid")
FILL_ENTFAELLT = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")
FILL_RUECKFRAGE = PatternFill(start_color="FFD6E4F0", end_color="FFD6E4F0", fill_type="solid")
FILL_HEADER = PatternFill(start_color="FFD9D9D9", end_color="FFD9D9D9", fill_type="solid")
FONT_STRIKE_WHITE = Font(strikethrough=True, color="FFFFFFFF")
FONT_ITALIC = Font(italic=True)
FONT_BOLD = Font(bold=True)

OUTPUT_COLUMNS = [
    "wg_id", "wg_name", "modus", "wg_desc_existing", "wg_desc_llm",
    "wg_examples_existing", "wg_examples_enthalten_llm",
    "wg_examples_nicht_enthalten_llm", "konfidenz_llm", "anmerkung_llm",
    "status", "diff_kurz", "modell", "datum_generierung",
    "review_kommentar", "review_aktion",
]

COLUMN_WIDTHS = {
    "wg_id": 16, "wg_name": 32, "modus": 18,
    "wg_desc_existing": 50, "wg_desc_llm": 50,
    "wg_examples_existing": 50, "wg_examples_enthalten_llm": 40,
    "wg_examples_nicht_enthalten_llm": 40, "konfidenz_llm": 10,
    "anmerkung_llm": 30, "status": 18, "diff_kurz": 30,
    "modell": 14, "datum_generierung": 22,
    "review_kommentar": 50, "review_aktion": 16,
}

WRAP_COLS = {
    "wg_desc_existing", "wg_desc_llm", "wg_examples_existing",
    "wg_examples_enthalten_llm", "wg_examples_nicht_enthalten_llm",
    "anmerkung_llm", "diff_kurz", "review_kommentar",
}


def export_excel(
    df: pd.DataFrame,
    change_map: dict[tuple[str, str], str],
    path: Path,
) -> None:
    out = df[OUTPUT_COLUMNS].copy()
    # Sort: reviewed rows first (any action), then by original sort order.
    status_order = {
        "neu": 0, "ergänzung_beispiele": 1, "verbessert": 2,
        "unverändert": 3, "review_korrektur": -3, "review_zusatz": -3,
        "review_abgrenzung": -3, "review_rueckfrage": -2, "entfällt": 4,
    }
    out["_review_first"] = out["review_aktion"].apply(lambda x: 0 if x else 1)
    out["_status_sort"] = out["status"].map(status_order).fillna(99).astype(int)
    out = out.sort_values(
        ["_review_first", "_status_sort", "konfidenz_llm"],
        ascending=[True, True, True],
    ).drop(columns=["_review_first", "_status_sort"])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Review v2"

    # Header row.
    for col_idx, col_name in enumerate(OUTPUT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = FONT_BOLD
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = COLUMN_WIDTHS.get(col_name, 20)

    wrap_align = Alignment(wrap_text=True, vertical="top")

    for r_idx, (_, row) in enumerate(out.iterrows(), start=2):
        action = row.get("review_aktion") or ""
        status = row.get("status") or ""
        wg = str(row.get("wg_name", "")).strip()

        row_fill = None
        row_font = None
        if status == "entfällt":
            row_fill = FILL_ENTFAELLT
            row_font = FONT_STRIKE_WHITE
        elif action == "rückfrage":
            row_fill = FILL_RUECKFRAGE
            row_font = FONT_ITALIC

        for c_idx, col_name in enumerate(OUTPUT_COLUMNS, start=1):
            value = row[col_name]
            if pd.isna(value):
                value = None
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if col_name in WRAP_COLS:
                cell.alignment = wrap_align
            else:
                cell.alignment = Alignment(vertical="top")

            if row_fill is not None:
                cell.fill = row_fill
                if row_font is not None:
                    cell.font = row_font
            elif (wg, col_name) in change_map and action not in ("entfällt",):
                cell.fill = FILL_CHANGED

    # Freeze header row.
    ws.freeze_panes = "A2"

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"Excel geschrieben: {path}  ({len(out)} Zeilen)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_summary(
    comments: list[ReviewComment], tasks: list[WGReviewTask]
) -> None:
    from collections import Counter
    action_counts = Counter(c.action.value for c in comments if c.action)
    print(f"\nExtrahiert: {len(comments)} Kommentare über {len(tasks)} Warengruppen.")
    print("Verteilung nach Aktionstyp:")
    for k, v in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {k:14s} {v}")

    consolidation = [t for t in tasks if t.entfaellt_sources]
    if consolidation:
        print("\nKonsolidierungs-Ziele (mit Quellen):")
        for t in consolidation:
            print(f"  {t.wg_name} <- {', '.join(t.entfaellt_sources)}")

    abgrenzungen = [t for t in tasks if t.primary_action == ActionType.ABGRENZUNG]
    if abgrenzungen:
        print("\nAbgrenzungen (verwandte WG aufgelöst):")
        for t in abgrenzungen:
            print(f"  {t.wg_name} <-> {t.related_wg or '(?)'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Setzt Fachgutachter-Kommentare aus der revidierten Overlay-Excel "
            "per LLM um und schreibt eine neue v2-Overlay-Excel mit "
            "farbcodierten Zellen fürs Re-Review."
        )
    )
    parser.add_argument("--revised", default=str(DEFAULT_REVISED))
    parser.add_argument("--original", default=str(DEFAULT_ORIGINAL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Nur Extraktion und Klassifikation, keine LLM-Calls.",
    )
    args = parser.parse_args()

    # Load .env from models/ (where the other scripts look) and repo root.
    load_dotenv(MODELS_DIR / ".env", override=False)
    load_dotenv(REPO_ROOT / ".env", override=False)

    revised_path = Path(args.revised)
    original_path = Path(args.original)
    output_path = Path(args.output)
    cache_path = Path(args.cache)

    if not revised_path.exists():
        print(f"FEHLER: revidierte Datei nicht gefunden: {revised_path}", file=sys.stderr)
        return 2
    if not original_path.exists():
        print(f"FEHLER: Original-Overlay nicht gefunden: {original_path}", file=sys.stderr)
        return 2

    print(f"Lade Original-Overlay: {original_path}")
    overlay_df = pd.read_excel(original_path)
    print(f"  {len(overlay_df)} Zeilen, {len(overlay_df.columns)} Spalten")

    print(f"\nExtrahiere Kommentare aus: {revised_path}")
    comments = extract_comments(revised_path)
    for c in comments:
        if c.action is None:
            c.action = classify_action(c)

    tasks = group_comments(comments, overlay_df, revised_path)
    _print_summary(comments, tasks)

    if args.dry_run:
        print("\n--dry-run: keine LLM-Calls, kein Excel-Output.")
        return 0

    print(f"\nVerarbeite {len(tasks)} Tasks mit Modell {args.model} ...")
    results = process_tasks(
        tasks, overlay_df, cache_path, args.model, args.temperature, dry_run=False,
    )

    print("\nMerge Ergebnisse ins DataFrame ...")
    merged_df, change_map = merge_results(overlay_df, results)

    print(f"\nSchreibe Output: {output_path}")
    export_excel(merged_df, change_map, output_path)
    print("\nFertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
