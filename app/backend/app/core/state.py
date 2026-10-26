"""In-memory session state for the demo backend.

Single-tenant on purpose: the prototype is meant to drive one user
through the four-step flow (upload → plausibility → regrouping →
dashboard). State lives in process memory and is reset on restart.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

import pandas as pd


@dataclass
class SessionState:
    invoices: Optional[pd.DataFrame] = None
    invoices_filename: Optional[str] = None
    plausibility_df: Optional[pd.DataFrame] = None
    prediction_df: Optional[pd.DataFrame] = None
    user_decisions: dict[int, dict] = field(default_factory=dict)
    # Pointer to the persisted Run (system of record). Set on upload; every
    # downstream stage write-through-persists against it. None when the active
    # run could not be persisted (DB down) — the live flow continues regardless.
    run_id: Optional[uuid.UUID] = None


_state = SessionState()
_lock = Lock()


def get_state() -> SessionState:
    return _state


def reset() -> None:
    global _state
    with _lock:
        _state = SessionState()
