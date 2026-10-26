# models

LLM-based models for UC44.

| Model | Purpose |
|---|---|
| [plausibility_model/](plausibility_model/) | Given an invoice line and its current Warengruppe, decide whether the assignment is `plausibel` / `implausibel` / `unklar` |
| [prediction_model/](prediction_model/)     | Given an invoice line's pre-classification fields, predict the best-fitting Warengruppe |

## Shared setup

API keys and Python dependencies are kept at this level so both models use
the same environment:

- `.env` — API keys (gitignored). Read by each model's `run.py` via
  `env_path=MODELS_DIR / ".env"`.
- `requirements.txt` — common Python dependencies.
- `_shared/catalog.py` — common Warengruppen loader and `WarengruppenCatalog`
  class. Both models go through it, so the dim master + LLM-enriched
  overlay are read in exactly one place.

```bash
pip install -r requirements.txt
```

Each model owns its own `config.yml` (model choice, pricing, prompt,
column mapping) so they can be tuned independently.

## Catalog variants (A/B switch)

Both `config.yml` files share a `catalog:` block selecting one of four
variants:

| Variant | Description | Examples (Einschluss) | Examples (Ausschluss) |
|---|---|---|---|
| `baseline` | Master `Genauere Beschreibung` only | – | – |
| `overlay_desc` | LLM-enriched description (master fallback) | – | – |
| `overlay_inclusive` | LLM description + ENTHÄLT-Beispiele | yes | – |
| `overlay_full` (default) | LLM description + ENTHÄLT + NICHT | yes | yes |

CLI override: `--catalog-variant baseline` on either `run.py`.

The default output path encodes the variant and overlay hash so A/B runs
do not overwrite each other:

```
outputs/predictions__overlay_full__cb0fb65e.xlsx
outputs/plausibility__overlay_full__cb0fb65e.xlsx
```

## Running

```bash
cd plausibility_model && python run.py
cd prediction_model   && python run.py
```

Both write their output Excel into their own `outputs/` directory and
cache API responses under their own `.cache/`. The cache key includes the
catalog hash, so switching variants invalidates entries automatically.

## Cost orientation (gpt-4o-mini, 5000 rows)

| Variant | prediction_model | plausibility_model |
|---|---|---|
| `baseline` | ~$3 | ~$1 |
| `overlay_full` | ~$16-17 | ~$2 |

The default `pricing.budget_usd` in both configs is 25, which fits a full
`overlay_full` run with headroom. Lower it to 10 if you stay on baseline.

## Tooling

- `tests/test_catalog_loader.py` and `tests/test_plausibility_refusal.py`
  (repo root) — unit tests for the catalog loader and the plausibility
  refusal path, no API calls.
  ```bash
  .venv/bin/python -m unittest tests.test_catalog_loader tests.test_plausibility_refusal -v
  ```
- `scripts/compare_variants.py` — runs the prediction model under two
  variants on a stratified subsample and writes a diff Excel + cost
  report.
- `scripts/compare_plausibility_variants.py` — same idea for the
  plausibility model. Default 200 rows, `--max-rows 0` for the full
  dataset.
