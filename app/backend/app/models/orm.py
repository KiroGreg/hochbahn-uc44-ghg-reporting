"""SQLAlchemy ORM schema — the persisted system of record.

Mirrors the in-memory flow (upload → plausibility → prediction → decisions)
but as durable, history-preserving tables. Design notes:

* `run` is the *Lauf* — one coherent uploaded CSV/Excel batch.
* `sample` is one invoice row, keyed within its run by `row_index` — the same
  positional Pandas index every backend stage aligns on.
* `plausibility_result` / `prediction_result` are append-only per sample: a
  re-run inserts a new row, the newest (`created_at`) is the current one.
* `decision_event` is the historised manual-change log (append-only). The
  "current" mapping for a sample is its newest event; older remappings stay
  for the audit trail.

Column types are portable across Postgres (compose) and the SQLite local
fallback: `Uuid` → native uuid / CHAR(32); `JSON` → JSONB on Postgres.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from ..core.db import Base

# text-embedding-3-small dimensionality.
EMBED_DIM = 1536
# pgvector on Postgres; JSON on the SQLite dev fallback (no vector search there).
EmbeddingType = Vector(EMBED_DIM).with_variant(JSON, "sqlite")

# JSONB on Postgres, plain JSON (TEXT-backed) elsewhere.
JSONVariant = JSON().with_variant(JSONB, "postgresql")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Run(Base):
    """A *Lauf*: one coherent uploaded invoice batch."""

    __tablename__ = "run"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    filename: Mapped[Optional[str]] = mapped_column(String(512))
    source: Mapped[Optional[str]] = mapped_column(String(32))  # 'upload' | 'sample'
    row_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_count: Mapped[Optional[int]] = mapped_column(Integer)
    # Lifecycle: 'uploaded' → 'running' → 'done' | 'failed'.
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    # Current stage while running: 'plausibility' | 'prediction' | None.
    stage: Mapped[Optional[str]] = mapped_column(String(32))
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Progress denominators (numerators are derived live via COUNT on the
    # result tables, so progress = done/total is read straight from the DB).
    plaus_total: Mapped[Optional[int]] = mapped_column(Integer)
    pred_total: Mapped[Optional[int]] = mapped_column(Integer)
    # LLM/budget snapshot for the run (filled as stages complete).
    model_name: Mapped[Optional[str]] = mapped_column(String(128))
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    api_calls: Mapped[Optional[int]] = mapped_column(Integer)

    samples: Mapped[list["Sample"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Sample(Base):
    """One invoice row within a run, keyed by its positional `row_index`."""

    __tablename__ = "sample"
    __table_args__ = (
        UniqueConstraint("run_id", "row_index", name="uq_sample_run_rowindex"),
        Index("ix_sample_run", "run_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"))
    row_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Inputs from the uploaded file.
    bestelltext: Mapped[Optional[str]] = mapped_column(Text)
    objektbezeichnung: Mapped[Optional[str]] = mapped_column(Text)
    kostenart: Mapped[Optional[str]] = mapped_column(Text)
    wg_id_original: Mapped[Optional[str]] = mapped_column(String(64))
    wg_name_original: Mapped[Optional[str]] = mapped_column(Text)
    betrag_eur: Mapped[Optional[float]] = mapped_column(Numeric(16, 2))
    # Loss-less copy of the original row for anything not modelled explicitly.
    raw: Mapped[Optional[dict]] = mapped_column(JSONVariant)

    run: Mapped["Run"] = relationship(back_populates="samples")
    plausibility_results: Mapped[list["PlausibilityResult"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )
    prediction_results: Mapped[list["PredictionResult"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )
    decision_events: Mapped[list["DecisionEvent"]] = relationship(
        back_populates="sample", cascade="all, delete-orphan"
    )


class PlausibilityResult(Base):
    """Model-1 output for a sample (append-only; newest is current)."""

    __tablename__ = "plausibility_result"
    __table_args__ = (Index("ix_plaus_sample", "sample_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sample.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    plausibilitaet: Mapped[Optional[str]] = mapped_column(String(16))
    confidence: Mapped[Optional[str]] = mapped_column(String(16))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    signale_pro: Mapped[Optional[list]] = mapped_column(JSONVariant)
    signale_contra: Mapped[Optional[list]] = mapped_column(JSONVariant)
    objektbez_fallback: Mapped[bool] = mapped_column(Boolean, default=False)

    sample: Mapped["Sample"] = relationship(back_populates="plausibility_results")


class PredictionResult(Base):
    """Model-2 output for a sample (append-only; newest is current)."""

    __tablename__ = "prediction_result"
    __table_args__ = (Index("ix_pred_sample", "sample_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sample.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    suggested_wg_name: Mapped[Optional[str]] = mapped_column(Text)
    suggested_wg_id: Mapped[Optional[str]] = mapped_column(String(64))
    confidence: Mapped[Optional[str]] = mapped_column(String(16))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    objektbez_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    ef_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    # How this prediction was produced: 'baseline' (no memory) | 'memory'
    # (LLM with retrieved hints) | 'memoized' (reused a confirmed identical case).
    source: Mapped[Optional[str]] = mapped_column(String(16))

    sample: Mapped["Sample"] = relationship(back_populates="prediction_results")


class DecisionEvent(Base):
    """Historised manual change for a sample (append-only audit trail).

    The newest event per sample is the current decision/remapping; earlier
    events are kept for history.
    """

    __tablename__ = "decision_event"
    __table_args__ = (
        Index("ix_decision_sample_created", "sample_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sample.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # 'plausibility' | 'regrouping' — which stage the decision was made in.
    stage: Mapped[Optional[str]] = mapped_column(String(32))
    # 'accept' | 'reject' | 'manual_wg_change'
    user_action: Mapped[Optional[str]] = mapped_column(String(32))
    # Backend decision label: 'ok' | 'reject' | 'regroup' | 'new_wg'
    decision: Mapped[Optional[str]] = mapped_column(String(16))
    field_changed: Mapped[Optional[str]] = mapped_column(String(32))  # 'decision' | 'wg_name'
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)  # target WG on a remap

    sample: Mapped["Sample"] = relationship(back_populates="decision_events")


class CorrectionMemory(Base):
    """Materialised 'current truth' per sample — the basis for the learning loop.

    One row per sample (upserted): the model's prediction, the human correction
    (if any), and the resulting `outcome`. Built from `prediction_result` +
    newest `decision_event`. The `feature_key` is the deterministic string that
    will be embedded (Step B) for retrieval-augmented prompting.

    Truth = `corrected_wg` when reassigned, else `predicted_wg` when accepted,
    else unknown (outcome 'unreviewed'/'rejected' carry no positive label).
    """

    __tablename__ = "correction_memory"
    __table_args__ = (
        UniqueConstraint("sample_id", name="uq_correction_memory_sample"),
        Index("ix_correction_memory_run", "run_id"),
        Index("ix_correction_memory_outcome", "outcome"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sample.id", ondelete="CASCADE")
    )
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run.id", ondelete="CASCADE"))
    feature_key: Mapped[str] = mapped_column(Text)
    predicted_wg: Mapped[Optional[str]] = mapped_column(Text)
    corrected_wg: Mapped[Optional[str]] = mapped_column(Text)
    # 'reassigned' | 'accepted' | 'rejected' | 'unreviewed'
    outcome: Mapped[str] = mapped_column(String(16), default="unreviewed")
    # Embedding of `feature_key` (text-embedding-3-small). Populated lazily for
    # confirmed rows only (reassigned/accepted/rejected); NULL until embedded.
    embedding = mapped_column(EmbeddingType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Warengruppe(Base):
    """Master data: one Warengruppe in the catalog (replaces the dim Excel files).

    Curated via the CRUD API. The LLM models build their prompt catalog and the
    dashboard reads its emission factors from these rows instead of the source
    Excel. `wg_id` is the stable business key — the hashed `WG Nr.` for imported
    rows, a generated id (`new-<uuid>`) for ones created through the UI. The
    overlay's auxiliary metadata (status/konfidenz/modell/datum) is intentionally
    not persisted; only the prompt-bearing fields are kept editable.
    """

    __tablename__ = "warengruppe"
    __table_args__ = (UniqueConstraint("wg_id", name="uq_warengruppe_wg_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    wg_id: Mapped[str] = mapped_column(String(64))
    wg_name: Mapped[str] = mapped_column(Text)
    beschreibung: Mapped[Optional[str]] = mapped_column(Text)
    # Bullet examples for the prompt, stored as JSON string arrays.
    examples_enthalten: Mapped[list] = mapped_column(JSONVariant, default=list)
    examples_nicht_enthalten: Mapped[list] = mapped_column(JSONVariant, default=list)
    # Soft-delete flag. Inactive Warengruppen are hidden from the prompt catalog
    # (no longer suggested by the LLM) but stay available for historical emission
    # calculation (`ef_lookup`) and the audit trail — and can be re-activated.
    # ORM inserts always set this via the Python default; existing rows are
    # back-filled by the additive migration in `core/db.py::init_db()`.
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    emissionsfaktoren: Mapped[list["Emissionsfaktor"]] = relationship(
        back_populates="warengruppe",
        cascade="all, delete-orphan",
        order_by="Emissionsfaktor.jahr",
    )


class Emissionsfaktor(Base):
    """One spend-based emission factor for a Warengruppe in a reporting year.

    Value is kg CO2e per EUR; the unit is implicit and not stored. One row per
    (warengruppe, jahr); the dashboard uses the most recent year present.
    """

    __tablename__ = "emissionsfaktor"
    __table_args__ = (
        UniqueConstraint("warengruppe_id", "jahr", name="uq_emissionsfaktor_wg_jahr"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    warengruppe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warengruppe.id", ondelete="CASCADE")
    )
    jahr: Mapped[int] = mapped_column(Integer)
    wert: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    warengruppe: Mapped["Warengruppe"] = relationship(back_populates="emissionsfaktoren")


class EnrichmentBatch(Base):
    """One bulk LLM-enrichment run over a selection of Warengruppen.

    Mirrors `Run`'s lifecycle so the frontend can poll progress the same way:
    `done` is COUNT(proposal) over `total`, status goes running → done | failed,
    and a batch left 'running' after a restart is reset to 'failed' in
    `core/db.py::init_db()`. The atomic (single-WG) path does NOT persist here —
    only the wizard's bulk runs do.
    """

    __tablename__ = "enrichment_batch"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Lifecycle: 'running' → 'done' | 'failed'.
    status: Mapped[str] = mapped_column(String(32), default="running")
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Progress denominator; numerator is COUNT(proposal) read live from the DB.
    total: Mapped[Optional[int]] = mapped_column(Integer)
    # Run parameters: the default per-field plan (JSON) + history toggle + model.
    plan: Mapped[Optional[dict]] = mapped_column(JSONVariant)
    use_history: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_name: Mapped[Optional[str]] = mapped_column(String(128))
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    api_calls: Mapped[Optional[int]] = mapped_column(Integer)

    proposals: Mapped[list["EnrichmentProposal"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class EnrichmentProposal(Base):
    """One Warengruppe's enrichment proposal within a batch — a review-queue item.

    Holds both the *before* snapshot (for the diff) and the LLM *proposal*, plus
    the plan used and the review state. Accepting a proposal writes it to the
    Warengruppe via the normal `warengruppen.update()` path (which resets the
    catalog cache); the proposal is only a staging record, never a value seam for
    the delete-protection.
    """

    __tablename__ = "enrichment_proposal"
    __table_args__ = (Index("ix_enrichment_proposal_batch", "batch_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("enrichment_batch.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    wg_id: Mapped[str] = mapped_column(String(64))
    wg_name: Mapped[str] = mapped_column(Text)
    plan: Mapped[Optional[dict]] = mapped_column(JSONVariant)

    # Before-snapshot (the values the proposal was generated from).
    current_beschreibung: Mapped[Optional[str]] = mapped_column(Text)
    current_examples_enthalten: Mapped[list] = mapped_column(JSONVariant, default=list)
    current_examples_nicht_enthalten: Mapped[list] = mapped_column(JSONVariant, default=list)

    # LLM proposal.
    proposed_beschreibung: Mapped[Optional[str]] = mapped_column(Text)
    proposed_examples_enthalten: Mapped[list] = mapped_column(JSONVariant, default=list)
    proposed_examples_nicht_enthalten: Mapped[list] = mapped_column(JSONVariant, default=list)
    konfidenz: Mapped[Optional[int]] = mapped_column(Integer)
    anmerkung: Mapped[Optional[str]] = mapped_column(Text)
    status_llm: Mapped[Optional[str]] = mapped_column(String(32))
    diff_kurz: Mapped[Optional[str]] = mapped_column(Text)
    history_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Review state: 'pending' → 'accepted' | 'rejected' | 'superseded' (refined).
    state: Mapped[str] = mapped_column(String(16), default="pending")
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))

    batch: Mapped["EnrichmentBatch"] = relationship(back_populates="proposals")
