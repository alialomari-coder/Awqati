"""Application orchestration for offline daily astronomical facts."""

from __future__ import annotations

from datetime import timezone

from ..domain.astronomy import (
	AstronomyReading,
	lunar_facts,
	next_seasonal_event,
	season_at,
	solar_day,
)
from ..domain.models import Location
from .ports import NowProvider, TimezoneProvider


class AstronomyService:
	def __init__(self, clock: NowProvider, timezones: TimezoneProvider) -> None:
		self._clock = clock
		self._timezones = timezones

	def read(self, location: Location) -> AstronomyReading:
		now = self._clock.now().value
		zone = self._timezones.get_timezone(location.timezone_id)
		local_now = now.astimezone(zone)
		season, started = season_at(now, location.latitude)
		next_event = next_seasonal_event(now)
		solar = solar_day(local_now.date(), location.latitude, location.longitude)
		lunar = lunar_facts(now.astimezone(timezone.utc))
		return AstronomyReading(
			local_date=local_now.date(),
			current_season=season,
			current_season_started=started,
			next_seasonal_event=next_event,
			next_seasonal_event_local=next_event.at_utc.astimezone(zone),
			solar_day=solar,
			sunrise_local=solar.sunrise_utc.astimezone(zone) if solar.sunrise_utc else None,
			sunset_local=solar.sunset_utc.astimezone(zone) if solar.sunset_utc else None,
			lunar=lunar,
			next_new_moon_local=lunar.next_new_moon_utc.astimezone(zone),
			next_full_moon_local=lunar.next_full_moon_utc.astimezone(zone),
		)
