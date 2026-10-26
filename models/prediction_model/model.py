"""Warengruppe prediction model.

Given an invoice line's pre-classification fields, predict one Warengruppe
from a fixed catalog using a single LLM call. The catalog is injected into
the prompt so the model must pick an exact string from the provided list.

No label-derived columns (Warengruppe, Kostenart, WG_Bezeichnung, EF_*, ...)
are read from the input row -- see config.yml `input_columns`.
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


@dataclass
class Prediction:
    warengruppe: str | None
    confidence: str       # "hoch" | "mittel" | "niedrig" | "error"
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
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _resolve_api_key(cfg_api_key_env: str) -> str:
    for var in ("LLM_API_KEY", cfg_api_key_env, "OPENAI_API_KEY"):
        if var and os.getenv(var):
            return os.getenv(var)  # type: ignore[return-value]
    raise RuntimeError(
        f"No API key found. Set LLM_API_KEY, {cfg_api_key_env} or OPENAI_API_KEY in .env."
    )


def _examples_hint_prediction(catalog: WarengruppenCatalog) -> str:
    """Hint that explains the ENTHÄLT:/NICHT: markers in the catalog string.

    Empty when the catalog carries no examples (baseline / overlay_desc).
    """
    if not catalog.has_any_examples:
        return ""
    if catalog.has_examples_enthalten and catalog.has_examples_nicht_enthalten:
        sections = '"ENTHÄLT:" (typisch dazugehörig) und "NICHT:" (bewusst ausgeschlossen)'
    elif catalog.has_examples_enthalten:
        sections = '"ENTHÄLT:" (typisch dazugehörig)'
    else:
        sections = '"NICHT:" (bewusst ausgeschlossen)'
    return (
        f"\n\nDie Liste enthält pro Warengruppe optional Beispiele unter "
        f"{sections}. Nutze sie zur Disambiguierung, leite daraus aber "
        "keine starren Regeln ab."
    )


# --------------------------------------------------------------------------- #
#  The model                                                                  #
# --------------------------------------------------------------------------- #


class PredictionModel:
    """LLM-backed Warengruppe classifier."""

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

        api_key = _resolve_api_key(llm_cfg.get("api_key_env", "OPENAI_API_KEY"))
        self.client = OpenAI(api_key=api_key, base_url=llm_cfg["base_url"])
        self.model = llm_cfg["model"]
        self.temperature = llm_cfg.get("temperature", 0)

        self.columns = config["input_columns"]
        # The raw system prompt has an `{examples_hint}` placeholder; the
        # final value is set in prepare_catalog() so the hint matches the
        # actual catalog content.
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

        # Populated by prepare_catalog().
        self.catalog: WarengruppenCatalog | None = None
        self._catalog_str: str = ""
        self._catalog_hash: str = ""

        self._usage_lock = threading.Lock()

    # -- catalog -------------------------------------------------------------

    def prepare_catalog(self, catalog: WarengruppenCatalog) -> None:
        """Cache the rendered catalog string so each row reuses it."""
        self.catalog = catalog
        self._catalog_str = catalog.render_for_prediction()
        self._catalog_hash = catalog.catalog_hash()
        # Use replace (not str.format) because the system prompt contains
        # literal `{` / `}` for JSON examples that would break str.format.
        self.system_prompt = self._raw_system_prompt.replace(
            "{examples_hint}", _examples_hint_prediction(catalog)
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

        Keyed on what is actually sent (model, full rendered messages incl.
        catalog/template/hint, response_format, temperature), the key cannot
        drift from the call: anything that would change the API answer misses
        the cache automatically. The cached VALUE is the raw response only —
        parsing/resolution runs on every read with the current code and
        catalog, so a fixed matcher or a renamed catalog entry heals cached
        rows retroactively instead of being frozen at write time.
        """
        blob = json.dumps(request, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    # -- prompt building -----------------------------------------------------

    def _extract(self, row: pd.Series) -> dict:
        """Pull configured (pre-prediction) columns out of a row."""
        def s(col_alias: str) -> str:
            col = self.columns.get(col_alias)
            if col is None:
                return "-"
            val = row.get(col)
            # pd.isna covers None, float NaN, and pd.NA -- string/Int64 columns
            # can surface any of them depending on dtype.
            if val is None or pd.isna(val):
                return "-"
            return str(val).strip() or "-"

        zusatz = " | ".join(
            v for v in (s("zusatz_1"), s("zusatz_2")) if v != "-"
        ) or "-"

        # Per requirement 3.1 neither the price (wert/waehrung) nor the booking
        # date (datum) feed the classifier -- they are intentionally not part
        # of the payload. Dropping them here also changes the cache key, so
        # predictions cached while date/price were still in the prompt are not
        # silently reused.
        return {
            "bestelltext": s("bestelltext"),
            "bezeichnung": s("bezeichnung"),
            "objektbezeichnung": s("objektbezeichnung"),
            "zusatz": zusatz,
            "menge": s("menge"),
            "einheit": s("einheit"),
        }

    # -- response parsing ----------------------------------------------------

    def _build_prediction(self, raw: str) -> Prediction:
        """Parse a raw LLM response into a Prediction.

        Resolves the returned Warengruppe against the catalog tolerantly (see
        ``WarengruppenCatalog.resolve`` — handles enumeration prefixes,
        whitespace/dash noise, casing and ß/ss) and stores the *canonical*
        catalog name, so a valid answer is never dropped over a formatting
        mismatch. Returns ``warengruppe=None`` only when the answer maps to no
        catalog entry (or the JSON is unparseable).
        """
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return Prediction(
                warengruppe=None, confidence="error", reason="parse_error", raw=raw
            )
        wg_raw = str(parsed.get("warengruppe", "")).strip()
        wg = self.catalog.resolve(wg_raw) if self.catalog is not None else (wg_raw or None)
        return Prediction(
            warengruppe=wg,
            confidence=str(parsed.get("confidence", "unknown")),
            reason=str(parsed.get("begruendung", "")),
            raw=raw,
        )

    # -- single request ------------------------------------------------------

    def predict_row(self, row: pd.Series, extra_hint: str = "") -> Prediction:
        if not self._catalog_str:
            raise RuntimeError("Call prepare_catalog() before predict_row().")

        payload = self._extract(row)
        user_prompt = self.user_template.format(
            catalog=self._catalog_str, **payload
        )
        # Additive per-row context (e.g. retrieved similar confirmed cases),
        # appended after the question. Empty by default → unchanged behaviour.
        if extra_hint:
            user_prompt = f"{user_prompt}\n\n{extra_hint}"

        request = self._request(user_prompt)
        cache_path = self._cache_path(self._cache_key(request))

        if cache_path.exists():
            with cache_path.open() as fh:
                cached = json.load(fh)
            raw_cached = str(cached.get("raw") or "")
            if raw_cached:
                with self._usage_lock:
                    self.usage.cache_hits += 1
                return self._build_prediction(raw_cached)

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
        return self._build_prediction(raw)

    # -- batch ---------------------------------------------------------------

    def predict(
        self,
        df: pd.DataFrame,
        max_rows: int | None = None,
        workers: int = 1,
        progress: bool = True,
        hint_provider=None,
    ) -> pd.DataFrame:
        """`hint_provider(row) -> str` optionally returns extra per-row prompt
        context (retrieved similar cases). None / "" → unchanged behaviour."""

        def _hint(row) -> str:
            if hint_provider is None:
                return ""
            try:
                return hint_provider(row) or ""
            except Exception:  # noqa: BLE001 — a hint failure must never break prediction
                return ""

        out = df.copy()
        out["predicted_warengruppe"] = pd.array([pd.NA] * len(out), dtype="string")
        out["confidence"] = pd.array([pd.NA] * len(out), dtype="string")
        out["reason"] = pd.array([pd.NA] * len(out), dtype="string")
        out["overlay_status_used"] = pd.array([pd.NA] * len(out), dtype="string")
        out["overlay_konfidenz_used"] = pd.array([pd.NA] * len(out), dtype="Int64")

        rows = list(out.iterrows())
        if max_rows is not None:
            rows = rows[:max_rows]

        def _apply_success(idx, result) -> None:
            out.at[idx, "predicted_warengruppe"] = result.warengruppe
            out.at[idx, "confidence"] = result.confidence
            out.at[idx, "reason"] = result.reason
            if result.warengruppe and self.catalog is not None:
                entry = self.catalog.lookup(result.warengruppe)
                if entry is not None:
                    if entry.status is not None:
                        out.at[idx, "overlay_status_used"] = entry.status
                    if entry.konfidenz is not None:
                        out.at[idx, "overlay_konfidenz_used"] = entry.konfidenz

        def _apply_error(idx, exc) -> None:
            out.at[idx, "predicted_warengruppe"] = pd.NA
            out.at[idx, "confidence"] = "error"
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
                    result = self.predict_row(row, _hint(row))
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
            future_to_idx = {
                ex.submit(self.predict_row, row, _hint(row)): idx for idx, row in rows
            }
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
