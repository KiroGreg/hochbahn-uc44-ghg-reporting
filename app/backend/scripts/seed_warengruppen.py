"""Seed the Warengruppen catalog (warengruppe + emissionsfaktor) from Excel.

One-time import from the LLM-enriched overlay (catalog: name / description /
inclusive + exclusive examples) and the spend-based emission-factor Excel
(per-year EF). The master dim Excel is not needed — the overlay already carries
the canonical name and descriptions. The standalone CLI models in
`Use Case/models/` keep reading Excel directly; this only populates the web
app's DB, which is then the authoritative source for the running app.

Usage (locally, from app/backend/):
    python scripts/seed_warengruppen.py            # refuse if table not empty
    python scripts/seed_warengruppen.py --force    # clear and reload

In the container:
    docker compose exec backend python scripts/seed_warengruppen.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `app.*` importable regardless of cwd (mirrors scripts/dump_openapi.py).
_backend_root = Path(__file__).resolve().parents[1]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.core.db import init_db  # noqa: E402
from app.services import warengruppen  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the Warengruppen catalog from the source Excel files."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear and reload even if the table already contains rows.",
    )
    args = parser.parse_args()

    init_db()  # ensure the tables exist before seeding
    try:
        result = warengruppen.seed_from_excel(force=args.force)
    except RuntimeError as exc:
        print(f"Aborted: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Seeded {result['warengruppen']} Warengruppen and "
        f"{result['emissionsfaktoren']} emission factors."
    )


if __name__ == "__main__":
    main()
