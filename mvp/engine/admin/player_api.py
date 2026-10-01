from typing import Dict, Any
from mvp.engine.handicap.handicap_engine import HandicapEngine
from mvp.engine.handicap.admin_override import apply_admin_override


class PlayerAdminAPI:
    """
    Admin API for viewing and managing player handicap data.
    """

    def __init__(self):
        self.engine = HandicapEngine()

    def get_player_handicap(self, player) -> Dict[str, Any]:
        """
        Expects a player object with:
        - player.simcore_index
        - player.outdoor_handicap
        """
        return {
            "player_id": player.id,
            "simcore_index": player.simcore_index,
            "projected_outdoor_index": self.engine.projected_outdoor_index(player.simcore_index),
            "outdoor_handicap": player.outdoor_handicap,
        }

    def override_handicap(self, player, simcore_value=None, outdoor_value=None):
        result = apply_admin_override(
            player_id=player.id,
            current_simcore=player.simcore_index,
            current_outdoor=player.outdoor_index,
            simcore_override=simcore_value,
            outdoor_override=outdoor_value,
        )

        player.simcore_index = result["simcore_index"]
        player.outdoor_index = result["outdoor_index"]

        return result