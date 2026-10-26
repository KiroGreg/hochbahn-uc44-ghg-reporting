# plausibility_model

LLM-based plausibility classifier for invoice line items.

For every row it asks: is the current `Warengruppe` assignment consistent
with the free-text fields (`Bestelltext`, `Bezeichnung`, `Objektbezeichnung`,
...)? Kostenart is intentionally not part of the prompt — it is only an
emission-factor fallback and would bias the judgment.

Output per row: `plausibilitaet` (`plausibel` / `implausibel` / `unklar`),
`confidence`, two signal lists (`unterstuetzende_signale`,
`widersprechende_signale`) with literal quotes from the invoice text, and a
short `reason`.

## Files

| File | Purpose |
|---|---|
| `config.yml` | LLM settings, pricing, budget, input column mapping, prompt template |
| `model.py`   | `PlausibilityModel` class + data structures |
| `run.py`     | CLI: load invoices, enrich with Warengruppe info, run model, write Excel |
| `.env`       | API key (gitignored) |

## Configuration

All tuning happens in [config.yml](config.yml):

- **LLM**: `base_url`, `model`, `temperature`, `api_key_env`
- **Pricing / budget**: `input_per_1m_usd`, `output_per_1m_usd`, `budget_usd`
- **Input columns**: mapping from logical placeholders to source column names
- **Prompt**: `system` and `user_template` (multi-line YAML strings)

Editing the prompt automatically invalidates the cache entries for the
changed rows (the cache key includes the system prompt).

## API key

The file `.env` holds secrets. `config.yml` names the env var to use
(`api_key_env`). Resolution order: `LLM_API_KEY` > `<configured>` > `OPENAI_API_KEY`.

## Usage

```bash
pip install -r ../requirements.txt

# default run -- variant from config.yml, default overlay_full
python run.py

# baseline run for A/B comparison
python run.py --catalog-variant baseline

# quick check on a small sample
python run.py --max-rows 50
```

The default output filename embeds variant and overlay hash, e.g.
`outputs/plausibility__overlay_full__cb0fb65e.xlsx`. Pass `--out` to
override explicitly.

## Output

The output Excel has one sheet with all input columns plus prediction and
audit columns:

| Column | Content |
|---|---|
| `plausibilitaet` | `plausibel` / `implausibel` / `unklar` / blank (skipped or not yet checked) |
| `confidence` | `hoch` / `mittel` / `niedrig` / `error` / `not_assessable` |
| `unterstuetzende_signale` | Literal quotes from the invoice text that support the assignment, joined with ` \| ` |
| `widersprechende_signale` | Literal quotes from the invoice text that contradict the assignment, joined with ` \| ` |
| `reason` | Short German reasoning, or `warengruppe_missing_or_unknown` for refused rows |
| `overlay_status_used` | Catalog status of the assigned Warengruppe, or sentinel `warengruppe_missing` |
| `overlay_konfidenz_used` | LLM self-confidence of the catalog entry, 0–100 |
| `overlay_variant`, `overlay_hash`, `overlay_modell`, `overlay_datum_generierung` | Run-level audit metadata |

### Refusal path

If an invoice row has no Warengruppe in the catalog (`Warengruppe` empty
or pointing at an unknown wg_id), the run **skips the LLM call** for that
row and writes `confidence=not_assessable` plus
`overlay_status_used=warengruppe_missing`. This keeps the audit trail
honest -- absent input is not silently graded as "plausible" -- and saves
the API cost. The CLI prints a `WARN` line at start-up with the count.

## Catalog variants

Same A/B switch as the prediction model -- see
[`../README.md`](../README.md#catalog-variants-ab-switch). Token budget is
not a concern here because each call sends only one Warengruppe in the
prompt (no full catalog).

## Budget stop

If the projected cost (observed tokens × configured $/1M) reaches
`pricing.budget_usd` the run stops gracefully and the processed rows stay
in the output file.
