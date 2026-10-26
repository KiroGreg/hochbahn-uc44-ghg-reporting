"""Run the plausibility model under two catalog variants and write a diff Excel.

Calls the LLM -- requires `OPENAI_API_KEY` (or `LLM_API_KEY`) in
`Use Case/models/.env` and costs real money. A two-variant sweep over the
full 5000-row sample costs roughly $1-2 with gpt-4o-mini (small prompts:
one Warengruppe per call, no full catalog).

Usage:
    # quick check (default 200 rows)
    .venv/bin/python "Use Case/models/scripts/compare_plausibility_variants.py" --max-rows 200

    # full dataset
    .venv/bin/python "Use Case/models/scripts/compare_plausibility_variants.py" --max-rows 0

    # different variant pair
    .venv/bin/python "Use Case/models/scripts/compare_plausibility_variants.py" \\
        --variants baseline overlay_inclusive --max-rows 200
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
sys.path.insert(0, str(MODELS_DIR / "plausibility_model"))

from _shared.catalog import load_warengruppen  # noqa: E402
from plausibility_model.model import PlausibilityModel, load_config  # noqa: E402
from plausibility_model.run import load_invoices_with_catalog  # noqa: E402


VALID = ("baseline", "overlay_desc", "overlay_inclusive", "overlay_full")


def _run_variant(
    variant: str,
    invoices_path: Path,
    data_dir: Path,
    models_dir: Path,
    max_rows: int | None,
) -> tuple[pd.DataFrame, dict]:
    cfg = load_config(models_dir / "plausibility_model" / "config.yml")
    cfg["catalog"]["variant"] = variant
    catalog = load_warengruppen(data_dir, cfg["catalog"])
    df = load_invoices_with_catalog(invoices_path, catalog)

    if max_rows is not None:
        df = df.head(max_rows).copy()

    n_missing = int(df["wg_name"].isna().sum())
    if n_missing:
        print(
            f"  WARN: {n_missing}/{len(df)} rows have no Warengruppe -- "
            f"marked confidence=not_assessable, no API call."
        )

    model = PlausibilityModel(config=cfg, env_path=models_dir / ".env")
    model.prepare_catalog(catalog)
    out = model.predict(df, progress=False)

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
    parser.add_argument(
        "--max-rows",
        type=int,
        default=200,
        help="Limit to first N rows; pass 0 for full dataset (default 200).",
    )
    parser.add_argument(
        "--out",
        default=str(
            MODELS_DIR / "plausibility_model" / "outputs" / "variant_diff.xlsx"
        ),
    )
    args = parser.parse_args()

    max_rows = args.max_rows if args.max_rows and args.max_rows > 0 else None
    a, b = args.variants
    models_dir = MODELS_DIR
    invoices_path = Path(args.invoices)
    data_dir = Path(args.data_dir)

    print(f"Plausibility A/B compare: {a} vs {b}")
    print(f"Invoices: {invoices_path}")
    print(f"max-rows: {max_rows if max_rows is not None else 'all (full dataset)'}")

    print(f"\n=== {a} ===")
    out_a, sum_a = _run_variant(a, invoices_path, data_dir, models_dir, max_rows)
    print(
        f"calls={sum_a['calls']}  cache={sum_a['cache_hits']}  "
        f"tokens={sum_a['input_tokens']}/{sum_a['output_tokens']}  "
        f"cost=${sum_a['cost_usd']:.4f}"
    )

    print(f"\n=== {b} ===")
    out_b, sum_b = _run_variant(b, invoices_path, data_dir, models_dir, max_rows)
    print(
        f"calls={sum_b['calls']}  cache={sum_b['cache_hits']}  "
        f"tokens={sum_b['input_tokens']}/{sum_b['output_tokens']}  "
        f"cost=${sum_b['cost_usd']:.4f}"
    )

    # Build diff. Both runs see the same invoice rows in the same order
    # (load_invoices_with_catalog merges 1:1 on Warengruppe), so a positional
    # join is safe.
    n = min(len(out_a), len(out_b))
    base_cols = [
        c
        for c in (
            "Bestelltext",
            "Bezeichnung",
            "Objektbezeichnung",
            "Warengruppe",
            "wg_name",
            "Kostenartenbezeichn.",
        )
        if c in out_a.columns
    ]
    diff = out_a[base_cols].head(n).reset_index(drop=True)
    for col in ("plausible", "confidence", "reason"):
        diff[f"{col}_{a}"] = out_a[col].head(n).reset_index(drop=True)
        diff[f"{col}_{b}"] = out_b[col].head(n).reset_index(drop=True)
    diff["agreement"] = (
        diff[f"plausible_{a}"].astype("string")
        == diff[f"plausible_{b}"].astype("string")
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    diff.to_excel(out_path, index=False)

    n_total = len(diff)
    agree = int(diff["agreement"].sum())
    print("\n--- Summary ---")
    print(
        f"Rows: {n_total}  Agreement: {agree} ({agree / n_total * 100:.1f}%)  "
        f"Disagreement: {n_total - agree}"
    )
    for variant, frame in ((a, out_a), (b, out_b)):
        plaus = int((frame["plausible"] == True).sum())  # noqa: E712
        impl = int((frame["plausible"] == False).sum())  # noqa: E712
        notass = int((frame["confidence"] == "not_assessable").sum())
        err = int((frame["confidence"] == "error").sum())
        print(
            f"  {variant:20s}  plausible: {plaus}  implausible: {impl}  "
            f"not_assessable: {notass}  error: {err}"
        )
    print(f"\nWrote diff: {out_path}")
    print(f"Total cost: ${sum_a['cost_usd'] + sum_b['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
