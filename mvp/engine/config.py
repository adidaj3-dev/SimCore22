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
