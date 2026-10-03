# WebSocket listener for SimCore22 → GSPro
GSPro_WS_HOST = "0.0.0.0"
GSPro_WS_PORT = 8765

# GSPro Connect TCP endpoint
GSPRO_TCP_HOST = "127.0.0.1"
GSPRO_TCP_PORT = 921

# --- Screen capture ---------------------------------------------------------
# Text that appears in GSPro's window title. The capture crops to that
# window's drawable area, so GSPro can be windowed, bordered, or on any
# monitor. `python -m mvp.tools.bay_check` lists the real titles - if GSPro's
# is different on your bay, set the SIMCORE_WINDOW_TITLE environment variable
# (or edit the default below).
# Set it to "" to fall back to capturing a whole monitor (GSPro must then
# fill that monitor exactly, or the OCR layouts will be off).
import os

CAPTURE_WINDOW_TITLE = os.environ.get("SIMCORE_WINDOW_TITLE", "GSPro")
CAPTURE_MONITOR_INDEX = int(os.environ.get("SIMCORE_MONITOR", "1"))  # only used when title is ""

# --- Rounds -----------------------------------------------------------------
# A round normally ends when GSPro shows its end-of-round scorecard. These are
# the safety nets for rounds that never get there (player quits, walks away).
# No shots / hole changes / scores for this long = the round is abandoned and
# saved as-is. It's a guess: long enough for a player waiting on friends, short
# enough that the next group isn't stuck in the previous round. Tune on the bay.
ROUND_IDLE_TIMEOUT_MINUTES = float(os.environ.get("SIMCORE_IDLE_MINUTES", "20"))

# Keep a PNG of every end-of-round scorecard (data/scorecards/) so each logged
# round can be checked against what GSPro actually showed.
SAVE_SCORECARD_IMAGES = True
