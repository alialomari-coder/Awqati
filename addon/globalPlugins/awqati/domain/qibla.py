"""Pure true-north Qibla bearing and language-neutral direction description."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .models import Coordinates


KAABA_COORDINATES = Coordinates(latitude=21.422487, longitude=39.826206)


class QiblaDirection(Enum):
	NORTH = "north"
	EAST = "east"
	SOUTH = "south"
	WEST = "west"


class QiblaUndefinedError(ValueError):
	"""The initial bearing is undefined for coincident or antipodal points."""


@dataclass(frozen=True, slots=True)
class QiblaResult:
	bearing_degrees: float
	direction: QiblaDirection
	lean_direction: QiblaDirection | None
	lean_degrees: float


_BASE_DIRECTIONS = (
	(QiblaDirection.NORTH, 0.0),
	(QiblaDirection.EAST, 90.0),
	(QiblaDirection.SOUTH, 180.0),
	(QiblaDirection.WEST, 270.0),
)
_CLOCKWISE_LEAN = {
	QiblaDirection.NORTH: QiblaDirection.EAST,
	QiblaDirection.EAST: QiblaDirection.SOUTH,
	QiblaDirection.SOUTH: QiblaDirection.WEST,
	QiblaDirection.WEST: QiblaDirection.NORTH,
}
_COUNTERCLOCKWISE_LEAN = {
	QiblaDirection.NORTH: QiblaDirection.WEST,
	QiblaDirection.EAST: QiblaDirection.NORTH,
	QiblaDirection.SOUTH: QiblaDirection.EAST,
	QiblaDirection.WEST: QiblaDirection.SOUTH,
}


def initial_qibla_bearing(origin: Coordinates) -> float:
	"""Return the spherical initial bearing clockwise from true north."""
	phi1 = math.radians(origin.latitude)
	phi2 = math.radians(KAABA_COORDINATES.latitude)
	delta = math.radians(KAABA_COORDINATES.longitude - origin.longitude)
	y = math.sin(delta) * math.cos(phi2)
	x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta)
	if math.hypot(x, y) <= 1e-14:
		raise QiblaUndefinedError("Qibla bearing is undefined at the Kaaba or its spherical antipode")
	bearing = math.degrees(math.atan2(y, x)) % 360.0
	if not math.isfinite(bearing):
		raise QiblaUndefinedError("Qibla bearing is not finite")
	return bearing


def describe_qibla_bearing(bearing_degrees: float) -> QiblaResult:
	"""Classify a normalized bearing by its nearest cardinal direction."""
	if not math.isfinite(bearing_degrees):
		raise ValueError("bearing_degrees must be finite")
	bearing = bearing_degrees % 360.0
	index = int(math.floor((bearing + 45.0) / 90.0)) % 4
	direction, base = _BASE_DIRECTIONS[index]
	delta = (bearing - base + 180.0) % 360.0 - 180.0
	amount = abs(delta)
	if amount <= 1e-12:
		lean = None
		amount = 0.0
	elif delta > 0:
		lean = _CLOCKWISE_LEAN[direction]
	else:
		lean = _COUNTERCLOCKWISE_LEAN[direction]
	return QiblaResult(bearing, direction, lean, amount)
