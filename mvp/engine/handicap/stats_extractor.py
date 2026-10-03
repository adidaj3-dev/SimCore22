# mvp/engine/handicap/stats_extractor.py

"""
Extracts round-level statistics from the engine state (RoundState → HoleState)
for use by the handicap engine.

This replaces the old ingestion-based stats model and ensures that handicap
calculations are driven entirely by engine state.
"""

from __future__ import annotations

from typing import Dict

from mvp.engine.engine import RoundState


def extract_stats_from_round(round_state: RoundState) -> Dict:
    """
    Convert RoundState → HoleState objects into a normalized stats dictionary.

    Output keys:
        - score_relative_to_par
        - round_quality_score
        - fir
        - gir
        - avg_putts
        - penalties
        - old_index   (if stored in RoundState)
    """

    holes = round_state.holes.values()
    if not holes:
        return {
            "score_relative_to_par": 0,
            "round_quality_score": 0,
            "fir": 0,
            "gir": 0,
            "avg_putts": 2.0,
            "penalties": 0,
            "old_index": getattr(round_state, "handicap_index", 0),
        }

    # ------------------------------------------------------------
    # Score relative to par
    # ------------------------------------------------------------
    total_strokes = 0
    total_par = 0

    for h in holes:
        if h.gross_score is not None:
            total_strokes += h.gross_score
        else:
            total_strokes += h.strokes  # fallback

        if h.par is not None:
            total_par += h.par

    score_relative_to_par = total_strokes - total_par

    # ------------------------------------------------------------
    # FIR (fairways in regulation)
    # ------------------------------------------------------------
    fir_count = 0
    fir_possible = 0

    for h in holes:
        # Par 4 or 5 → FIR possible
        if h.par in (4, 5):
            fir_possible += 1

            # Placeholder: later we can track LM landing position
            # For now, assume FIR if strokes <= par - 2 (MVP logic)
            if h.strokes <= (h.par - 2):
                fir_count += 1

    fir = fir_count / fir_possible if fir_possible > 0 else 0

    # ------------------------------------------------------------
    # GIR (greens in regulation)
    # ------------------------------------------------------------
    gir_count = 0
    gir_possible = len(holes)

    for h in holes:
        # GIR if reaching green in par - 2 strokes
        # MVP logic: strokes <= par - 2
        if h.strokes <= (h.par - 2):
            gir_count += 1

    gir = gir_count / gir_possible if gir_possible > 0 else 0

    # ------------------------------------------------------------
    # Avg putts (placeholder until putting OCR is added)
    # ------------------------------------------------------------
    # MVP assumption: 2 putts per hole unless we add putting OCR
    avg_putts = 2.0

    # ------------------------------------------------------------
    # Penalties (placeholder until LM/OCR penalty detection)
    # ------------------------------------------------------------
    penalties = 0

    # ------------------------------------------------------------
    # Round quality score (placeholder)
    # ------------------------------------------------------------
    # MVP logic: inverse of score relative to par
    # Lower score → higher quality
    round_quality_score = max(0, min(10, 10 - (score_relative_to_par / 2)))

    # ------------------------------------------------------------
    # Old index (stored in RoundState if available)
    # ------------------------------------------------------------
    old_index = getattr(round_state, "handicap_index", 0)

    # ------------------------------------------------------------
    # Final stats dict
    # ------------------------------------------------------------
    return {
        "score_relative_to_par": score_relative_to_par,
        "round_quality_score": round_quality_score,
        "fir": fir,
        "gir": gir,
        "avg_putts": avg_putts,
        "penalties": penalties,
        "old_index": old_index,
    }
