from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "backend"))

from app.core.db import init_db  # noqa: E402
from app.core.state import SessionState  # noqa: E402
from app.services import dashboard as dashboard_svc  # noqa: E402


class _StubCatalog:
    rows = []


class TestDashboardYearSelection(unittest.TestCase):
    def test_build_uses_selected_year_for_ef_lookup(self) -> None:
        state = SessionState()
        state.invoices = pd.DataFrame(
            [{"Warengruppe": "A", "Kostenart": "K", "Betrag": 100.0}]
        )
        state.plausibility_df = None
        state.prediction_df = None

        init_db()
        with patch(
            "app.services.dashboard.warengruppen_svc.ef_lookup",
            return_value={"A": 1.0},
        ) as ef_lookup, patch(
            "app.services.dashboard.warengruppen_svc.available_years",
            return_value=[2024],
        ), patch(
            "app.services.dashboard.prediction_svc.get_catalog",
            return_value=_StubCatalog(),
        ):
            dashboard_svc.build(state, jahr=2024)

        ef_lookup.assert_called_once_with(2024)


if __name__ == "__main__":
    unittest.main()
