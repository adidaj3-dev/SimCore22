# SimCore22

An all-in-one system for indoor golf venues: it reads rounds from GSPro and
launch monitors, scores them automatically, keeps handicaps, and drives live
leaderboards for leagues and tournaments. Windows, Python 3.12+ (developed on
3.14).

> **Status: proof of concept.** Everything below is built and tested without
> hardware. The first run on a real bay (Foresight Falcon / Hawk + GSPro) is
> the next milestone - see [Status](#status).

## Status

| Area | State |
|---|---|
| Capture the GSPro window (any size / position / monitor) | built, tested on stand-in windows |
| Read GSPro's scorecard, verified against its printed totals | built; works on the one real 18-hole card; 9-hole layout is an **assumption** |
| Round lifecycle: ends on GSPro's scorecard, quit / save any time | built, tested |
| Append-only round log with the scorecard screenshot of every round | built, tested |
| Leaderboard / round summary / admin snapshot JSON | built, tested |
| Live player and hole tracking from the HUD | needs calibration on a bay |
| Live shot data (ball speed, carry, ...) | **not working yet** - needs real launch-monitor packets (`packet_capture`) |
| Handicap updates | engine built; leagues (schedule, round numbers) not configurable yet |
| Database, admin portal, on-screen leaderboards, POS, scheduling | not started |

## How it works

```
Foresight listener (placeholder protocol) ─┐
GSPro screen capture + OCR  ───────────────┼─► EventDispatcher ─► engine ─► leaderboard
   - player / hole tracking                                          │        handicap
   - end-of-round scorecard                                          │        analyzer
                                                                     ├─► state/*.json      (live, overwritten)
                                                                     └─► data/rounds.jsonl (permanent log)
```

Until there is official API access, reading GSPro's screen is the bridge. When a
real data feed exists it plugs in as one more event source; nothing downstream
changes.

## Set up a bay PC (once)

Double-click **`setup_bay.bat`**. It installs Python 3.14 and Tesseract
(via winget), creates `.venv`, installs `requirements.txt`, and runs the
diagnostic. Then **`run_bay.bat`** starts the engine.

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
database should store. Read it with `simcore22.engine.round_log.read_rounds()`.

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

## Tools

Run from the project folder, e.g. `.venv\Scripts\python -m simcore22.tools.bay_check`.

| Tool | What it's for |
|---|---|
| `simcore22.tools.bay_check` | What's running, what the capture sees, a verdict. Saves `captures/<time>/` (screenshots, `report.json`) - send that folder back when something looks wrong |
| `simcore22.tools.packet_capture` | Record what a launch monitor / simulator really sends (hex dump file) so it can be decoded |
| `simcore22.tools.capture_screenshot` | Save one frame of the GSPro picture |
| `simcore22.tools.ocr_calibration` | Draw the HUD regions on that frame and save them as the OCR layout |
| `simcore22.tools.fake_round_feed` | Demo data with no hardware, for developing a leaderboard screen |
| `simcore22.tools.diagnostic_dashboard` | Live "is data flowing / are the files updating" board |
| `simcore22.ui.live_leaderboard`, `round_summary`, `admin_view` | Console viewers for `state/*.json` (see `examples/state/` for the file shapes) |

## Project layout

- `simcore22/engine/engine_loop.py` - entry point; wires ingestion → engine → outputs
- `simcore22/engine/engine.py` - live session state (players, holes, handicaps)
- `simcore22/engine/ocr/` - window capture, scorecard reader, HUD reading
  (`layouts/*.json` are fractions of the game picture)
- `simcore22/engine/ingestion/` - event bus; Foresight and TrackMan parsers (placeholders)
- `simcore22/engine/{leaderboard,analyzer,handicap,scheduling,models,admin}/` - scoring
- `simcore22/engine/round_log.py`, `state_writer.py` - the permanent log, the live JSON
- `simcore22/tools/`, `simcore22/ui/` - diagnostics and console viewers
- `examples/` - sample output files
- `tests/` - `python -m pytest`

## Developing

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check simcore22 tests
```

Generated folders (`state/`, `data/`, `logs/`, `captures/`) are git-ignored.
