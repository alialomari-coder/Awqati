"""Application orchestration for offline daily astronomical facts."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo

from ..domain.astronomy import (
	ASTRONOMY_MIN_YEAR,
	AstronomyReading,
	SolarDay,
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
		solar = _solar_day_for_local_date(local_date, location, zone)
		previous_date = local_date - timedelta(days=1)
		daylight_change = None
		if previous_date.year >= ASTRONOMY_MIN_YEAR:
			previous_solar = _solar_day_for_local_date(previous_date, location, zone)
			daylight_change = solar.daylight - previous_solar.daylight
		lunar = lunar_facts(local_now)
		return AstronomyReading(
			local_date=local_date,
			observed_at_local=local_now,
			current_season=season,
			current_season_started=started,
			next_seasonal_event=next_event,
			next_seasonal_event_local=next_event.at_utc.astimezone(zone),
			solar_day=solar,
			daylight_change_from_previous_day=daylight_change,
			sunrise_local=solar.sunrise_utc.astimezone(zone) if solar.sunrise_utc else None,
			sunset_local=solar.sunset_utc.astimezone(zone) if solar.sunset_utc else None,
			lunar=lunar,
			next_new_moon_local=lunar.next_new_moon_utc.astimezone(zone),
			next_full_moon_local=lunar.next_full_moon_utc.astimezone(zone),
		)


def _solar_day_for_local_date(day: date, location: Location, zone: tzinfo) -> SolarDay:
	"""Use the established local-date anchoring policy for any compared day."""
	local_noon = datetime.combine(day, time(12), tzinfo=zone)
	utc_anchor_day = local_noon.astimezone(timezone.utc).date()
	return solar_day(
		day,
		location.latitude,
		location.longitude,
		utc_anchor_day=utc_anchor_day,
	)
