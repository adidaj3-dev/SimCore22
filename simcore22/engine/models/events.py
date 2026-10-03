# simcore22/engine/models/events.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


# ---------------------------------------------------------
# CORE SHOT / PLAYER / HOLE / SCORE EVENTS
# ---------------------------------------------------------

@dataclass
class ShotEvent:
    source_device: str
    timestamp: datetime

    ball_speed: Optional[float] = None
    launch_angle: Optional[float] = None
    azimuth: Optional[float] = None

    spin_rate: Optional[float] = None
    spin_axis: Optional[float] = None
    total_spin: Optional[float] = None

    club_speed: Optional[float] = None
    carry_distance: Optional[float] = None
    total_distance: Optional[float] = None

    curve: Optional[float] = None
    direction: Optional[float] = None
    apex: Optional[float] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerEvent:
    timestamp: datetime
    player_name: str


@dataclass
class HoleEvent:
    timestamp: datetime
    hole_number: int


@dataclass
class ScoreEvent:
    timestamp: datetime
    player_name: str
    hole_number: int
    gross_score: int
    par: Optional[int] = None
    handicap_stroke_index: Optional[int] = None
    tee_yardage: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------
# ROUND LIFECYCLE EVENTS
# ---------------------------------------------------------

@dataclass
class RoundStartEvent:
    timestamp: datetime
    course_name: str


@dataclass
class RoundEndEvent:
    timestamp: datetime
    reason: str = "completed"
