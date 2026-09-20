from mvp.engine.models.shot import SimCore22Shot

def parse_trackman_shot(payload: dict) -> SimCore22Shot:
    """
    Converts a TrackMan live payload into a normalized SimCore22Shot.
    """

    return SimCore22Shot(
        ball_speed=payload.get("BallSpeed"),
        launch_angle=payload.get("LaunchAngle"),
        azimuth=payload.get("LaunchDirection"),
        spin=payload.get("SpinRate"),
        spin_axis=payload.get("SpinAxis"),
        club_speed=payload.get("ClubSpeed"),
        face_to_target=payload.get("FaceToPath"),
        club_path=payload.get("ClubPath"),
        raw_payload=payload,
        source="trackman",
    )