"""Aggregate stats for the dashboard view.

The KPIs combine the plausibility-run output, the regrouping output
and the user's accept/reject decisions to estimate the corrected
CO2e and EUR figures per Warengruppe. Emission factors come from the
Warengruppen catalog in the DB (via `services.warengruppen.ef_lookup`,
most recent year); rows whose Warengruppe has no EF count toward
"not_calculable".
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import pandas as pd

from ..core.data import amount_column, clean_cols
from ..core.paths import DATA_DIR
from ..core.state import SessionState
from ..services import prediction as prediction_svc
from ..services import warengruppen as warengruppen_svc
from ..schemas.models import (
    BudgetStats,
    DashboardKPIs,
    DashboardResponse,
    FunnelStats,
    TopWGEntry,
)


def _ef_lookup(jahr: Optional[int] = None) -> dict:
    """{Warengruppe-id -> emission factor} for the chosen year, else the latest.

    Read fresh on every dashboard request, so catalog/EF edits made via the
    CRUD interface are reflected immediately. Falls back to the EF Excel while
    the catalog table is unseeded (handled inside the service).
    """
    return warengruppen_svc.ef_lookup(jahr)


@lru_cache(maxsize=8)
def _load_ka_ef_table(jahr: Optional[int] = None) -> pd.DataFrame:
    path = DATA_DIR / "fak_Emissionsfaktoren_Kostenart_spend-based_hashed.xlsx"
    df = clean_cols(pd.read_excel(path))
    if "Kostenart" not in df.columns:
        return pd.DataFrame(columns=["Kostenart", "EF"])

    year_cols = [c for c in df.columns if str(c).isdigit()]
    if year_cols:
        chosen = str(jahr) if jahr is not None and str(jahr) in year_cols else None
        latest = max(year_cols, key=int)
        source_col = chosen or latest
        df = df.rename(columns={source_col: "EF"})
    return df[["Kostenart", "EF"]].dropna()


def _ka_ef_lookup(jahr: Optional[int] = None) -> dict:
    df = _load_ka_ef_table(jahr)
    return {str(k): float(v) for k, v in zip(df["Kostenart"], df["EF"])}


def _wg_id_to_name() -> dict:
    """Take the WG-id → name mapping from the shared catalog (master + overlay)."""
    catalog = prediction_svc.get_catalog()
    return {e.wg_id: e.name for e in catalog.rows if e.wg_id and e.name}


def _wg_name_to_id() -> dict:
    return {v: k for k, v in _wg_id_to_name().items()}


def build(state: SessionState, jahr: Optional[int] = None) -> DashboardResponse:
    invoices = state.invoices
    plaus = state.plausibility_df
    pred = state.prediction_df

    if invoices is None:
        empty = DashboardKPIs(
            co2_before_t=0, co2_after_t=0, co2_delta_pct=0,
            not_calculable=0, regroup_rate_pct=0,
            eur_total=0, top_wg_share_pct=0, eur_regrouped=0, eur_avg_per_entry=0,
        )
        return DashboardResponse(
            kpis=empty,
            funnel=FunnelStats(total=0, not_plausible=0, regrouped=0, low_open=0),
            top_wg=[],
            ranking=[],
            available_years=warengruppen_svc.available_years(),
            selected_year=jahr,
        )

    ka_ef = _ka_ef_lookup(jahr)
    ef = _ef_lookup(jahr)
    id_to_name = _wg_id_to_name()
    name_to_id = _wg_name_to_id()
    amount_col = amount_column(invoices)

    df = invoices.copy()
    df["__amount"] = pd.to_numeric(df.get(amount_col), errors="coerce").fillna(0.0) if amount_col else 0.0
    df["__wg_before"] = df.get("Warengruppe").astype(str)
    df["__kostenart"] = df.get("Kostenart").astype(str)
    df["__ka_ef"] = df["__kostenart"].map(lambda k: ka_ef.get(str(k), 0.0))

    # Apply regrouping suggestions where the user accepted them (or, in
    # the absence of decisions, where confidence is high).
    df["__wg_after"] = df["__wg_before"]
    pred_conf = pd.Series({int(idx): str(row.get("confidence") or "") for idx, row in pred.iterrows()}) if pred is not None else pd.Series(dtype="string")
    if pred is not None and "predicted_warengruppe" in pred.columns:
        for idx, row in pred.iterrows():
            if idx not in df.index:
                continue
            decision = state.user_decisions.get(int(idx), {}).get("decision")
            suggested = row.get("predicted_warengruppe")
            confidence = str(row.get("confidence") or "")
            if decision == "ok" or (decision is None and suggested and confidence == "hoch"):
                if pd.notna(suggested):
                    new_id = name_to_id.get(str(suggested))
                    if new_id is not None:
                        df.at[idx, "__wg_after"] = new_id

    df["__co2_before"] = df["__wg_before"].map(lambda w: ef.get(str(w), 0.0)) * df["__amount"]


    df["__co2_after"] = df["__wg_after"].map(lambda w: ef.get(str(w), 0.0)) * df["__amount"]
    no_wg_mask = df["Warengruppe"].isna() | df["Warengruppe"].astype(str).str.strip().eq("")
    low_conf_mask = ~df.index.to_series().map(pred_conf).fillna("hoch").astype(str).str.lower().eq("hoch")
    df.loc[no_wg_mask & low_conf_mask, "__co2_after"] = df.loc[no_wg_mask & low_conf_mask, "__ka_ef"] * df.loc[no_wg_mask & low_conf_mask, "__amount"]

    co2_before_t = float(df["__co2_before"].sum()) / 1000.0
    co2_after_t = float(df["__co2_after"].sum()) / 1000.0
    delta_pct = ((co2_after_t - co2_before_t) / co2_before_t * 100.0) if co2_before_t else 0.0

    not_calculable = int((~df["__wg_after"].isin(ef.keys())).sum())
    regrouped_count = int((df["__wg_before"] != df["__wg_after"]).sum())
    regroup_rate_pct = (regrouped_count / len(df) * 100.0) if len(df) else 0.0

    eur_total = float(df["__amount"].sum())
    eur_avg = eur_total / len(df) if len(df) else 0.0
    eur_regrouped = float(df.loc[df["__wg_before"] != df["__wg_after"], "__amount"].sum())

    grouped = (
        df.groupby("__wg_after", dropna=False)
        .agg(
            co2_after=("__co2_after", "sum"),
            co2_before=("__co2_before", "sum"),
            eur=("__amount", "sum"),
            n=("__amount", "size"),
        )
        .sort_values("co2_after", ascending=False)
    )

    top_wg: list[TopWGEntry] = []
    for wg_id, row in grouped.head(5).iterrows():
        name = id_to_name.get(str(wg_id), str(wg_id))
        before = float(row["co2_before"]) / 1000.0
        after = float(row["co2_after"]) / 1000.0
        d = ((after - before) / before * 100.0) if before else 0.0
        top_wg.append(
            TopWGEntry(
                wg_name=name,
                co2_before_t=round(before, 1),
                co2_after_t=round(after, 1),
                delta_pct=round(d, 1),
                eur_before=round(float(row["eur"]), 2),
                eur_after=round(float(row["eur"]), 2),
                regrouped_count=int(row["n"]),
                avg_confidence="hoch",
                ef_ok=str(wg_id) in ef,
            )
        )

    top_share = float(grouped["eur"].head(1).sum() / eur_total * 100.0) if eur_total else 0.0

    kpis = DashboardKPIs(
        co2_before_t=round(co2_before_t, 1),
        co2_after_t=round(co2_after_t, 1),
        co2_delta_pct=round(delta_pct, 1),
        not_calculable=not_calculable,
        regroup_rate_pct=round(regroup_rate_pct, 1),
        eur_total=round(eur_total, 2),
        top_wg_share_pct=round(top_share, 1),
        eur_regrouped=round(eur_regrouped, 2),
        eur_avg_per_entry=round(eur_avg, 2),
    )

    plaus_total = int(len(plaus)) if plaus is not None else 0
    not_plausible = (
        int((plaus["plausibilitaet"] == "implausibel").sum())
        if plaus is not None and "plausibilitaet" in plaus.columns
        else 0
    )
    pred_total = int(len(pred)) if pred is not None else 0
    low_open = int((pred["confidence"] == "niedrig").sum()) if pred is not None else 0

    funnel = FunnelStats(
        total=int(len(invoices)),
        not_plausible=not_plausible if plaus_total else 0,
        regrouped=pred_total - low_open if pred_total else 0,
        low_open=low_open,
    )

    return DashboardResponse(
        kpis=kpis,
        funnel=funnel,
        top_wg=top_wg,
        ranking=top_wg,
        available_years=warengruppen_svc.available_years(),
        selected_year=jahr,
    )


def budget(plaus_cfg: dict, plaus_usage_cost: float, pred_usage_cost: float,
           plaus_calls: int, pred_calls: int, plaus_cache: int, pred_cache: int) -> BudgetStats:
    return BudgetStats(
        spent_usd=round(plaus_usage_cost + pred_usage_cost, 4),
        budget_usd=float(plaus_cfg["pricing"]["budget_usd"]),
        api_calls=plaus_calls + pred_calls,
        cache_hits=plaus_cache + pred_cache,
        model=str(plaus_cfg["llm"]["model"]),
    )
