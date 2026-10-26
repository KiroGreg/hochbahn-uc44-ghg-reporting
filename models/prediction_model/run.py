"""CLI: run the Warengruppe prediction model on an invoice Excel file.

Only pre-prediction columns are read from the invoice -- the current
Warengruppe / Kostenart and any label-derived fields are deliberately
excluded. The dimension catalog (master + optional LLM-enriched overlay)
is built via the shared loader.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from model import PredictionModel, load_config


HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE.parent          # "Use Case/models/"  (shared .env)
DATA_DIR = MODELS_DIR.parent      # "Use Case/"         (source Excel files)

sys.path.insert(0, str(MODELS_DIR))
from _shared.catalog import _clean_cols, load_warengruppen  # noqa: E402


def _default_out_path(catalog) -> Path:
    suffix_hash = catalog.overlay_hash[:8] if catalog.overlay_hash else "nooverlay"
    return HERE / "outputs" / f"predictions__{catalog.variant}__{suffix_hash}.xlsx"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--invoices",
        default=str(DATA_DIR / "HHA_Rechnungsdaten_reduced_hashed_5000.xlsx"),
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--config", default=str(HERE / "config.yml"))
    parser.add_argument(
        "--out",
        default=None,
        help="Output Excel path. Defaults to outputs/predictions__{variant}__{hash}.xlsx",
    )
    parser.add_argument(
        "--catalog-variant",
        default=None,
        choices=("baseline", "overlay_desc", "overlay_inclusive", "overlay_full"),
        help="Override catalog.variant from config.yml.",
    )
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Anzahl paralleler LLM-Worker. Default aus config.yml (concurrency.workers).",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if args.catalog_variant is not None:
        config.setdefault("catalog", {})["variant"] = args.catalog_variant

    workers = args.workers if args.workers is not None else int(
        config.get("concurrency", {}).get("workers", 1)
    )

    print(f"Model: {config['llm']['model']}")
    print(f"Budget: ${config['pricing']['budget_usd']}")
    print(f"Concurrency: {workers} workers")

    catalog = load_warengruppen(Path(args.data_dir), config["catalog"])
    print(
        f"Catalog: {len(catalog.rows)} Warengruppen "
        f"(variant={catalog.variant}, overlay_hash={catalog.overlay_hash or '-'})"
    )

    out_path = Path(args.out) if args.out else _default_out_path(catalog)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading invoices: {args.invoices}")
    df = _clean_cols(pd.read_excel(args.invoices))

    model = PredictionModel(config=config, env_path=MODELS_DIR / ".env")
    model.prepare_catalog(catalog)

    print(f"Predicting Warengruppe for {len(df)} rows ...")
    df = model.predict(df, max_rows=args.max_rows, workers=workers)

    u = model.usage
    predicted = df["predicted_warengruppe"].notna().sum()
    print(
        f"\nDone: {predicted}/{len(df)} rows predicted  "
        f"(errors: {(df['confidence'] == 'error').sum()})"
    )
    print(
        f"API calls: {u.calls}  cache hits: {u.cache_hits}  "
        f"tokens in/out: {u.input_tokens}/{u.output_tokens}  ~ ${u.cost_usd:.4f}"
    )

    # Quick agreement check against the currently assigned Warengruppe (if
    # the invoice contains it). This is NOT validation -- ~43% of the
    # existing labels are themselves implausible per the plausibility model
    # -- but it is a useful sanity signal.
    if "Warengruppe" in df.columns:
        dim = _clean_cols(pd.read_excel(Path(args.data_dir) / "dimWarengruppen_hashed.xlsx")).rename(
            columns={"WG Nr.": "Warengruppe", "Warengruppenbezeichnung": "current_wg_name"}
        )
        tmp = df.merge(dim[["Warengruppe", "current_wg_name"]], on="Warengruppe", how="left")
        both = tmp.dropna(subset=["predicted_warengruppe", "current_wg_name"])
        if len(both) > 0:
            match = (both["predicted_warengruppe"] == both["current_wg_name"]).sum()
            print(
                f"Agreement with existing Warengruppe: {match}/{len(both)} "
                f"({match/len(both)*100:.1f}%)"
            )

    # Audit metadata that is constant for the whole run.
    df["overlay_variant"] = catalog.variant
    df["overlay_hash"] = catalog.overlay_hash[:8] if catalog.overlay_hash else ""
    df["overlay_modell"] = catalog.overlay_modell or ""
    df["overlay_datum_generierung"] = catalog.overlay_datum_generierung or ""

    print(f"\nWriting: {out_path}")
    df.to_excel(out_path, index=False)
    print("Done.")


if __name__ == "__main__":
    main()
