"""Application orchestration for offline daily astronomical facts."""

from __future__ import annotations

from datetime import datetime, time, timezone

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
		# The supported civil-year contract follows the location's local date.
		# Passing local_now keeps UTC instants just outside an endpoint available
		# solely as internal auxiliary calculations.
		season, started = season_at(local_now, location.latitude)
		next_event = next_seasonal_event(local_now)
		local_date = local_now.date()
		local_noon = datetime.combine(local_date, time(12), tzinfo=zone)
		utc_anchor_day = local_noon.astimezone(timezone.utc).date()
		solar = solar_day(
			local_date,
			location.latitude,
			location.longitude,
			utc_anchor_day=utc_anchor_day,
		)
		lunar = lunar_facts(local_now)
		return AstronomyReading(
			local_date=local_date,
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
