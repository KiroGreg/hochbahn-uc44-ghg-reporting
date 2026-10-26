"""Run the prediction model under two catalog variants and write a diff Excel.

Calls the LLM -- requires `OPENAI_API_KEY` (or `LLM_API_KEY`) in
`Use Case/models/.env` and costs real money. Default subsample is 200 rows;
a baseline + overlay_full sweep over 200 rows costs roughly $0.60-$1.00
with gpt-4o-mini.

Usage:
    .venv/bin/python "Use Case/models/scripts/compare_variants.py"
    .venv/bin/python "Use Case/models/scripts/compare_variants.py" \\
        --variants baseline overlay_full --max-rows 100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent      # Use Case/models/scripts/
MODELS_DIR = HERE.parent                    # Use Case/models/
DATA_DIR = MODELS_DIR.parent                # Use Case/

sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(MODELS_DIR / "prediction_model"))

from _shared.catalog import _clean_cols, load_warengruppen  # noqa: E402
from prediction_model.model import PredictionModel, load_config  # noqa: E402


VALID = ("baseline", "overlay_desc", "overlay_inclusive", "overlay_full")


def _stratified_sample(df: pd.DataFrame, n: int, key: str = "Kostenartenbezeichn.") -> pd.DataFrame:
    """Stratified subsample by Kostenart. Falls back to head() if key missing."""
    if key not in df.columns:
        return df.head(n).copy()
    groups = df.groupby(key, sort=False, observed=True)
    per = max(1, n // max(1, groups.ngroups))
    sample = groups.head(per)
    if len(sample) < n:
        extra = df.drop(sample.index).head(n - len(sample))
        sample = pd.concat([sample, extra])
    return sample.head(n).reset_index(drop=True)


def _run_variant(
    variant: str,
    df: pd.DataFrame,
    data_dir: Path,
    models_dir: Path,
) -> tuple[pd.DataFrame, dict]:
    cfg = load_config(models_dir / "prediction_model" / "config.yml")
    cfg["catalog"]["variant"] = variant
    catalog = load_warengruppen(data_dir, cfg["catalog"])
    model = PredictionModel(config=cfg, env_path=models_dir / ".env")
    model.prepare_catalog(catalog)
    out = model.predict(df.copy(), progress=False)
    u = model.usage
    summary = {
        "variant": variant,
        "overlay_hash": catalog.overlay_hash,
        "calls": u.calls,
        "cache_hits": u.cache_hits,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cost_usd": u.cost_usd,
    }
    return out, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--invoices",
        default=str(DATA_DIR / "HHA_Rechnungsdaten_reduced_hashed_5000.xlsx"),
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument(
        "--variants", nargs=2, default=["baseline", "overlay_full"], choices=VALID,
    )
    parser.add_argument("--max-rows", type=int, default=200)
    parser.add_argument(
        "--out",
        default=str(
            MODELS_DIR / "prediction_model" / "outputs" / "variant_diff.xlsx"
        ),
    )
    args = parser.parse_args()

    a, b = args.variants
    print(f"Loading invoices: {args.invoices}")
    df_full = _clean_cols(pd.read_excel(args.invoices))
    df = _stratified_sample(df_full, args.max_rows)
    print(f"Sample: {len(df)} rows (stratified by Kostenart where available)")

    models_dir = MODELS_DIR

    print(f"\n=== {a} ===")
    out_a, sum_a = _run_variant(a, df, Path(args.data_dir), models_dir)
    print(
        f"calls={sum_a['calls']}  cache={sum_a['cache_hits']}  "
        f"tokens={sum_a['input_tokens']}/{sum_a['output_tokens']}  "
        f"cost=${sum_a['cost_usd']:.4f}"
    )

    print(f"\n=== {b} ===")
    out_b, sum_b = _run_variant(b, df, Path(args.data_dir), models_dir)
    print(
        f"calls={sum_b['calls']}  cache={sum_b['cache_hits']}  "
        f"tokens={sum_b['input_tokens']}/{sum_b['output_tokens']}  "
        f"cost=${sum_b['cost_usd']:.4f}"
    )

    # Build diff
    base_cols = [
        c
        for c in (
            "Bestelltext",
            "Bezeichnung",
            "Objektbezeichnung",
            "Warengruppe",
            "Kostenartenbezeichn.",
        )
        if c in df.columns
    ]
    diff = df[base_cols].copy().reset_index(drop=True)
    diff[f"predicted_{a}"] = out_a["predicted_warengruppe"].values
    diff[f"predicted_{b}"] = out_b["predicted_warengruppe"].values
    diff[f"confidence_{a}"] = out_a["confidence"].values
    diff[f"confidence_{b}"] = out_b["confidence"].values
    diff[f"reason_{a}"] = out_a["reason"].values
    diff[f"reason_{b}"] = out_b["reason"].values
    diff["agreement"] = diff[f"predicted_{a}"] == diff[f"predicted_{b}"]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    diff.to_excel(out_path, index=False)

    n = len(diff)
    agree = int(diff["agreement"].sum())
    print(f"\n--- Summary ---")
    print(f"Rows: {n}  Agreement: {agree} ({agree / n * 100:.1f}%)  Disagreement: {n - agree}")
    for variant, frame in ((a, out_a), (b, out_b)):
        hist = frame["confidence"].value_counts(dropna=False).to_dict()
        print(f"  {variant:20s} confidence: {hist}")
    print(f"\nWrote diff: {out_path}")


if __name__ == "__main__":
    main()
