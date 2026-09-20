def display_dashboard(analysis: dict, summary: str) -> None:
    """
    Clean, modern SimCore22 dashboard display.
    Accepts:
      - analysis: dict returned by analyze_round()
      - summary: formatted summary string
    """

    print("\n==================== SIMCORE22 DASHBOARD ====================")

    # --- Core Round Metrics ---
    print(f"Total Score: {analysis.get('total_score', 'N/A')}")
    print(f"Score vs Par: {analysis.get('score_relative_to_par', 'N/A'):+}")
    print(f"Gross Score: {analysis.get('gross_score', 'N/A')}")
    print(f"Net Score: {analysis.get('net_score', 'N/A')}")

    # --- Ball & Shot Metrics ---
    print("\n--- Ball & Shot Performance ---")
    print(f"Total Shots: {analysis.get('total_shots', 'N/A')}")
    print(f"Avg Ball Speed: {analysis.get('avg_ball_speed', 'N/A')}")
    print(f"Max Ball Speed: {analysis.get('max_ball_speed', 'N/A')}")
    print(f"Avg Carry: {analysis.get('avg_carry', 'N/A')}")
    print(f"Max Carry: {analysis.get('max_carry', 'N/A')}")
    print(f"Offline Avg: {analysis.get('offline_avg', 'N/A')}")
    print(f"Left Miss %: {analysis.get('left_miss_pct', 'N/A')}")
    print(f"Right Miss %: {analysis.get('right_miss_pct', 'N/A')}")
    print(f"Penalties: {analysis.get('penalties', 0)}")

    # --- Accuracy Metrics ---
    print("\n--- Accuracy ---")
    print(f"FIR: {analysis.get('fir', 'N/A')}")
    print(f"GIR: {analysis.get('gir', 'N/A')}")
    print(f"Avg Proximity: {analysis.get('avg_proximity', 'N/A')}")
    print(f"Scrambling: {analysis.get('scrambling', 'N/A')}")
    print(f"Up & Down: {analysis.get('up_and_down', 'N/A')}")
    print(f"Sand Saves: {analysis.get('sand_saves', 'N/A')}")

    # --- Putting Metrics ---
    print("\n--- Putting ---")
    print(f"Total Putts: {analysis.get('total_putts', 'N/A')}")
    print(f"Avg Putts: {analysis.get('avg_putts', 'N/A')}")
    print(f"3-Putt Avoidance: {analysis.get('three_putt_avoidance', 'N/A')}")
    print(f"Birdie Conversion: {analysis.get('birdie_conversion', 'N/A')}")
    print(f"Par Save Rate: {analysis.get('par_save_rate', 'N/A')}")

    # --- Par Breakdown ---
    print("\n--- Par Scoring ---")
    print(f"Par 3 Avg: {analysis.get('par3_avg', 'N/A')}")
    print(f"Par 4 Avg: {analysis.get('par4_avg', 'N/A')}")
    print(f"Par 5 Avg: {analysis.get('par5_avg', 'N/A')}")
    print(f"Best Hole: {analysis.get('best_hole', 'N/A')}")
    print(f"Worst Hole: {analysis.get('worst_hole', 'N/A')}")

    # --- League / Points ---
    print("\n--- League / Points ---")
    print(f"Stableford Points: {analysis.get('stableford_points', 'N/A')}")
    print(f"Quota Points: {analysis.get('quota_points', 'N/A')}")
    print(f"Points Earned: {analysis.get('points_earned', 'N/A')}")
    print(f"Points Needed: {analysis.get('points_needed', 'N/A')}")

    # --- Handicap ---
    print("\n--- Handicap ---")
    print(f"SimCore Index (Before): {analysis.get('simcore_index_before', 'N/A')}")
    print(f"SimCore Index (After): {analysis.get('simcore_index_after', 'N/A')}")
    print(f"Index Change: {analysis.get('simcore_index_delta', 'N/A')}")
    print(f"Outdoor Handicap Start: {analysis.get('outdoor_handicap_start', 'N/A')}")
    print(f"Outdoor vs SimCore: {analysis.get('outdoor_vs_simcore', 'N/A')}")

    # --- Summary ---
    print("\n-------------------- SESSION SUMMARY --------------------")
    print(summary)

    print("==============================================================\n")
