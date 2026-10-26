"""Cache-Regressionstests für das Prediction-Modell (ohne API-Calls).

Seit dem Umbau (2026-07-21) gilt: Der Cache-Key ist der SHA-256 über den
EXAKTEN OpenAI-Request; gespeichert wird NUR die rohe Antwort. Die
Interpretation (JSON-Parse + Katalog-resolve) läuft bei jedem LESEN neu,
damit Matcher-/Katalog-Fixes gecachte Zeilen rückwirkend heilen, statt
zum Schreibzeitpunkt eingefroren zu werden.

Run from repo root:
    .venv/bin/python -m unittest tests.test_model_cache -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Use Case" / "models"))

from _shared.catalog import load_warengruppen  # noqa: E402
from prediction_model.model import PredictionModel, UsageStats  # noqa: E402

DATA_DIR = ROOT / "Use Case"

# Antwort mit der Komma-Variante des Live-Falls vom 21.07.: der Katalog
# schreibt "DL Wartung …" ohne Komma — die Auflösung muss beim Lesen aus
# dem raw-Feld passieren, nicht aus einem eingefrorenen Feld im Cache.
RAW_COMMA = json.dumps(
    {
        "warengruppe": "DL, Wartung und Instandhaltung von Nutzerspezifische techn. Anlagen",
        "confidence": "hoch",
        "begruendung": "Testfall",
    },
    ensure_ascii=False,
)
CANONICAL = "DL Wartung und Instandhaltung von Nutzerspezifische techn. Anlagen"


class _StubClient:
    """Zählt Calls und liefert eine feste rohe Antwort."""

    def __init__(self, raw: str) -> None:
        self.calls = 0
        self.last_request: dict | None = None

        def _create(**request):
            self.calls += 1
            self.last_request = request
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=raw))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            )

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def _make_model(cache_dir: Path, raw: str) -> PredictionModel:
    """PredictionModel ohne __init__ (kein API-Key nötig), minimal verdrahtet."""
    m = PredictionModel.__new__(PredictionModel)
    m.model = "test-model"
    m.temperature = 0
    m.columns = {"bestelltext": "Bestelltext"}
    m._raw_system_prompt = "sys {examples_hint}"
    m.system_prompt = ""
    m.user_template = "Katalog:\n{catalog}\nBestelltext: {bestelltext}"
    m.cache_dir = cache_dir
    m.budget_usd = 10.0
    m.usage = UsageStats(price_input_per_1m=1.0, price_output_per_1m=1.0)
    m._usage_lock = threading.Lock()
    m.client = _StubClient(raw)
    m.prepare_catalog(load_warengruppen(DATA_DIR, {"variant": "baseline"}))
    return m


class TestPredictionCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.model = _make_model(Path(self._tmp.name), RAW_COMMA)
        self.row = pd.Series({"Bestelltext": "Prüfdienst"})

    def tearDown(self):
        self._tmp.cleanup()

    def test_cache_value_is_raw_only(self):
        self.model.predict_row(self.row)
        files = list(Path(self._tmp.name).glob("*.json"))
        self.assertEqual(len(files), 1)
        cached = json.loads(files[0].read_text())
        self.assertEqual(set(cached), {"raw"})
        self.assertEqual(cached["raw"], RAW_COMMA)

    def test_cache_hit_skips_api_and_reparses(self):
        first = self.model.predict_row(self.row)
        second = self.model.predict_row(self.row)
        self.assertEqual(self.model.client.calls, 1)
        self.assertEqual(self.model.usage.cache_hits, 1)
        # Aufgelöst wird beim Lesen aus raw — beide Male auf den kanonischen
        # Katalognamen, obwohl der Cache keinen aufgelösten Namen speichert.
        self.assertEqual(first.warengruppe, CANONICAL)
        self.assertEqual(second.warengruppe, CANONICAL)

    def test_key_is_exact_request(self):
        self.model.predict_row(self.row)
        req = self.model.client.last_request
        expected = self.model._cache_key(req)
        files = list(Path(self._tmp.name).glob("*.json"))
        self.assertEqual(files[0].stem, expected)

    def test_hint_changes_key(self):
        self.model.predict_row(self.row)
        self.model.predict_row(self.row, extra_hint="Ähnlicher Fall: …")
        self.assertEqual(self.model.client.calls, 2)
        self.assertEqual(len(list(Path(self._tmp.name).glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
