import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mvp.engine.leaderboard.leaderboard import Leaderboard

logger = logging.getLogger(__name__)

app = FastAPI(title="SimCore22 Live API")

leaderboard = Leaderboard()

# Allow local UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/leaderboard")
def get_leaderboard():
    """
    Returns the current live leaderboard.
    """
    try:
        data = leaderboard.to_dict() if hasattr(leaderboard, "to_dict") else {}
        return {"status": "ok", "leaderboard": data}
    except Exception as e:
        logger.error(f"Failed to serialize leaderboard: {e}")
        return {"status": "error", "leaderboard": {}}
