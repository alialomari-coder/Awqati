"""Application orchestration for civil and Maghrib-based clock readings."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable

from ..domain import ClockReading, Instant, Location, PrayerCalculationRequest
from .ports import NowProvider, TimezoneProvider
from .prayer_service import PrayerService


PrayerRequestFactory = Callable[[date, Location], PrayerCalculationRequest]


class ClockService:
	"""Read Zawali time and real elapsed time since the applicable local Maghrib."""

	def __init__(self, clock: NowProvider, timezones: TimezoneProvider,
			prayers: PrayerService, request_factory: PrayerRequestFactory) -> None:
		self._clock = clock
		self._timezones = timezones
		self._prayers = prayers
		self._request_factory = request_factory

	def read_civil(self, location: Location | None = None) -> datetime:
		"""Civil time remains available before a location has been assigned."""
		zone = self._timezones.get_timezone(location.timezone_id) if location else None
		return self._clock.now().value.astimezone(zone)

	def read(self, location: Location) -> ClockReading:
		return self.read_at(location, self._clock.now())

	def read_at(self, location: Location, instant: Instant) -> ClockReading:
		"""Read an explicit occurrence without changing the current clock."""
		now = instant.value
		zone = self._timezones.get_timezone(location.timezone_id)
		local_now = now.astimezone(zone)
		today = local_now.date()
		today_maghrib = self._maghrib(today, location)
		if _utc(local_now) < _utc(today_maghrib):
			reference = self._maghrib(today - timedelta(days=1), location)
		else:
			reference = today_maghrib
		elapsed = _utc(local_now) - _utc(reference)
		return ClockReading(local_now, elapsed, reference)

	def _maghrib(self, local_date: date, location: Location) -> datetime:
		request = self._request_factory(local_date, location)
		if request.local_date != local_date:
			raise ValueError("prayer request date does not match the requested local date")
		if (request.latitude, request.longitude, request.timezone_id) != (
				location.latitude, location.longitude, location.timezone_id):
			raise ValueError("prayer request does not match the effective location")
		maghrib = self._prayers.calculate(request).maghrib
		if maghrib.tzinfo is None or maghrib.utcoffset() is None:
			raise ValueError("PrayerService returned a naive Maghrib")
		return maghrib


def _utc(value: datetime) -> datetime:
	if value.tzinfo is None or value.utcoffset() is None:
		raise ValueError("clock instants must be timezone-aware")
	return value.astimezone(timezone.utc)
