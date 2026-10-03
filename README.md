# SimCore22 MVP

Indoor-golf league engine: reads rounds from GSPro / launch monitors, scores
them, updates handicaps, and writes a live leaderboard. Windows, Python 3.12+
(developed on 3.14).

## What it does today

```
Foresight listener (placeholder protocol) ─┐
GSPro screen capture + OCR  ───────────────┼─► EventDispatcher ─► engine ─► leaderboard
   - player / hole tracking (needs calibration)                      │        handicap
   - round-end scorecard, verified against GSPro's printed totals    │        analyzer
                                                                     └─► state/*.json
```

- **Working and tested:** scorecard reader, window capture, engine event
  flow, leaderboard / round summary / admin snapshot JSON.
- **Not working yet:** live shot stats from the screen (`parse_shot_tiles` is
  a stub), and the real Foresight wire protocol (nobody has captured a real
  Falcon/Hawk packet yet - use `mvp/tools/falcon_packet_decoder.py` on a bay).
- **Not wired up:** `mvp/engine/server/api.py` (web leaderboard), TrackMan.

## Set up a bay PC (once)

Double-click **`setup_bay.bat`**. It installs Python 3.14 and Tesseract
(via winget), creates `.venv`, installs `requirements.txt`, and runs the
diagnostic. Then **`run_bay.bat`** starts the engine.

## Screen capture

The engine captures the GSPro **window**, cropped to its picture (no title
bar, borders, or position on screen involved), so GSPro doesn't need to fill
the display. Requirements:

- GSPro must be **Windowed or Borderless**, not exclusive fullscreen
  (exclusive fullscreen captures as black; the engine logs a warning if so).
- Keep GSPro on top of its monitor - other windows covering it show up in
  the capture.
- GSPro's window title must contain `GSPro`. If it doesn't, set the
  `SIMCORE_WINDOW_TITLE` environment variable. `bay_check` lists real titles.

### Diagnose / calibrate

```bash
python -m mvp.tools.bay_check            # what's running, what the capture sees, verdict
python -m mvp.tools.capture_screenshot   # save one frame of the GSPro picture
python -m mvp.tools.ocr_calibration      # draw the HUD boxes on that frame
```

`bay_check` writes `captures/<timestamp>/` (screenshots, `game_window.png`,
`report.json`) - send that folder back when something looks wrong.

## Project layout

- `mvp/engine/engine_loop.py` - entry point; wires ingestion → engine → outputs
- `mvp/engine/ocr/` - window capture, Tesseract setup, scorecard + HUD reading,
  layouts (`layouts/*.json`, fractions of the game picture)
- `mvp/engine/ingestion/` - event bus and Foresight / TrackMan parsers
- `mvp/engine/{leaderboard,analyzer,handicap,scheduling,models}/` - scoring
- `mvp/tools/` - bay diagnostics and calibration
- `state/` - JSON output the leaderboard screens read
- `tests/` - `python -m pytest tests`

## Developing

```bash
.venv\Scripts\python -m pytest tests
```
