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

## How a round works

GSPro shows its scorecard when the chosen number of holes (9, 18, any) is
finished - never mid-round. The engine watches for that screen (the one with
the **PLAY AGAIN!** button), reads it, and finishes the round. A scorecard
without that button is treated as a mid-round peek and ignored.

| How it ended | Status | Handicap can change? |
|---|---|---|
| End-of-round scorecard appears | `completed` | yes (league rounds) |
| Someone types `end` in the engine window | `ended_early` | no |
| No activity for 20 min (`SIMCORE_IDLE_MINUTES`) | `abandoned` | no |
| Someone types `save` | `snapshot` (round continues) | no |

Every way keeps all data and stats; a hole left unfinished when someone quits
is kept but not counted as a score. Then the next round starts clean
(handicaps and the current player carry over). Type `help` in the engine
window for the commands: `end`, `save`, `status`.

Scores come from GSPro's scorecard where it **adds up** (each player's holes
checked against the printed OUT / IN totals); otherwise from our shot count.
The scorecard also adds players the live tracking missed, so a round is still
recorded if HUD tracking never worked.

## Round log

Every finished round is appended to `data/rounds.jsonl` - one line per player
per round: status, hole-by-hole scores, where the scores came from
(`scorecard_ocr_verified` = GSPro's own scorecard, `shot_tally` = our shot
count), every shot captured, the stats, and the raw scorecard reading. Each
end-of-round scorecard screenshot is kept in `data/scorecards/` so any logged
round can be checked against what GSPro showed. A `snapshot` line shares its
`round_id` with the round's final line - use the latest line per `round_id`.
The log is append-only, survives restarts, and is git-ignored (it holds player
names). It is not a database - it's the evidence for deciding what the
database should store. Read it with `mvp.engine.round_log.read_rounds()`.

**Assumption to confirm on the bay:** the 9-hole scorecard layout (columns
1-9, OUT, optional TOT) is a guess; only the 18-hole card has been checked
against a real GSPro card.

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
