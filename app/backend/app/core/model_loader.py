"""Load the existing PlausibilityModel and PredictionModel classes.

Both files are named `model.py` in different directories, so we import
them via importlib under unique module names to avoid clashes. We also
add `Use Case/models/` to sys.path so the model files' own
`from _shared.catalog import ...` works at import time.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from .paths import MODELS_DIR, PLAUSIBILITY_DIR, PREDICTION_DIR

_models_str = str(MODELS_DIR)
if _models_str not in sys.path:
    sys.path.insert(0, _models_str)


def _load(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_plaus = _load("uc44_plausibility_model", PLAUSIBILITY_DIR / "model.py")
_pred = _load("uc44_prediction_model", PREDICTION_DIR / "model.py")

PlausibilityModel = _plaus.PlausibilityModel
PredictionModel = _pred.PredictionModel
load_plaus_config = _plaus.load_config
load_pred_config = _pred.load_config

# Shared catalog loader — re-exported so service code can import it
# without touching sys.path itself.
from _shared.catalog import (  # noqa: E402
    WarengruppenCatalog,
    load_warengruppen,
)

PLAUSIBILITY_CONFIG_PATH = PLAUSIBILITY_DIR / "config.yml"
PREDICTION_CONFIG_PATH = PREDICTION_DIR / "config.yml"
