# SimCore22 MVP

SimCore22 is a golf analytics engine that ingests shot data from simulators (GSPro, Trackman, FSX), normalizes it into a common model, and feeds an analytics pipeline (analyzer, leaderboard, dashboard, summary).

## Project structure

- `mvp/ui/` – console UI and menus  
- `mvp/data/` – sample data (optional)  
- `mvp/engine/`
  - `ingestion/` – router + parsers + GSPro live listener  
  - `analyzer/` – core analytics  
  - `leaderboard/` – scoring and rankings  
  - `dashboard/` – session‑level metrics  
  - `summary/` – round/session summaries  
  - `logging_config.py` – logging setup  
  - `run_pipeline.py` – end‑to‑end pipeline entrypoint

## Setup

```bash
cd SimCore22_MVP
python -m venv venv
source venv/bin/activate
pip install -r mvp/requirements.txt
