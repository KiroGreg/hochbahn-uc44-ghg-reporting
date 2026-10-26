"""Dump the FastAPI OpenAPI document to a JSON file.

Used by the frontend's `openapi:dump` npm script so the Angular
client can be regenerated without keeping the server running.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `app.main` importable regardless of cwd.
_backend_root = Path(__file__).resolve().parents[1]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.main import app  # noqa: E402


def _patch_binary_fields(node):
    """Rewrite OpenAPI 3.1 `contentMediaType: application/octet-stream`
    into 3.0-style `type: string, format: binary` so typescript-angular's
    generator emits `FormData` rather than URL-encoded params for file
    uploads."""
    if isinstance(node, dict):
        if node.get("contentMediaType") == "application/octet-stream":
            node.pop("contentMediaType", None)
            node["type"] = "string"
            node["format"] = "binary"
        for v in node.values():
            _patch_binary_fields(v)
    elif isinstance(node, list):
        for v in node:
            _patch_binary_fields(v)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json").resolve()
    spec = app.openapi()
    _patch_binary_fields(spec)
    out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
