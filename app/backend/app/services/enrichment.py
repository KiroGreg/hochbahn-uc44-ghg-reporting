"""LLM enrichment for the Warengruppen catalog.

Generates or gently improves a Warengruppe's description + example lists via the
LLM, with **per-field** control (`lassen` / `ergänzen` / `neu`). This ports the
offline notebook ``Use Case/notebooks/02_warengruppen_enrichment.ipynb`` — the
system prompt, the anti-hallucination rules and the strict-mode for unchanged
text — into the web app, and generalises its three whole-Warengruppe modes into
independent per-field actions:

    neu                 = beschreibung:neu,    enthalten:neu,    nicht:neu
    ergänzung_beispiele = beschreibung:lassen, enthalten:neu,    nicht:neu
    verbessern          = beschreibung:ergänzen (+ examples ergänzen)

The OpenAI client is bootstrapped exactly like ``services/embeddings.py`` (lazy,
thread-locked, key resolved from env → the baked-in ``Use Case/models/.env``).
Callers get an ``EnrichSuggestion`` back — nothing is persisted here; saving runs
through the normal ``warengruppen.update()`` path so the catalog cache is reset.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from ..core.paths import ENV_FILE
from ..schemas.models import (
    EnrichContent,
    EnrichPlan,
    EnrichSuggestion,
    FieldAnnotations,
    HistorySignal,
)

logger = logging.getLogger(__name__)

# Model + sampling. gpt-4o at T=0.2 matches the notebook; override via env.
MODEL = os.getenv("UC44_ENRICH_MODEL", "gpt-4o")
TEMPERATURE = float(os.getenv("UC44_ENRICH_TEMPERATURE", "0.2"))

# Rough USD price per 1M tokens (input, output) — for the budget hint only.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


class EnrichmentError(Exception):
    """Base for enrichment failures (router maps to HTTP 502)."""


class EnrichmentConfigError(EnrichmentError):
    """Missing/invalid API key or config (router maps to HTTP 503)."""


# --- OpenAI client (mirrors services/embeddings.py) -------------------------

_client: OpenAI | None = None
_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                key = os.getenv("OPENAI_API_KEY")
                # The container sets OPENAI_API_KEY="" (empty default); fall back
                # to the baked-in models/.env with override=True, mirroring how
                # the standalone models and embeddings.py resolve the key.
                if not key and ENV_FILE.exists():
                    load_dotenv(ENV_FILE, override=True)
                    key = os.getenv("OPENAI_API_KEY")
                if not key:
                    raise EnrichmentConfigError(
                        "OPENAI_API_KEY ist nicht gesetzt — bitte den Schlüssel in "
                        "app/.env oder Use Case/models/.env hinterlegen."
                    )
                _client = OpenAI(api_key=key)
    return _client


# --- prompts (verbatim base from the notebook) ------------------------------

SYSTEM_BASE = (
    "Du bist ein erfahrener Beschaffungs- und Stammdaten-Experte für ein\n"
    "deutsches Verkehrsunternehmen. Deine Aufgabe ist es, Beschreibungen und\n"
    "Beispiele für Warengruppen zu generieren oder behutsam zu verbessern.\n"
    "\n"
    "Antworte ausschließlich mit gültigem JSON nach folgendem Schema (alle\n"
    'Schlüssel sind Pflicht, "diff_kurz" darf null sein):\n'
    "\n"
    "{\n"
    '  "beschreibung": "1 bis 3 Sätze in deutscher Sprache",\n'
    '  "enthalten": ["3 bis 6 konkrete Einschluss-Beispiele"],\n'
    '  "nicht_enthalten": ["2 bis 4 typische Abgrenzungen"],\n'
    '  "konfidenz": 0-100,\n'
    '  "anmerkung": "optional, ein Satz bei Mehrdeutigkeit oder leer",\n'
    '  "status": "neu" | "verbessert" | "unverändert" | "ergänzung_beispiele",\n'
    '  "diff_kurz": "Satz oder null"\n'
    "}\n"
    "\n"
    "Allgemeine Regeln (gelten in allen Modi):\n"
    "- Sprache Deutsch.\n"
    "- Erfinde keine konkreten Lieferanten- oder Produktnamen\n"
    '  (kein "eCitaro", "Hectronic", "Siemens", "MAN", "Mercedes" usw.),\n'
    "  außer sie stehen wörtlich in der vorhandenen Beschreibung oder im Namen.\n"
    "- Erfinde keine konkreten Emissionsfaktoren oder Mengenangaben.\n"
    '- Wenn der Warengruppen-Name zu generisch ist (z. B. "Sonstiges Material",\n'
    '  "Gebühren, sonstige"), setze die Konfidenz auf höchstens 50 und\n'
    '  schreibe in "anmerkung" "Interpretation unsicher".'
)

# HOCHBAHN-internal acronyms that mode `neu` must never invent (only echo if in
# the name) and mode `ergänzen` must preserve verbatim.
_EIGENKUERZEL = "ATG, HADAG, FFG, HHA, BBM, SPNV, P+R, U5, U4HoGe, HHA1"

# Per-(field, action) directive text. Faithful to the notebook's mode prompts,
# decomposed to the field level so a plan can mix them freely.
_DIRECTIVE: dict[tuple[str, str], str] = {
    ("beschreibung", "neu"): (
        'Feld "beschreibung" — NEU: Erstelle eine prägnante, generische, '
        "branchenübliche Beschreibung (1–3 Sätze) allein aus dem Namen. "
        f"Anti-Halluzinations-Regel: Erfinde KEINE HOCHBAHN-internen Eigenkürzel "
        f"({_EIGENKUERZEL}) und keine Eigennamen, außer sie stehen wörtlich im "
        "Namen. Die Stilbeispiele dienen NUR als Stil-Anker (Tonalität, "
        "Satzlänge, Listenform) — übernimm nichts inhaltlich aus ihnen."
    ),
    ("beschreibung", "ergänzen"): (
        'Feld "beschreibung" — BEHUTSAM VERBESSERN: Default ist unverändert '
        "(Zeichen für Zeichen identisch, status=\"unverändert\"). Ändere den Text "
        "NUR bei einem harten Trigger (Tippfehler, fehlerhafte Zeichensetzung, "
        "Grammatikbruch). Reine Reformulierung, Rahmensätze oder Stilgeschmack "
        "sind KEINE Trigger. Erhalte alle fachlichen Aussagen und alle Eigenkürzel "
        f"({_EIGENKUERZEL}) WÖRTLICH. Keine neuen Lieferanten-/Produktnamen."
    ),
    ("beschreibung", "lassen"): (
        'Feld "beschreibung" — UNVERÄNDERT: Gib die vorhandene Beschreibung '
        "Zeichen für Zeichen unverändert zurück."
    ),
    ("examples_enthalten", "neu"): (
        'Feld "enthalten" — NEU: 3–6 konkrete Einschluss-Beispiele, abgeleitet '
        "aus Name und (sofern vorhanden) Beschreibung."
    ),
    ("examples_enthalten", "ergänzen"): (
        'Feld "enthalten" — ERGÄNZEN: Behalte die vorhandenen Einschluss-Beispiele '
        "und ergänze sinnvolle fehlende. Keine Dubletten, nichts streichen."
    ),
    ("examples_enthalten", "lassen"): (
        'Feld "enthalten" — UNVERÄNDERT: Gib die vorhandenen Einschluss-Beispiele '
        "unverändert zurück."
    ),
    ("examples_nicht_enthalten", "neu"): (
        'Feld "nicht_enthalten" — NEU: 2–4 typische Abgrenzungen (was gehört '
        "ausdrücklich NICHT in diese Warengruppe)."
    ),
    ("examples_nicht_enthalten", "ergänzen"): (
        'Feld "nicht_enthalten" — ERGÄNZEN: Behalte die vorhandenen Abgrenzungen '
        "und ergänze sinnvolle fehlende. Keine Dubletten, nichts streichen."
    ),
    ("examples_nicht_enthalten", "lassen"): (
        'Feld "nicht_enthalten" — UNVERÄNDERT: Gib die vorhandenen Abgrenzungen '
        "unverändert zurück."
    ),
}

# Style anchors — injected ONLY when the description is generated fresh (`neu`),
# so an existing description never gets contaminated with foreign examples.
_FEW_SHOTS = [
    {
        "wg_name": "Dieselkraftstoffe",
        "beschreibung": (
            "Diesel für Busse und Fähren einschließlich der internen "
            "Verrechnung der Dieselkosten zwischen den HOCHBAHN-Tochter- "
            "und Schwestergesellschaften."
        ),
        "enthalten": [
            "Diesel für Busse",
            "Diesel für Fähren",
            "Interne Verrechnung Dieselkosten zwischen Konzerngesellschaften",
        ],
        "nicht_enthalten": ["Tankkarten-Abrechnung", "Betankung von Mietwagen"],
    },
    {
        "wg_name": "Heizöl (Busse)",
        "beschreibung": (
            "Diesel für die Heizanlage in Bussen einschließlich der internen "
            "Verrechnung der Heizöl-Kosten zwischen Konzerngesellschaften."
        ),
        "enthalten": [
            "Heizöl für Bus-Heizanlagen",
            "Interne Verrechnung Heizöl-Kosten Busse",
        ],
        "nicht_enthalten": [
            "Heizöl für Gebäude-Heizungsanlagen",
            "Diesel zur Antriebsbetankung",
        ],
    },
    {
        "wg_name": "Heizöl (Heizanlagen)",
        "beschreibung": (
            "Heizöl nach DIN EN 590 zur Beheizung von Gebäuden und Liegenschaften."
        ),
        "enthalten": [
            "Heizöl DIN EN 590 für Gebäudeheizungen",
            "Heizöl für Werkstatt- und Betriebshofgebäude",
        ],
        "nicht_enthalten": ["Heizöl für Bus-Heizanlagen", "Erdgas und Fernwärme"],
    },
]


def _few_shots_block() -> str:
    parts = []
    for i, s in enumerate(_FEW_SHOTS, 1):
        parts.append(
            f"Stilbeispiel {i}:\n"
            f"  Name: {s['wg_name']}\n"
            f"  Beschreibung: {s['beschreibung']}\n"
            f"  enthalten: {json.dumps(s['enthalten'], ensure_ascii=False)}\n"
            f"  nicht_enthalten: {json.dumps(s['nicht_enthalten'], ensure_ascii=False)}"
        )
    return "\n\n".join(parts)


_REFINE_ADDENDUM = (
    "Modus: Einarbeitung von Feedback.\n"
    "Du erhältst den aktuellen Vorschlag und Anmerkungen der Fachperson pro Feld. "
    "Arbeite die Anmerkungen präzise ein. Ein Feld ohne Anmerkung nur ändern, wenn "
    "eine Anmerkung es erkennbar betrifft — sonst wörtlich unverändert lassen. "
    "Halte alle globalen Regeln (keine erfundenen Marken, Eigenkürzel wörtlich) ein."
)


# --- helpers ----------------------------------------------------------------

def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items) if items else "—"


def _coerce_list(value) -> list[str]:
    """Normalise an LLM example field to a clean list of non-empty strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [ln.strip(" -\t").strip() for ln in value.splitlines() if ln.strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _as_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    price = _PRICE_PER_MTOK.get(model)
    if not price:
        return None
    p_in, p_out = price
    return round(prompt_tokens / 1e6 * p_in + completion_tokens / 1e6 * p_out, 6)


def _extract_json(raw: str) -> dict:
    """Parse the first complete JSON object from the model output.

    Tolerates markdown fences (```json ... ```) the model sometimes emits despite
    the response_format instruction — same approach as the standalone
    ``scripts/llm_caller.py``.
    """
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    if start == -1:
        raise EnrichmentError("Keine JSON-Antwort vom Modell erhalten.")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as exc:
                    raise EnrichmentError(f"Ungültiges JSON vom Modell: {exc}") from exc
    raise EnrichmentError("JSON-Antwort des Modells ist unvollständig.")


def _call(system_prompt: str, user_prompt: str) -> tuple[dict, int, int]:
    """One chat completion → (parsed_json, prompt_tokens, completion_tokens)."""
    client = _get_client()
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = resp.choices[0].message.content or ""
            parsed = _extract_json(content)
            usage = resp.usage
            pt = int(getattr(usage, "prompt_tokens", 0) or 0)
            ct = int(getattr(usage, "completion_tokens", 0) or 0)
            return parsed, pt, ct
        except EnrichmentError as exc:  # parse failure → one retry
            last_err = exc
            continue
        except Exception as exc:  # noqa: BLE001 — API/network error
            raise EnrichmentError(f"LLM-Aufruf fehlgeschlagen: {exc}") from exc
    raise last_err or EnrichmentError("LLM-Aufruf fehlgeschlagen.")


def build_history_block(history: Optional[HistorySignal]) -> str:
    """Directional hint block: influx → include-side, outflux → exclude-side."""
    if history is None:
        return ""
    lines: list[str] = []
    if history.top_influx:
        lines.append(
            "Diese Positionen wurden von Fachpersonen manuell IN diese Warengruppe "
            'umgruppiert — Beschreibung und "enthalten" sollten sie inhaltlich abdecken:'
        )
        for it in history.top_influx:
            extra = f", Σ {it.betrag_eur:.0f} €" if it.betrag_eur else ""
            lines.append(f"- {it.text} ({it.count}×{extra})")
        lines.append("")
    if history.top_outflux:
        lines.append(
            "Diese Positionen wurden manuell aus dieser Warengruppe HERAUS korrigiert "
            '— "nicht_enthalten"/Abgrenzung sollte sie ausschließen:'
        )
        for it in history.top_outflux:
            extra = f", Σ {it.betrag_eur:.0f} €" if it.betrag_eur else ""
            lines.append(f"- {it.text} ({it.count}×{extra})")
        lines.append("")
    if not lines:
        return ""
    return (
        "### Hinweis: historische manuelle Korrekturen\n"
        "Verallgemeinere diese Muster; übernimm KEINE Einzeltexte wörtlich.\n"
        + "\n".join(lines)
    )


def _system_prompt(plan: EnrichPlan) -> str:
    directives = [
        _DIRECTIVE[("beschreibung", plan.beschreibung)],
        _DIRECTIVE[("examples_enthalten", plan.examples_enthalten)],
        _DIRECTIVE[("examples_nicht_enthalten", plan.examples_nicht_enthalten)],
    ]
    return (
        SYSTEM_BASE
        + "\n\nModus: feldbezogene Bearbeitung. Bearbeite jedes Feld gemäß seiner "
        "Regel; gib immer alle Schlüssel des Schemas zurück:\n"
        + "\n".join(f"- {d}" for d in directives)
    )


def _user_prompt(
    wg_name: str,
    content: EnrichContent,
    plan: EnrichPlan,
    history: Optional[HistorySignal],
) -> str:
    parts = [f"Warengruppen-Name: {wg_name}"]
    if content.beschreibung:
        parts.append(f"Vorhandene Beschreibung:\n{content.beschreibung}")
    if content.examples_enthalten:
        parts.append("Vorhandene Einschluss-Beispiele:\n" + _bullets(content.examples_enthalten))
    if content.examples_nicht_enthalten:
        parts.append("Vorhandene Abgrenzungen:\n" + _bullets(content.examples_nicht_enthalten))
    if plan.beschreibung == "neu":
        parts.append(_few_shots_block())
    hist = build_history_block(history)
    if hist:
        parts.append(hist)
    parts.append("Bearbeite die Felder gemäß den Modus-Regeln. Antworte als JSON nach Schema.")
    return "\n\n".join(parts)


# --- in-process cache (avoids double-billing repeat calls) -------------------

_cache: dict[str, EnrichSuggestion] = {}


def _cache_key(wg_name: str, content: EnrichContent, plan: EnrichPlan, history) -> str:
    hist_sig = ""
    if history is not None:
        hist_sig = json.dumps(
            [(i.text, i.count) for i in (history.top_influx + history.top_outflux)],
            ensure_ascii=False,
        )
    payload = json.dumps(
        {
            "wg": wg_name,
            "c": content.model_dump(),
            "p": plan.model_dump(),
            "h": hist_sig,
            "m": MODEL,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- public API -------------------------------------------------------------

def derive_plan(content: EnrichContent) -> EnrichPlan:
    """Auto plan from the current state: empty field → 'neu', filled → 'lassen'."""
    return EnrichPlan(
        beschreibung="lassen" if (content.beschreibung or "").strip() else "neu",
        examples_enthalten="lassen" if content.examples_enthalten else "neu",
        examples_nicht_enthalten="lassen" if content.examples_nicht_enthalten else "neu",
    )


def enrich_one(
    wg_name: str,
    content: EnrichContent,
    plan: Optional[EnrichPlan] = None,
    history: Optional[HistorySignal] = None,
) -> EnrichSuggestion:
    """Generate/improve one Warengruppe per the plan. Nothing is persisted."""
    plan = plan or derive_plan(content)
    history_used = bool(history and (history.top_influx or history.top_outflux))
    hist = history if history_used else None

    desc = content.beschreibung or None
    inc = list(content.examples_enthalten or [])
    exc = list(content.examples_nicht_enthalten or [])

    # All fields kept → nothing to ask the model.
    if {plan.beschreibung, plan.examples_enthalten, plan.examples_nicht_enthalten} == {"lassen"}:
        return EnrichSuggestion(
            beschreibung=desc, examples_enthalten=inc, examples_nicht_enthalten=exc,
            status="unverändert", diff_kurz="keine Änderung", plan=plan, history_used=False,
        )

    key = _cache_key(wg_name, content, plan, hist)
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    parsed, pt, ct = _call(_system_prompt(plan), _user_prompt(wg_name, content, plan, hist))

    out_desc = parsed.get("beschreibung")
    out_inc = _coerce_list(parsed.get("enthalten"))
    out_exc = _coerce_list(parsed.get("nicht_enthalten"))
    status = parsed.get("status") or None

    # Enforce 'lassen' (never trust the echo) and the notebook's strict-mode:
    # a 'ergänzen' description the model claims is unchanged is restored verbatim.
    if plan.beschreibung == "lassen":
        out_desc = desc
    elif plan.beschreibung == "ergänzen" and status == "unverändert" and desc is not None:
        out_desc = desc
    if plan.examples_enthalten == "lassen":
        out_inc = inc
    if plan.examples_nicht_enthalten == "lassen":
        out_exc = exc

    suggestion = EnrichSuggestion(
        beschreibung=(str(out_desc).strip() if out_desc else None),
        examples_enthalten=out_inc,
        examples_nicht_enthalten=out_exc,
        konfidenz=_as_int(parsed.get("konfidenz")),
        anmerkung=(parsed.get("anmerkung") or None),
        status=status,
        diff_kurz=(parsed.get("diff_kurz") or None),
        plan=plan,
        history_used=history_used,
        prompt_tokens=pt,
        completion_tokens=ct,
        cost_usd=_cost(MODEL, pt, ct),
    )
    with _lock:
        _cache[key] = suggestion
    return suggestion


def refine_one(
    wg_name: str,
    current: EnrichContent,
    annotations: FieldAnnotations,
    plan: Optional[EnrichPlan] = None,
    history: Optional[HistorySignal] = None,
) -> EnrichSuggestion:
    """Incorporate per-field annotations into the current draft (the 'refine' loop).

    Simpler than the offline ``process_overlay_review.py``: the annotations arrive
    already structured per field, so no comment classification is needed.
    """
    plan = plan or EnrichPlan(
        beschreibung="ergänzen", examples_enthalten="ergänzen", examples_nicht_enthalten="ergänzen"
    )
    history_used = bool(history and (history.top_influx or history.top_outflux))
    hist = history if history_used else None

    ann_lines = []
    if annotations.beschreibung:
        ann_lines.append(f"- Feld Beschreibung: {annotations.beschreibung}")
    if annotations.examples_enthalten:
        ann_lines.append(f"- Feld enthalten: {annotations.examples_enthalten}")
    if annotations.examples_nicht_enthalten:
        ann_lines.append(f"- Feld nicht_enthalten: {annotations.examples_nicht_enthalten}")
    if not ann_lines:
        # Nothing to incorporate → echo the current draft as the suggestion.
        return EnrichSuggestion(
            beschreibung=current.beschreibung or None,
            examples_enthalten=list(current.examples_enthalten or []),
            examples_nicht_enthalten=list(current.examples_nicht_enthalten or []),
            status="unverändert", diff_kurz="keine Anmerkungen", plan=plan,
            history_used=False,
        )

    user_parts = [
        f"Warengruppen-Name: {wg_name}",
        "Aktueller Vorschlag:\n"
        f"Beschreibung: {current.beschreibung or '—'}\n"
        f"enthalten:\n{_bullets(list(current.examples_enthalten or []))}\n"
        f"nicht_enthalten:\n{_bullets(list(current.examples_nicht_enthalten or []))}",
        "Anmerkungen der Fachperson:\n" + "\n".join(ann_lines),
    ]
    hist_block = build_history_block(hist)
    if hist_block:
        user_parts.append(hist_block)
    user_parts.append("Arbeite die Anmerkungen ein und antworte als JSON nach Schema.")

    parsed, pt, ct = _call(SYSTEM_BASE + "\n\n" + _REFINE_ADDENDUM, "\n\n".join(user_parts))

    return EnrichSuggestion(
        beschreibung=(str(parsed.get("beschreibung")).strip() if parsed.get("beschreibung") else None),
        examples_enthalten=_coerce_list(parsed.get("enthalten")),
        examples_nicht_enthalten=_coerce_list(parsed.get("nicht_enthalten")),
        konfidenz=_as_int(parsed.get("konfidenz")),
        anmerkung=(parsed.get("anmerkung") or None),
        status=(parsed.get("status") or "verbessert"),
        diff_kurz=(parsed.get("diff_kurz") or None),
        plan=plan,
        history_used=history_used,
        prompt_tokens=pt,
        completion_tokens=ct,
        cost_usd=_cost(MODEL, pt, ct),
    )
