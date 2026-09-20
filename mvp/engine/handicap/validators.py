# mvp/engine/handicap/validators.py

def validate_round_data(stats: dict) -> dict:
    """
    Validate and sanitize round statistics extracted from engine state.
    Ensures all required fields exist and fall within safe bounds.
    """

    safe = {}

    # Score relative to par
    try:
        safe["score_relative_to_par"] = float(stats.get("score_relative_to_par", 0))
    except Exception:
        safe["score_relative_to_par"] = 0
    # No strict bounds — players can shoot very high or low

    # Round quality score (0–10)
    try:
        safe["round_quality_score"] = float(stats.get("round_quality_score", 3.5))
    except Exception:
        safe["round_quality_score"] = 3.5
    safe["round_quality_score"] = min(max(safe["round_quality_score"], 0), 10)

    # FIR (0–1)
    try:
        safe["fir"] = float(stats.get("fir", 0.5))
    except Exception:
        safe["fir"] = 0.5
    safe["fir"] = min(max(safe["fir"], 0), 1)

    # GIR (0–1)
    try:
        safe["gir"] = float(stats.get("gir", 0.3))
    except Exception:
        safe["gir"] = 0.3
    safe["gir"] = min(max(safe["gir"], 0), 1)

    # Avg putts (0–4)
    try:
        safe["avg_putts"] = float(stats.get("avg_putts", 1.8))
    except Exception:
        safe["avg_putts"] = 1.8
    safe["avg_putts"] = min(max(safe["avg_putts"], 0), 4)

    # Penalties (>= 0)
    try:
        safe["penalties"] = int(stats.get("penalties", 0))
    except Exception:
        safe["penalties"] = 0
    safe["penalties"] = max(safe["penalties"], 0)

    # Old index (0–54)
    try:
        safe["old_index"] = int(stats.get("old_index", 0))
    except Exception:
        safe["old_index"] = 0
    safe["old_index"] = max(0, min(54, safe["old_index"]))

    return safe
