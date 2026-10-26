"""Build the retrieval-augmented prompt hint + memoization decision per row.

Given a row's feature string, one retrieval call yields the nearest confirmed
corrections. Two outputs:
- **Memoization:** if the closest confirmed case is near-identical (sim >=
  memo_threshold) and has a known truth, return that label → skip the LLM.
- **Hint:** otherwise, format the relevant cases as an additive XML block for the
  prediction prompt — but only when the neighbourhood actually contains a known
  confusion (gate), to avoid noise where the model is already reliable.
"""
from __future__ import annotations

from typing import Optional

from ..core import features
from ..services import memory


def _short(feature_key: str) -> str:
    """Drop the constant domain framing so the example stays compact."""
    return feature_key.split(features._FRAMING, 1)[-1].strip() or feature_key


def format_hint(neighbors: list[dict]) -> str:
    """XML block of similar confirmed cases. Empty if no known confusion."""
    falsch = [n for n in neighbors if n["outcome"] == "reassigned" and n["corrected_wg"]]
    korrekt = [n for n in neighbors if n["outcome"] == "accepted" and n["truth_wg"]]
    if not falsch:
        return ""  # gate: only intervene where there's evidence of difficulty

    lines = [
        "Berücksichtige ähnliche, bereits von Fachprüfer:innen entschiedene Fälle "
        "(leite daraus Muster ab, keine starren Regeln):",
        "<historische_aehnliche_faelle>",
        "  <falsch_klassifiziert>",
    ]
    for n in falsch:
        lines.append(
            f"    <fall><merkmale>{_short(n['feature_key'])}</merkmale>"
            f"<modell_tippte>{n['predicted_wg']}</modell_tippte>"
            f"<korrekt_war>{n['corrected_wg']}</korrekt_war></fall>"
        )
    lines.append("  </falsch_klassifiziert>")
    if korrekt:
        lines.append("  <korrekt_klassifiziert>")
        for n in korrekt:
            lines.append(
                f"    <fall><merkmale>{_short(n['feature_key'])}</merkmale>"
                f"<klasse>{n['truth_wg']}</klasse></fall>"
            )
        lines.append("  </korrekt_klassifiziert>")
    lines.append("</historische_aehnliche_faelle>")
    return "\n".join(lines)


def augment_row(
    raw: dict,
    top_n: int = 6,
    threshold: float = 0.82,
    memo_threshold: float = 0.99,
) -> tuple[Optional[str], str]:
    """Return (memoized_truth_wg | None, hint_xml).

    1. Memoize on an **exact** feature_key match (literally repeated invoice
       line) — safe and deterministic.
    2. Optional cosine memoization only at a *very* high threshold (default
       0.99), since templated texts cluster high.
    3. Otherwise retrieve neighbours and format a hint (gated on confusion).
    """
    fkey = features.feature_key_from_raw(raw)

    exact = memory.find_exact_truth(fkey)
    if exact:
        return (exact, "")

    neighbors = memory.retrieve(fkey, top_n=top_n, threshold=threshold)
    if neighbors:
        top = neighbors[0]
        if top["similarity"] >= memo_threshold and top["truth_wg"]:
            return (top["truth_wg"], "")
    return (None, format_hint(neighbors))
