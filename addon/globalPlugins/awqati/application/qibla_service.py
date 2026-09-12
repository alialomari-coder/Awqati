"""Application service for the effective location's Qibla bearing."""

from __future__ import annotations

from ..domain.models import Coordinates, Location
from ..domain.qibla import QiblaResult, describe_qibla_bearing, initial_qibla_bearing


class QiblaService:
	def calculate(self, location: Location) -> QiblaResult:
		coordinates = Coordinates(location.latitude, location.longitude)
		return describe_qibla_bearing(initial_qibla_bearing(coordinates))
