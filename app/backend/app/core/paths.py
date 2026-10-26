"""Path resolution for the backend.

The backend reuses the model classes that already live under
`Use Case/models/` and the source Excel files under `Use Case/`.
"""
from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR.parent
PROJECT_ROOT = APP_DIR.parent

USE_CASE_DIR = PROJECT_ROOT / "Use Case"
MODELS_DIR = USE_CASE_DIR / "models"
DATA_DIR = USE_CASE_DIR

PLAUSIBILITY_DIR = MODELS_DIR / "plausibility_model"
PREDICTION_DIR = MODELS_DIR / "prediction_model"

DEFAULT_INVOICES = DATA_DIR / "HHA_Rechnungsdaten_reduced_hashed_5000.xlsx"
DIM_WARENGRUPPEN = DATA_DIR / "dimWarengruppen_hashed.xlsx"
ENV_FILE = MODELS_DIR / ".env"
