"""Pydantic response/request schemas exposed via the OpenAPI spec.

Field names use English where possible; domain identifiers
(Warengruppe, Kostenart, ...) keep their German names because they
match the source Excel headers and the prompt logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


Confidence = Literal[
    "hoch", "mittel", "niedrig", "unknown", "error", "not_assessable"
]
Plausibilitaet = Literal["plausibel", "implausibel", "unklar"]
UserDecision = Literal["ok", "reject", "regroup", "new_wg"]


class CatalogEntry(BaseModel):
    name: str
    description: Optional[str] = None


# --- Warengruppen catalog CRUD ----------------------------------------------

class EmissionsfaktorRow(BaseModel):
    """One spend-based emission factor (kg CO2e / €) for a reporting year."""
    jahr: int
    wert: float


class WarengruppeRow(BaseModel):
    """A Warengruppe in the catalog, with its per-year emission factors."""
    id: str
    wg_id: str
    wg_name: str
    beschreibung: Optional[str] = None
    examples_enthalten: list[str] = Field(default_factory=list)
    examples_nicht_enthalten: list[str] = Field(default_factory=list)
    emissionsfaktoren: list[EmissionsfaktorRow] = Field(default_factory=list)
    aktiv: bool = Field(
        default=True,
        description=(
            "Whether the Warengruppe is active. Inactive ones are no longer "
            "offered to the LLM as a suggestion target, but stay available for "
            "historical emission calculation and the audit trail. Toggle via the "
            "activate/deactivate endpoints, not the upsert payload."
        ),
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WarengruppeUpsertRequest(BaseModel):
    """Create/update payload. `wg_id` is optional on create (generated)."""
    wg_id: Optional[str] = Field(
        default=None,
        description="Business key. Omit on create to generate one ('new-<uuid>').",
    )
    wg_name: str
    beschreibung: Optional[str] = None
    examples_enthalten: list[str] = Field(default_factory=list)
    examples_nicht_enthalten: list[str] = Field(default_factory=list)
    emissionsfaktoren: list[EmissionsfaktorRow] = Field(default_factory=list)


class BulkDeleteRequest(BaseModel):
    """Delete several Warengruppen at once by their business keys."""
    wg_ids: list[str] = Field(default_factory=list)


class BulkDeleteResult(BaseModel):
    """Outcome of a bulk delete: how many were removed, which were unknown.

    `blocked` lists ids that were kept because they are still referenced by
    historical data (see the delete protection in `services/warengruppen.py`);
    those should be deactivated instead of deleted.
    """
    deleted: int = 0
    not_found: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class BulkActiveResult(BaseModel):
    """Outcome of a bulk activate/deactivate: how many changed, which were unknown."""
    updated: int = 0
    not_found: list[str] = Field(default_factory=list)


class BulkActiveRequest(BaseModel):
    """Activate (`aktiv=True`) or deactivate (`aktiv=False`) several Warengruppen."""
    wg_ids: list[str] = Field(default_factory=list)
    aktiv: bool


class ImportResult(BaseModel):
    """Outcome of a catalog import (upsert by wg_id)."""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


# --- Warengruppen enrichment (LLM) ------------------------------------------
#
# Generates/improves a Warengruppe's description + example lists via the LLM.
# The three notebook modes (neu / ergänzung_beispiele / verbessern) are
# generalised into a *per-field* action so the reviewer can target exactly one
# feature. `lassen` keeps the current value untouched; `ergänzen` respects the
# existing text (gentle improve / add missing); `neu` regenerates from scratch.

FieldAction = Literal["lassen", "ergänzen", "neu"]


class EnrichPlan(BaseModel):
    """Per-field action for one enrichment call. Defaults to full generation."""
    beschreibung: FieldAction = "neu"
    examples_enthalten: FieldAction = "neu"
    examples_nicht_enthalten: FieldAction = "neu"


class EnrichContent(BaseModel):
    """The current field values a suggestion is based on (may hold unsaved edits)."""
    beschreibung: Optional[str] = None
    examples_enthalten: list[str] = Field(default_factory=list)
    examples_nicht_enthalten: list[str] = Field(default_factory=list)


class FieldAnnotations(BaseModel):
    """Free-text 'Anmerkung für KI' per field, fed back into the refine call."""
    beschreibung: Optional[str] = None
    examples_enthalten: Optional[str] = None
    examples_nicht_enthalten: Optional[str] = None


class HistoryItem(BaseModel):
    """One aggregated manual-correction pattern (a Bestelltext), for the signal."""
    text: str
    count: int = 1
    betrag_eur: float = 0.0


class HistorySignal(BaseModel):
    """Manual in-/out-flux for a Warengruppe — the enrichment history signal.

    influx  = rows a human manually moved INTO this WG (decision_event.new_value)
              → its description/examples_enthalten likely miss these cases.
    outflux = rows a human manually moved OUT of this WG (old_value)
              → its examples_nicht_enthalten / scope boundary should be sharpened.
    """
    wg_id: str
    influx_count: int = 0
    outflux_count: int = 0
    top_influx: list[HistoryItem] = Field(default_factory=list)
    top_outflux: list[HistoryItem] = Field(default_factory=list)


class EnrichSuggestion(BaseModel):
    """An LLM enrichment proposal (not yet saved). Mirrors the notebook JSON."""
    beschreibung: Optional[str] = None
    examples_enthalten: list[str] = Field(default_factory=list)
    examples_nicht_enthalten: list[str] = Field(default_factory=list)
    konfidenz: Optional[int] = None
    anmerkung: Optional[str] = None
    status: Optional[str] = None
    diff_kurz: Optional[str] = None
    plan: EnrichPlan
    history_used: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Optional[float] = None


class EnrichRequest(BaseModel):
    """Atomic generate: work on the given content (plan=None → auto-derive)."""
    wg_name: str
    content: EnrichContent = Field(default_factory=EnrichContent)
    plan: Optional[EnrichPlan] = None
    use_history: bool = False
    wg_id: Optional[str] = Field(
        default=None,
        description="For the history signal; may be omitted for unsaved/new WGs.",
    )


class EnrichRefineRequest(BaseModel):
    """Atomic refine: incorporate per-field annotations into the current draft."""
    wg_name: str
    current: EnrichContent
    annotations: FieldAnnotations
    plan: Optional[EnrichPlan] = None
    use_history: bool = False
    wg_id: Optional[str] = None


class BulkEnrichRequest(BaseModel):
    """Start a background enrichment batch over the selected Warengruppen."""
    wg_ids: list[str] = Field(default_factory=list)
    plan: Optional[EnrichPlan] = Field(
        default=None,
        description="Default per-field plan; None → derive per WG from its state.",
    )
    use_history: bool = False


class EnrichBatchStatus(BaseModel):
    """Pollable progress of an enrichment batch — derived from the DB."""
    id: str
    status: str  # 'running' | 'done' | 'failed'
    total: int = 0
    done: int = 0
    error: Optional[str] = None
    use_history: bool = False
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    cost_usd: Optional[float] = None
    created_at: Optional[datetime] = None


class EnrichProposal(BaseModel):
    """One persisted proposal in a batch's review queue."""
    id: str
    batch_id: str
    wg_id: str
    wg_name: str
    plan: EnrichPlan
    current: EnrichContent
    suggestion: EnrichSuggestion
    state: str = "pending"  # 'pending' | 'accepted' | 'rejected' | 'superseded'
    applied: bool = False
    history_used: bool = False


