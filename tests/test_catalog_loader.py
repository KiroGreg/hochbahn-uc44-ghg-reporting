"""Loader regression tests for `_shared/catalog.py`.

Pure unit tests -- no LLM call, no environment requirement beyond the
shared models venv. Run from repo root:

    .venv/bin/python -m unittest tests.test_catalog_loader -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Use Case" / "models"))

from _shared.catalog import (  # noqa: E402
    VALID_VARIANTS,
    WarengruppenCatalog,
    load_warengruppen,
    normalize_wg_key,
)


DATA_DIR = ROOT / "Use Case"


def _load(variant: str, **extra) -> WarengruppenCatalog:
    cfg = {"variant": variant}
    cfg.update(extra)
    return load_warengruppen(DATA_DIR, cfg)


class TestCatalogLoader(unittest.TestCase):
    def test_all_variants_load_192_rows(self):
        for v in VALID_VARIANTS:
            with self.subTest(variant=v):
                cat = _load(v)
                self.assertEqual(len(cat.rows), 192)
                self.assertEqual(cat.variant, v)

    def test_baseline_has_no_overlay_metadata(self):
        cat = _load("baseline")
        self.assertEqual(cat.overlay_hash, "")
        self.assertIsNone(cat.overlay_modell)
        self.assertIsNone(cat.overlay_datum_generierung)
        self.assertEqual(sum(len(r.examples_enthalten) for r in cat.rows), 0)
        self.assertEqual(sum(len(r.examples_nicht_enthalten) for r in cat.rows), 0)

    def test_baseline_keeps_master_gaps(self):
        # 62 master entries are blank; the loader must surface that.
        cat = _load("baseline")
        with_desc = sum(1 for r in cat.rows if r.description)
        self.assertEqual(with_desc, 130)

    def test_overlay_full_fills_all_descriptions(self):
        cat = _load("overlay_full")
        with_desc = sum(1 for r in cat.rows if r.description)
        self.assertEqual(with_desc, 192)
        self.assertEqual(cat.overlay_modell, "gpt-4o")
        self.assertTrue(cat.overlay_hash)

    def test_overlay_full_has_examples(self):
        cat = _load("overlay_full")
        ent = sum(len(r.examples_enthalten) for r in cat.rows)
        nicht = sum(len(r.examples_nicht_enthalten) for r in cat.rows)
        # Concrete numbers from the current overlay generation; they will move
        # if the overlay is regenerated. Asserting > 500 / > 300 keeps the test
        # stable across small drifts while still catching a breakage.
        self.assertGreater(ent, 500)
        self.assertGreater(nicht, 300)

    def test_overlay_inclusive_omits_exclusive_examples(self):
        cat = _load("overlay_inclusive")
        self.assertGreater(sum(len(r.examples_enthalten) for r in cat.rows), 0)
        self.assertEqual(sum(len(r.examples_nicht_enthalten) for r in cat.rows), 0)

    def test_overlay_desc_omits_all_examples(self):
        cat = _load("overlay_desc")
        self.assertEqual(sum(len(r.examples_enthalten) for r in cat.rows), 0)
        self.assertEqual(sum(len(r.examples_nicht_enthalten) for r in cat.rows), 0)

    def test_invalid_variant_raises(self):
        with self.assertRaises(ValueError):
            load_warengruppen(DATA_DIR, {"variant": "foo"})

    def test_invalid_on_missing_raises(self):
        with self.assertRaises(ValueError):
            load_warengruppen(
                DATA_DIR, {"variant": "overlay_full", "on_missing_overlay": "bogus"}
            )

    def test_lookup_returns_entry(self):
        cat = _load("overlay_full")
        entry = cat.lookup("Tischlerarbeiten")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "Tischlerarbeiten")
        self.assertEqual(entry.status, "neu")
        self.assertIsNotNone(entry.konfidenz)
        # wg_id must be carried but never leaked to the LLM (see next test).
        self.assertTrue(entry.wg_id)

    def test_lookup_unknown_returns_none(self):
        cat = _load("overlay_full")
        self.assertIsNone(cat.lookup("not-a-warengruppe"))

    def test_render_for_prediction_does_not_leak_wg_ids(self):
        cat = _load("overlay_full")
        rendered = cat.render_for_prediction()
        for entry in cat.rows:
            self.assertNotIn(
                entry.wg_id, rendered,
                f"hashed wg_id {entry.wg_id!r} leaked into the LLM prompt",
            )

    def test_render_includes_examples_when_overlay_full(self):
        cat = _load("overlay_full")
        rendered = cat.render_for_prediction()
        self.assertIn("ENTHÄLT:", rendered)
        self.assertIn("NICHT:", rendered)

    def test_render_omits_examples_when_baseline(self):
        cat = _load("baseline")
        rendered = cat.render_for_prediction()
        self.assertNotIn("ENTHÄLT:", rendered)
        self.assertNotIn("NICHT:", rendered)

    def test_description_max_chars_truncates(self):
        cat = _load("overlay_full", description_max_chars=50)
        rendered = cat.render_for_prediction()
        # Spot check: pick the longest description and verify it gets capped
        # in the rendered output.
        for line in rendered.splitlines():
            # Description is between " — " and either " ENTHÄLT:" or end of line
            if " — " in line:
                desc_chunk = line.split(" — ", 1)[1].split(" ENTHÄLT:")[0]
                self.assertLessEqual(len(desc_chunk), 50)

    def test_merge_frame_has_required_columns(self):
        cat = _load("overlay_full")
        mf = cat.as_invoice_merge_frame()
        for col in (
            "Warengruppe",
            "wg_name",
            "wg_description",
            "wg_examples_enthalten",
            "wg_examples_nicht_enthalten",
            "wg_status_overlay",
            "wg_konfidenz_overlay",
        ):
            self.assertIn(col, mf.columns)
        self.assertEqual(len(mf), 192)

    def test_merge_frame_examples_format(self):
        cat = _load("overlay_full")
        mf = cat.as_invoice_merge_frame()
        sample = mf[mf["wg_examples_enthalten"] != ""].iloc[0]
        # Bullet-line format: "- a\n- b"
        for line in str(sample["wg_examples_enthalten"]).splitlines():
            self.assertTrue(line.startswith("- "))

    def test_has_any_examples_per_variant(self):
        # Drives the conditional system-prompt hint in both models.
        self.assertFalse(_load("baseline").has_any_examples)
        self.assertFalse(_load("overlay_desc").has_any_examples)
        self.assertTrue(_load("overlay_inclusive").has_any_examples)
        self.assertTrue(_load("overlay_full").has_any_examples)

    def test_example_breakdown_properties(self):
        inclusive = _load("overlay_inclusive")
        self.assertTrue(inclusive.has_examples_enthalten)
        self.assertFalse(inclusive.has_examples_nicht_enthalten)
        full = _load("overlay_full")
        self.assertTrue(full.has_examples_enthalten)
        self.assertTrue(full.has_examples_nicht_enthalten)


class TestNormalizeWgKey(unittest.TestCase):
    def test_inner_comma_is_ignored(self):
        # Live-Fall vom 21.07.2026: der Katalog schreibt "DL Wartung …" ohne
        # Komma, das LLM antwortet mit der im Katalog dominanten Schreibweise
        # "DL, …" — die Suggestion wurde deshalb komplett verworfen.
        self.assertEqual(
            normalize_wg_key(
                "DL, Wartung und Instandhaltung von Nutzerspezifische techn. Anlagen"
            ),
            normalize_wg_key(
                "DL Wartung und Instandhaltung von Nutzerspezifische techn. Anlagen"
            ),
        )

    def test_slash_spacing_is_ignored(self):
        self.assertEqual(
            normalize_wg_key("DL Instandhaltung Fahrzeuge PKW / LKW"),
            normalize_wg_key("DL Instandhaltung Fahrzeuge PKW/LKW"),
        )

    def test_keys_stay_collision_free_across_catalog(self):
        names = [e.name for e in _load("baseline").rows]
        keys = [normalize_wg_key(n) for n in names]
        self.assertEqual(len(names), len(set(keys)))

    def test_resolve_returns_canonical_name(self):
        cat = _load("baseline")
        target = next(n for n in (e.name for e in cat.rows) if "," in n)
        noisy = "17. " + target.replace(",", " ,").upper()
        self.assertEqual(cat.resolve(noisy), target)


if __name__ == "__main__":
    unittest.main()
