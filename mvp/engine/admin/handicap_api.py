import dataclasses
from typing import Dict, Any

from mvp.engine.handicap.history import get_history, get_history_for_player


class HandicapAdminAPI:
    """
    Admin API for viewing handicap history and changes.
    """

    def get_history(self, player_id: str = None) -> Dict[str, Any]:
        entries = get_history_for_player(player_id) if player_id else get_history()
        return {"history": [dataclasses.asdict(e) for e in entries]}

    def get_recent_changes(self, limit: int = 10) -> Dict[str, Any]:
        entries = get_history()[-limit:]
        return {"recent": [dataclasses.asdict(e) for e in entries]}