class EnrichBatchDetail(BaseModel):
    """A batch's status plus its proposals — the review queue payload."""
    status: EnrichBatchStatus
    proposals: list[EnrichProposal] = Field(default_factory=list)


class EnrichApplyRequest(BaseModel):
    """Apply a proposal to its Warengruppe; `content` overrides with edited values."""
    content: Optional[EnrichContent] = None


class ProposalRefineRequest(BaseModel):
    """Refine a persisted proposal with per-field annotations (bulk review loop)."""
    annotations: FieldAnnotations
    content: Optional[EnrichContent] = None


class UploadSummary(BaseModel):
    filename: str
    row_count: int
    column_count: int
    detected_columns: list[str]
    warengruppe_count: int = Field(
        ...,
        description="Distinct Warengruppe IDs present in the uploaded invoices.",
    )


class PlausibilityRow(BaseModel):
    row_index: int
    bestelltext: str
    objektbezeichnung: str
    wg_id: Optional[str] = None
    wg_name: Optional[str] = None
    kostenart: Optional[str] = None
    betrag_eur: Optional[float] = Field(
        default=None,
        description="Invoice amount in EUR from the uploaded file, if an amount column was present.",
    )
    plausibilitaet: Optional[Plausibilitaet] = None
    confidence: Confidence
    unterstuetzende_signale: list[str] = Field(default_factory=list)
    widersprechende_signale: list[str] = Field(default_factory=list)
    reason: str
    decision: Optional[UserDecision] = None


class PlausibilityStats(BaseModel):
    total: int
    plausible: int
    implausible: int
    unklar: int = 0
    not_assessable: int = 0
    low_confidence: int
    objektbez_fallback: int


class PlausibilityRunResponse(BaseModel):
    stats: PlausibilityStats
    rows: list[PlausibilityRow]
    cost_usd: float
    api_calls: int
    cache_hits: int


class PredictionRow(BaseModel):
    row_index: int
    bestelltext: str
    current_wg_name: Optional[str] = None
    suggested_wg_name: Optional[str] = None
    betrag_eur: Optional[float] = Field(
        default=None,
        description="Invoice amount in EUR from the uploaded file, if an amount column was present.",
    )
    confidence: Confidence
    reason: str
    objektbez_signal: bool = False
    ef_missing: bool = False
    decision: Optional[UserDecision] = None
    source: Optional[str] = Field(
        default=None,
        description="How produced: 'baseline' | 'memory' | 'memoized'.",
    )


class PredictionStats(BaseModel):
    total: int
    regrouped_high_med: int
    low_confidence: int
    no_ef: int
    confirmed: int


