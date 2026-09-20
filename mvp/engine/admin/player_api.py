from typing import Dict, Any
from mvp.engine.handicap.handicap_engine import HandicapEngine


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
            "projected_ghin": self.engine.projected_ghin(player.simcore_index),
            "outdoor_handicap": player.outdoor_handicap,
        }

    def override_handicap(self, player, simcore_value=None, outdoor_value=None):
        result = self.engine.apply_override(
            current_simcore=player.simcore_index,
            current_outdoor=player.outdoor_index,
            simcore_override=simcore_value,
            outdoor_override=outdoor_value,
        )

        player.simcore_index = result["simcore_index"]
        player.outdoor_index = result["outdoor_index"]

        return result