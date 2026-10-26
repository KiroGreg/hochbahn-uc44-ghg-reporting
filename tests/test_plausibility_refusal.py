"""Refusal-path tests for the plausibility model.

Synthetic input rows whose `Warengruppe` is missing (NaN) or unknown to the
catalog must NOT trigger an LLM call -- they are marked confidence=
"not_assessable" so a CSRD audit can distinguish them from real "plausible"
verdicts. Run from repo root:

    .venv/bin/python -m unittest tests.test_plausibility_refusal -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Use Case" / "models"))
sys.path.insert(0, str(ROOT / "Use Case" / "models" / "plausibility_model"))

# load_dotenv inside PlausibilityModel.__init__ may overwrite this; we set it
# again right before instantiation in setUp().
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")

from plausibility_model.model import PlausibilityModel, load_config  # noqa: E402


CONFIG_PATH = ROOT / "Use Case" / "models" / "plausibility_model" / "config.yml"


class _CallCounter:
    """Stand-in for client.chat.completions.create that fails the test if invoked."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError(
            "LLM should not be called for refused rows (confidence=not_assessable)"
        )


class TestPlausibilityRefusal(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-fake"
        cfg = load_config(CONFIG_PATH)
        self.model = PlausibilityModel(config=cfg, env_path=None)
        self.counter = _CallCounter()
        # Replace the OpenAI client method so we can prove no call happens.
        self.model.client.chat.completions.create = self.counter

    def _row(self, **overrides) -> pd.Series:
        row = {
            "Bestelltext": "Some invoice text",
            "Bezeichnung": "Some line",
            "Objektbezeichnung": "Some object",
            "Bezeichnung.1": "",
            "Bezeichnung.2": "",
            "wg_name": pd.NA,
            "wg_description": pd.NA,
            "wg_examples_enthalten": "",
            "wg_examples_nicht_enthalten": "",
        }
        row.update(overrides)
        return pd.Series(row)

    def test_missing_wg_returns_not_assessable(self) -> None:
        result = self.model.predict_row(self._row())
        self.assertIsNone(result.plausibilitaet)
        self.assertEqual(result.confidence, "not_assessable")
        self.assertEqual(result.reason, "warengruppe_missing_or_unknown")
        self.assertEqual(result.unterstuetzende_signale, [])
        self.assertEqual(result.widersprechende_signale, [])
        self.assertEqual(self.counter.calls, 0)

    def test_present_wg_does_not_short_circuit(self) -> None:
        # When wg_name is present the refusal path must NOT trigger; the call
        # would normally proceed to the LLM, so our stub raises AssertionError.
        with self.assertRaises(AssertionError):
            self.model.predict_row(self._row(wg_name="Dieselkraftstoffe"))
        self.assertEqual(self.counter.calls, 1)

    def test_predict_batch_marks_overlay_status_sentinel(self) -> None:
        df = pd.DataFrame(
            [
                self._row().to_dict(),  # missing -> not_assessable
                self._row(wg_name="Dieselkraftstoffe").to_dict(),  # would call
            ]
        )
        # Need this column present (would normally come from the catalog merge).
        df["wg_status_overlay"] = pd.NA

        # For the second row we want the "real" path to error out (no API key);
        # patch the API client to raise, so predict() routes it through the
        # generic error branch -- still proving the first row is the refusal.
        def boom(*a, **kw):
            raise RuntimeError("api unavailable in test")

        self.model.client.chat.completions.create = boom
        out = self.model.predict(df)
        self.assertEqual(out.at[0, "confidence"], "not_assessable")
        self.assertEqual(out.at[0, "wg_status_overlay"], "warengruppe_missing")
        self.assertEqual(out.at[1, "confidence"], "error")  # api_error path


if __name__ == "__main__":
    unittest.main()