class PredictionRunResponse(BaseModel):
    stats: PredictionStats
    rows: list[PredictionRow]
    cost_usd: float
    api_calls: int
    cache_hits: int


class DecisionRequest(BaseModel):
    row_index: int
    decision: UserDecision
    new_wg_name: Optional[str] = Field(
        default=None,
        description=(
            "Target Warengruppe when the user remaps a row (decision "
            "'regroup'/'new_wg'). Persisted as the new_value of the "
            "historised decision event."
        ),
    )
    old_value: Optional[str] = Field(
        default=None,
        description="Previous Warengruppe/decision value, for the audit trail.",
    )


class FunnelStats(BaseModel):
    total: int
    not_plausible: int
    regrouped: int
    low_open: int


class BudgetStats(BaseModel):
    spent_usd: float
    budget_usd: float
    api_calls: int
    cache_hits: int
    model: str


class TopWGEntry(BaseModel):
    wg_name: str
    co2_before_t: float
    co2_after_t: float
    delta_pct: float
    eur_before: float
    eur_after: float
    regrouped_count: int
    avg_confidence: Confidence
    ef_ok: bool


class DashboardKPIs(BaseModel):
    co2_before_t: float
    co2_after_t: float
    co2_delta_pct: float
    not_calculable: int
    regroup_rate_pct: float
    eur_total: float
    top_wg_share_pct: float
    eur_regrouped: float
    eur_avg_per_entry: float


class DashboardResponse(BaseModel):
    kpis: DashboardKPIs
    funnel: FunnelStats
    top_wg: list[TopWGEntry]
    ranking: list[TopWGEntry]
    available_years: list[int] = Field(default_factory=list)
    selected_year: Optional[int] = None


class RunOptions(BaseModel):
    max_rows: Optional[int] = Field(
        default=200,
        description="Cap rows for demo speed. Null = run on the full file.",
    )
    # Correction-memory augmentation (Step C). Off by default.
    enable_hints: bool = Field(
        default=False,
        description="Inject retrieved similar confirmed cases into the prediction prompt.",
    )
    hint_top_n: int = Field(default=6, description="Max retrieved cases per row.")
    hint_threshold: float = Field(
        default=0.82, description="Min cosine similarity for a case to be used as a hint."
    )
    memo_threshold: float = Field(
        default=0.99,
        description=(
            "Cosine memoization threshold (secondary). Primary memoization is an "
            "exact feature_key match; templated texts cluster high, so keep this near 1.0."
        ),
    )


# --- Run history & resume ----------------------------------------------------

class RunSummary(BaseModel):
    """One persisted Lauf, for the history picker."""
    id: str
    created_at: datetime
    filename: Optional[str] = None
    source: Optional[str] = None
    status: str
    row_count: Optional[int] = None
    sample_count: int = 0
    decision_count: int = 0
    has_plausibility: bool = False
    has_prediction: bool = False


class RunStatus(BaseModel):
    """Lightweight, pollable run progress — all derived from the DB."""
    id: str
    status: str  # 'uploaded' | 'running' | 'done' | 'failed'
    stage: Optional[str] = None  # 'plausibility' | 'prediction' | None
    error: Optional[str] = None
    sample_count: int = 0
    plaus_total: int = 0
    plaus_done: int = 0
    pred_total: int = 0
    pred_done: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ComparisonItem(BaseModel):
    """One sample where the memory-assisted run disagreed with the baseline."""
    row_index: int
    bestelltext: str
    baseline_wg: Optional[str] = None
    baseline_confidence: Optional[str] = None
    memory_wg: Optional[str] = None
    memory_confidence: Optional[str] = None
    memory_source: Optional[str] = None  # 'memory' | 'memoized'


class ComparisonResult(BaseModel):
    """Baseline vs. memory predictions for a run, for human spot-checking."""
    compared: int = 0          # samples that have both a baseline and a memory prediction
    changed: int = 0           # of those, how many the memory changed
    memoized: int = 0          # of the changes, how many were exact-match memoized
    has_baseline: bool = False
    has_memory: bool = False
    items: list["ComparisonItem"] = Field(default_factory=list)


class DecisionState(BaseModel):
    """The current (newest) decision for a sample, to restore the review table."""
    row_index: int
    decision: UserDecision
    selected_wg: Optional[str] = None
    stage: Optional[str] = None


class ChangeLogRecord(BaseModel):
    """A historised decision event, shaped for the frontend audit log."""
    timestamp: str
    stage: str
    row_index: int
    field_changed: str
    old_value: str
    new_value: str
    user_action: str


class RunDetail(BaseModel):
    """Everything needed to resume a run: rebuilt from the DB (no LLM re-run)."""
    run: RunSummary
    upload: UploadSummary
    plausibility: Optional[PlausibilityRunResponse] = None
    prediction: Optional[PredictionRunResponse] = None
    decisions: list[DecisionState] = Field(default_factory=list)
    change_log: list[ChangeLogRecord] = Field(default_factory=list)
