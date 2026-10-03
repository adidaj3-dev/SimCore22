# mvp/engine/ingestion/trackman/parser.py
"""
UNVERIFIED: no TrackMan unit has been captured against this yet.

Builds a normalized ShotEvent from what TrackMan's live JSON output is
documented to look like. Field names and payload shape need confirming
against a real capture (see mvp/tools/falcon_packet_decoder.py for the
pattern - point the same approach at a TrackMan unit) before this is trusted
for scoring.
"""
from datetime import datetime

from mvp.engine.models.events import ShotEvent


def parse_trackman_shot(payload: dict) -> ShotEvent:
    """Converts a TrackMan live payload into SimCore22's normalized ShotEvent."""
    return ShotEvent(
        source_device="TrackMan",
        timestamp=datetime.now(),
        ball_speed=payload.get("BallSpeed"),
        launch_angle=payload.get("LaunchAngle"),
        azimuth=payload.get("LaunchDirection"),
        spin_rate=payload.get("SpinRate"),
        spin_axis=payload.get("SpinAxis"),
        club_speed=payload.get("ClubSpeed"),
        carry_distance=payload.get("Carry"),
        total_distance=payload.get("Total"),
        metadata={
            "face_to_target": payload.get("FaceToPath"),
            "club_path": payload.get("ClubPath"),
            "raw": payload,
        },
    )
