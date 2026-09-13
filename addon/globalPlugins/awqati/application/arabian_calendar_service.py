"""Application use case for the Arabian calendar, independent of astronomy."""

from __future__ import annotations

from datetime import date

from ..domain import ArabianCalendarReading, Location
from .ports import ArabianCalendarRepository, NowProvider, TimezoneProvider


class ArabianCalendarService:
	def __init__(
		self,
		repository: ArabianCalendarRepository,
		clock: NowProvider | None = None,
		timezones: TimezoneProvider | None = None,
	) -> None:
		self._repository = repository
		self._clock = clock
		self._timezones = timezones

	@property
	def data_version(self) -> str:
		return self._repository.arabian_calendar_data_version

	def read_date(self, local_date: date) -> ArabianCalendarReading:
		return self._repository.read(local_date)

	def read(self, location: Location) -> ArabianCalendarReading:
		if self._clock is None or self._timezones is None:
			raise RuntimeError("clock and timezone provider are required for location-based reads")
		zone = self._timezones.get_timezone(location.timezone_id)
		return self.read_date(self._clock.now().value.astimezone(zone).date())
