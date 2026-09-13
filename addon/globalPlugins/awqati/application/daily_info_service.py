"""Application orchestration that keeps astronomy and heritage independent."""

from __future__ import annotations

from ..domain import DailyInfoReading, Location
from .arabian_calendar_service import ArabianCalendarService
from .astronomy_service import AstronomyService


class DailyInfoService:
	def __init__(
		self,
		astronomy: AstronomyService,
		arabian_calendar: ArabianCalendarService | None = None,
	) -> None:
		self._astronomy = astronomy
		self._arabian_calendar = arabian_calendar

	def read(self, location: Location, *, include_arabian_calendar: bool = False) -> DailyInfoReading:
		scientific = self._astronomy.read(location)
		heritage = None
		if include_arabian_calendar:
			if self._arabian_calendar is None:
				raise RuntimeError("Arabian calendar service is required when heritage is requested")
			heritage = self._arabian_calendar.read(location)
		return DailyInfoReading(scientific=scientific, heritage=heritage)
