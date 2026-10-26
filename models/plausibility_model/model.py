"""Plausibility model.

Ask an LLM, for each invoice line, whether the current Warengruppe
assignment is consistent with the free-text fields.

Configuration lives in config.yml. The prompt template, model, budget and
input column mapping are all declared there -- this file is pure logic.

Domain column names (Warengruppe, Bestelltext, ...) are kept in German
because they match the source Excel headers.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _shared.catalog import WarengruppenCatalog  # noqa: E402


# --------------------------------------------------------------------------- #
#  Data structures                                                            #
# --------------------------------------------------------------------------- #


VALID_PLAUSIBILITAET = {"plausibel", "implausibel", "unklar"}


@dataclass
class Prediction:
    # "plausibel" | "implausibel" | "unklar" | "error" | None (Refusal-Pfad)
    plausibilitaet: str | None
    confidence: str           # "hoch" | "mittel" | "niedrig" | "error" | "not_assessable"
    unterstuetzende_signale: list[str]
    widersprechende_signale: list[str]
    reason: str
    raw: str


@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    cache_hits: int = 0
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * self.price_input_per_1m
            + self.output_tokens / 1_000_000 * self.price_output_per_1m
        )


class BudgetExceeded(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
#  Config loading                                                             #
# --------------------------------------------------------------------------- #


def load_config(path: str | Path) -> dict:
    """Load config.yml as a plain dict."""
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _resolve_api_key(cfg_api_key_env: str) -> str:
    """Resolve the API key from env vars.

    Priority: LLM_API_KEY > <configured var> > OPENAI_API_KEY.
    """
    for var in ("LLM_API_KEY", cfg_api_key_env, "OPENAI_API_KEY"):
        if var and os.getenv(var):
            return os.getenv(var)  # type: ignore[return-value]
    raise RuntimeError(
        f"No API key found. Set LLM_API_KEY, {cfg_api_key_env} or OPENAI_API_KEY in .env."
    )


def _coerce_signal_list(value: object) -> list[str]:
    """LLM may return a list, a string, or None for the signal fields.

    We normalize to `list[str]`, dropping empties, so the dataclass and
    cache JSON shape stays stable across runs.
    """
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _format_examples_block(header: str, bullets_str: str) -> str:
    """Render an indented Markdown-style block, or empty string if no bullets.

    `bullets_str` is the raw value from the catalog merge -- a string like
    `"- a\\n- b"` or `"-"` / `""` for empty. The block is prefixed with a
    leading newline so it slots seamlessly into the user_template.
    """
    if not bullets_str or bullets_str.strip() in ("", "-"):
        return ""
    indented = "\n  ".join(bullets_str.splitlines())
    return f"\n  {header}\n  {indented}"


def _examples_hint_plausibility(catalog: WarengruppenCatalog) -> str:
    """Hint that points the model at the prose Beispiele/Ausschlüsse blocks.

    Empty when the catalog carries no examples (baseline / overlay_desc).
    """
    if not catalog.has_any_examples:
        return ""
    return (
        "\n\nDie Beschreibung der Warengruppe enthält gegebenenfalls typische "
        "Beispiele und Ausschlüsse – nutze beides bei deiner Bewertung."
    )


# --------------------------------------------------------------------------- #
#  The model                                                                  #
# --------------------------------------------------------------------------- #


class PlausibilityModel:
    """LLM-backed plausibility classifier.

    The heavy lifting (prompt, model, columns) is declared in config.yml so
    the same class can back different prompts or providers without code
    changes.
    """

    def __init__(
        self,
        config: dict,
        env_path: str | Path | None = None,
    ) -> None:
        if env_path:
            load_dotenv(env_path, override=True)
        else:
            load_dotenv()

        self.config = config
        llm_cfg = config["llm"]
        pricing_cfg = config["pricing"]

        api_key = _resolve_api_key(llm_cfg.get("api_key_env", "NEBIUS_API_KEY"))
        self.client = OpenAI(api_key=api_key, base_url=llm_cfg["base_url"])
        self.model = llm_cfg["model"]
        self.temperature = llm_cfg.get("temperature", 0)

        self.columns = config["input_columns"]
        # Raw template; the final value is set in prepare_catalog() so the
        # examples hint matches the catalog's actual content.
        self._raw_system_prompt = config["prompt"]["system"]
        self.system_prompt = ""
        self.user_template = config["prompt"]["user_template"]

        self.cache_dir = Path(config.get("cache", {}).get("dir", ".cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.budget_usd = float(pricing_cfg["budget_usd"])
        self.usage = UsageStats(
            price_input_per_1m=float(pricing_cfg["input_per_1m_usd"]),
            price_output_per_1m=float(pricing_cfg["output_per_1m_usd"]),
        )

        self.catalog: WarengruppenCatalog | None = None
        self._catalog_str: str = ""

        self._usage_lock = threading.Lock()

    # -- catalog -------------------------------------------------------------

    def prepare_catalog(self, catalog: WarengruppenCatalog) -> None:
        """Bind the catalog and render the full catalog string for the prompt."""
        self.catalog = catalog
        self._catalog_str = catalog.render_for_prediction()
        # Use replace (not str.format) because the system prompt contains
        # literal `{` / `}` for JSON examples that would break str.format.
        self.system_prompt = self._raw_system_prompt.replace(
            "{examples_hint}", _examples_hint_plausibility(catalog)
        )

    # -- cache ---------------------------------------------------------------

    def _request(self, user_prompt: str) -> dict:
        """The exact chat.completions payload that goes to OpenAI."""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": self.temperature,
        }

    def _cache_key(self, request: dict) -> str:
        """sha256 over the exact request bytes.

        Keyed on what is actually sent, the key cannot drift from the call.
        The cached VALUE is the raw response only — parsing runs on every
        read with the current code, so interpretation fixes heal cached rows
        retroactively instead of being frozen at write time.
        """
        blob = json.dumps(request, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    # -- prompt building -----------------------------------------------------

    def _extract(self, row: pd.Series) -> dict:
        """Pull configured columns out of a row, mapping missing values to '-'."""
        def s(col_alias: str) -> str:
            col = self.columns.get(col_alias)
            if col is None:
                return "-"
            val = row.get(col)
            # pd.isna handles None, float NaN, and pd.NA in one go -- left-merges
            # on object/string/Int64 columns can produce any of them.
            if val is None or pd.isna(val):
                return "-"
            return str(val).strip() or "-"

        zusatz = " | ".join(
            v for v in (s("zusatz_1"), s("zusatz_2")) if v != "-"
        ) or "-"

        wg_description = s("wg_description")
        description_block = (
            f"\n  Beschreibung: {wg_description}" if wg_description != "-" else ""
        )
        enthalten_block = _format_examples_block(
            "Enthält typischerweise:", s("wg_examples_enthalten")
        )
        nicht_enthalten_block = _format_examples_block(
            "Nicht enthalten sind:", s("wg_examples_nicht_enthalten")
        )

        return {
            "catalog": self._catalog_str,
            "bestelltext": s("bestelltext"),
            "bezeichnung": s("bezeichnung"),
            "objektbezeichnung": s("objektbezeichnung"),
            "zusatz": zusatz,
            "wg_name": s("wg_name"),
            "wg_description_block": description_block,
            "wg_examples_enthalten_block": enthalten_block,
            "wg_examples_nicht_enthalten_block": nicht_enthalten_block,
        }

    # -- single request ------------------------------------------------------

    def predict_row(self, row: pd.Series) -> Prediction:
        payload = self._extract(row)

        # Refuse rows without a usable Warengruppe before any API/cache work.
        # An invoice line whose `Warengruppe` is missing or not in the catalog
        # would otherwise be sent to the LLM as `Warengruppe: "-"`, which the
        # model tends to wave through as plausible -- a CSRD audit problem.
        if payload["wg_name"] == "-":
            return Prediction(
                plausibilitaet=None,
                confidence="not_assessable",
                unterstuetzende_signale=[],
                widersprechende_signale=[],
                reason="warengruppe_missing_or_unknown",
                raw="",
            )

        user_prompt = self.user_template.format(**payload)
        request = self._request(user_prompt)
        cache_path = self._cache_path(self._cache_key(request))

        if cache_path.exists():
            with cache_path.open() as fh:
                cached = json.load(fh)
            raw_cached = str(cached.get("raw") or "")
            if raw_cached:
                with self._usage_lock:
                    self.usage.cache_hits += 1
                return self._build_result(raw_cached)

        if self.usage.cost_usd >= self.budget_usd:
            raise BudgetExceeded(
                f"Budget exceeded: ${self.usage.cost_usd:.2f} >= ${self.budget_usd:.2f}"
            )

        response = self.client.chat.completions.create(**request)
        raw = response.choices[0].message.content or "{}"

        with self._usage_lock:
            if response.usage is not None:
                self.usage.input_tokens += response.usage.prompt_tokens or 0
                self.usage.output_tokens += response.usage.completion_tokens or 0
            self.usage.calls += 1

        # Atomar schreiben: zwei Threads dürfen nicht denselben halbfertigen
        # JSON sehen. Bei kollidierenden Keys (zwei identische Zeilen parallel)
        # ist das Ergebnis ohnehin idempotent. Gespeichert wird NUR die rohe
        # Antwort — interpretiert wird bei jedem Lesen neu (s. _cache_key).
        tmp_path = cache_path.with_suffix(f".json.tmp.{threading.get_ident()}")
        with tmp_path.open("w") as fh:
            json.dump({"raw": raw}, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, cache_path)
        return self._build_result(raw)

    def _build_result(self, raw: str) -> Prediction:
        """Map the German JSON keys of a raw response to the dataclass."""
        try:
            parsed = json.loads(raw)
            plaus_raw = str(parsed.get("plausibilitaet", "")).strip().lower()
            plausibilitaet = plaus_raw if plaus_raw in VALID_PLAUSIBILITAET else "unklar"
            return Prediction(
                plausibilitaet=plausibilitaet,
                confidence=str(parsed.get("confidence", "unknown")),
                unterstuetzende_signale=_coerce_signal_list(
                    parsed.get("unterstuetzende_signale")
                ),
                widersprechende_signale=_coerce_signal_list(
                    parsed.get("widersprechende_signale")
                ),
                reason=str(parsed.get("begruendung", "")),
                raw=raw,
            )
        except json.JSONDecodeError:
            return Prediction(
                plausibilitaet=None,
                confidence="error",
                unterstuetzende_signale=[],
                widersprechende_signale=[],
                reason="parse_error",
                raw=raw,
            )

    # -- batch ---------------------------------------------------------------

    def predict(
        self,
        df: pd.DataFrame,
        max_rows: int | None = None,
        workers: int = 1,
        progress: bool = True,
    ) -> pd.DataFrame:
        """Return a copy of df with plausibilitaet / confidence / signal columns.

        Stops gracefully if the budget is exceeded -- rows already processed
        keep their values.
        """
        out = df.copy()
        out["plausibilitaet"] = pd.array([pd.NA] * len(out), dtype="string")
        out["confidence"] = pd.array([pd.NA] * len(out), dtype="string")
        out["unterstuetzende_signale"] = pd.array([pd.NA] * len(out), dtype="string")
        out["widersprechende_signale"] = pd.array([pd.NA] * len(out), dtype="string")
        out["reason"] = pd.array([pd.NA] * len(out), dtype="string")

        rows = list(out.iterrows())
        if max_rows is not None:
            rows = rows[:max_rows]

        def _join_signals(items: list[str]) -> object:
            return " | ".join(items) if items else pd.NA

        def _apply_success(idx, result) -> None:
            out.at[idx, "plausibilitaet"] = result.plausibilitaet
            out.at[idx, "confidence"] = result.confidence
            out.at[idx, "unterstuetzende_signale"] = _join_signals(
                result.unterstuetzende_signale
            )
            out.at[idx, "widersprechende_signale"] = _join_signals(
                result.widersprechende_signale
            )
            out.at[idx, "reason"] = result.reason
            # Audit marker: NaN -> "warengruppe_missing" so the renamed
            # overlay_status_used column carries the sentinel into the Excel.
            if result.confidence == "not_assessable":
                out.at[idx, "wg_status_overlay"] = "warengruppe_missing"

        def _apply_error(idx, exc) -> None:
            out.at[idx, "plausibilitaet"] = pd.NA
            out.at[idx, "confidence"] = "error"
            out.at[idx, "unterstuetzende_signale"] = pd.NA
            out.at[idx, "widersprechende_signale"] = pd.NA
            out.at[idx, "reason"] = f"api_error: {exc!s}"[:200]

        def _print_progress(done: int) -> None:
            if progress and done % 25 == 0:
                u = self.usage
                print(
                    f"  [{done}] checked  |  api calls: {u.calls}  cache: {u.cache_hits}  "
                    f"tokens in/out: {u.input_tokens}/{u.output_tokens}  ~ ${u.cost_usd:.3f}"
                )

        if workers <= 1:
            for i, (idx, row) in enumerate(rows):
                try:
                    result = self.predict_row(row)
                except BudgetExceeded as exc:
                    print(f"WARN: {exc} -- stopping after {i} rows.")
                    break
                except Exception as exc:  # noqa: BLE001
                    _apply_error(idx, exc)
                    continue
                _apply_success(idx, result)
                _print_progress(i + 1)
            return out

        budget_stop = False
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_to_idx = {ex.submit(self.predict_row, row): idx for idx, row in rows}
            for fut in as_completed(future_to_idx):
                idx = future_to_idx[fut]
                done += 1
                try:
                    result = fut.result()
                except (BudgetExceeded, CancelledError) as exc:
                    if isinstance(exc, BudgetExceeded) and not budget_stop:
                        print(f"WARN: {exc} -- no new tasks; finishing in-flight.")
                        budget_stop = True
                        for f in future_to_idx:
                            if not f.running() and not f.done():
                                f.cancel()
                    continue
                except Exception as exc:  # noqa: BLE001
                    _apply_error(idx, exc)
                    _print_progress(done)
                    continue
                _apply_success(idx, result)
                _print_progress(done)
        return out
