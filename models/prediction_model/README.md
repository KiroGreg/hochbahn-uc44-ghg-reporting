# prediction_model

LLM-based Warengruppe classifier for invoice line items.

For each invoice line the model receives only the **pre-classification**
fields (free text, amount, date, unit) and the full catalog of available
Warengruppen, then picks exactly one.

No label-derived features are read: `Warengruppe`, `Kostenart`,
`WG_Bezeichnung`, `WG_Beschreibung`, `Kostenartenbezeichn.`, emission
factors and plausibility outputs are all intentionally excluded. That
mirrors the production scenario where the classifier runs on fresh
invoices before any assignment exists.

## Files

| File | Purpose |
|---|---|
| `config.yml` | LLM settings, pricing, budget, input columns, prompt template |
| `model.py`   | `PredictionModel` class |
| `run.py`     | CLI: load invoices, build catalog from dim table, predict, export |

Shared across models (one level up, in `../`):

| File | Purpose |
|---|---|
| `../.env`          | API keys |
| `../requirements.txt` | Python dependencies |

## Usage

```bash
pip install -r ../requirements.txt

# default run -- variant from config.yml, default overlay_full
# (~5000 rows, ~16-17 USD with gpt-4o-mini)
python run.py

# baseline run for A/B comparison
python run.py --catalog-variant baseline

# quick sample
python run.py --max-rows 50
```

The default output filename embeds variant and overlay hash, e.g.
`outputs/predictions__overlay_full__cb0fb65e.xlsx`. Pass `--out` to
override explicitly.

## Output

The original invoice columns plus prediction and audit columns:

| Column | Content |
|---|---|
| `predicted_warengruppe` | The chosen Warengruppe name (exact string from catalog) |
| `confidence` | `hoch` / `mittel` / `niedrig` |
| `reason` | Short German reasoning |
| `overlay_status_used` | `neu` / `verbessert` / `unverändert` / `ergänzung_beispiele` of the predicted Warengruppe (CSRD audit) |
| `overlay_konfidenz_used` | LLM self-confidence of the catalog entry, 0–100 |
| `overlay_variant` | Run-level: which catalog variant was used |
| `overlay_hash` | First 8 chars of the overlay content hash |
| `overlay_modell` | LLM that produced the overlay (e.g. `gpt-4o`) |
| `overlay_datum_generierung` | Overlay generation timestamp (ISO) |

The CLI also prints a quick agreement metric against the currently
assigned `Warengruppe` when present in the input. That is **not** a
validation metric -- the plausibility model suggests ~43 % of the
existing labels are themselves wrong -- but it is a useful sanity signal.

## Tuning

- `catalog.variant` in config.yml — see the top-level
  [models README](../README.md#catalog-variants-ab-switch).
- `catalog.description_max_chars` caps per-entry description length in the
  rendered prompt (default 220).
- `catalog.examples_max_inclusive` / `examples_max_exclusive` cap the
  number of bullet examples per entry (defaults 4 / 2).
- Swap `llm.model` to upgrade quality (e.g. `gpt-4.1-mini`, `gpt-4o`).
  Remember to update `pricing.input_per_1m_usd` / `output_per_1m_usd`.
