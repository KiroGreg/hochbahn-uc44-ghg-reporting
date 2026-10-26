"""OpenAI text embeddings for the correction-memory retrieval.

Resolves the API key like the standalone models do (env first, then the
baked-in `Use Case/models/.env`). Default model `text-embedding-3-small`
(1536-dim, very cheap); override via `UC44_EMBED_MODEL`.
"""
from __future__ import annotations

import os
import threading

from dotenv import load_dotenv
from openai import OpenAI

from ..core.paths import ENV_FILE

MODEL = os.getenv("UC44_EMBED_MODEL", "text-embedding-3-small")

_client: OpenAI | None = None
_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                key = os.getenv("OPENAI_API_KEY")
                # The container sets OPENAI_API_KEY="" (empty default); fall back
                # to the baked-in models/.env with override=True, mirroring how
                # the standalone models resolve the key.
                if not key and ENV_FILE.exists():
                    load_dotenv(ENV_FILE, override=True)
                    key = os.getenv("OPENAI_API_KEY")
                _client = OpenAI(api_key=key)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input (order preserved)."""
    if not texts:
        return []
    resp = _get_client().embeddings.create(model=MODEL, input=texts)
    return [d.embedding for d in resp.data]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
