"""Instantaneous geometric Earth-center/Moon-center range, without light time."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math

from .astronomy import _require_aware, validate_astronomy_year
from .lunar_horizon import _position

LUNAR_DISTANCE_ALGORITHM_VERSION = "awqati-lunar-distance-meeus47-v1"


@dataclass(frozen=True, slots=True)
class LunarDistance:
    observed_at_utc: datetime
    distance_km: float
    algorithm_version: str = LUNAR_DISTANCE_ALGORITHM_VERSION


def lunar_distance(moment: datetime) -> LunarDistance:
    """Unrounded km, UTC years 1901–2099; no observer or daily cache.

    Reuse the radial series from the existing chapter-47 position calculation.
    Its directional nutation correction does not alter the returned radius.
    """
    _require_aware(moment)
    utc = moment.astimezone(timezone.utc)
    validate_astronomy_year(utc.year)
    radius = _position(utc)[2]
    if not math.isfinite(radius) or radius <= 0:
        raise ArithmeticError("non-finite or non-positive geocentric lunar range")
    return LunarDistance(utc, radius)
