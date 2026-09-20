from typing import Dict, Any
from mvp.engine.handicap.history import HANDICAP_HISTORY


class HandicapAdminAPI:
    """
    Admin API for viewing handicap history and changes.
    """

    def get_history(self, player_id: str = None) -> Dict[str, Any]:
        if player_id:
            filtered = [h for h in HANDICAP_HISTORY if h["player_id"] == player_id]
            return {"history": filtered}

        return {"history": HANDICAP_HISTORY}

    def get_recent_changes(self, limit: int = 10) -> Dict[str, Any]:
        return {"recent": HANDICAP_HISTORY[-limit:]}