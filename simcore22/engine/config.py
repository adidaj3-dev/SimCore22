"""Settings. Each can be overridden with the environment variable shown."""
import os

# --- Display ------------------------------------------------------------------
# Shown as the title of the live leaderboard (e.g. "Tuesday Night League"). Unset =
# the board just says "Live Leaderboard" rather than inventing a league name.
LEAGUE_NAME = os.environ.get("SIMCORE_LEAGUE_NAME", "").strip() or None

# --- Launch-monitor shot feed ------------------------------------------------
# OFF by default. Nothing has decoded a real Falcon/Hawk stream yet, so there is
# no feed to connect to; turn it on by setting SIMCORE_FEED_PORT to the port
# `python -m simcore22.tools.bay_check` / `packet_capture` found on the bay.
FEED_HOST = os.environ.get("SIMCORE_FEED_HOST", "127.0.0.1")
_feed_port = os.environ.get("SIMCORE_FEED_PORT", "").strip()
FEED_PORT = int(_feed_port) if _feed_port else None

# GSPro Connect: GSPro itself LISTENS here and the launch-monitor software
# connects to it. The engine must never connect to this port - GSPro accepts a
# single client, so we could take FSX's place and break the bay.
GSPRO_CONNECT_PORT = 921

# --- Screen capture ---------------------------------------------------------
# Text that appears in GSPro's window title. The capture crops to that
# window's drawable area, so GSPro can be windowed, bordered, or on any
# monitor. `python -m simcore22.tools.bay_check` lists the real titles - if GSPro's
# is different on your bay, set the SIMCORE_WINDOW_TITLE environment variable
# (or edit the default below).
# Set it to "" to fall back to capturing a whole monitor (GSPro must then
# fill that monitor exactly, or the OCR layouts will be off).
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
