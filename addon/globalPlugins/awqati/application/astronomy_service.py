"""Application orchestration for offline daily astronomical facts."""

from __future__ import annotations

from datetime import date, timedelta, tzinfo
from functools import lru_cache
from ..domain.daily_astronomy import DailyAstronomyDetails

from ..domain.astronomy import (
	ASTRONOMY_MIN_YEAR,
	AstronomyReading,
	Season,
	SeasonEvent,
	SolarDay,
	SunDistance,
	sun_distance,
	lunar_facts,
	next_seasonal_event,
	season_at,
	annual_daylight,
	seasonal_daylight,
	SeasonalDaylight,
	solar_day_for_local_date,
)
from ..domain.lunar_phases import UpcomingLunarPhases, upcoming_lunar_phases
from ..domain.models import Location
from ..domain.lunar_horizon import LunarHorizonEvents, lunar_horizon_events
from ..domain.lunar_distance import LunarDistance, lunar_distance
from ..domain.lunar_transit import LunarTransitDay, lunar_transit_day
from .ports import NowProvider, TimezoneProvider


class AstronomyService:
	def __init__(self, clock: NowProvider, timezones: TimezoneProvider) -> None:
		self._clock = clock
		self._timezones = timezones
		self._annual_daylight = lru_cache(maxsize=4)(annual_daylight)
		self._daily_horizon = lru_cache(maxsize=8)(lunar_horizon_events)
		self._daily_transit = lru_cache(maxsize=8)(lunar_transit_day)

	def read_lunar_phases(self, location: Location | None = None) -> UpcomingLunarPhases:
		"""Opt-in task 2.4; a single clock read, UTC events, no synopsis change."""
		now = self._clock.now().value
		if location is None:
			return upcoming_lunar_phases(now)
		zone = self._timezones.get_timezone(location.timezone_id)
		return upcoming_lunar_phases(now, zone)

	def read_sun_distance(self) -> SunDistance:
		"""Opt-in instant range; one clock read, no daily cache or location."""
		return sun_distance(self._clock.now().value)

	def read_lunar_distance(self) -> LunarDistance:
		"""Instant center-to-center range, one clock read and no location/cache."""
		return lunar_distance(self._clock.now().value)

	def read_lunar_horizon(self, location: Location) -> LunarHorizonEvents:
		"""Opt-in task 2.1 data; call on the astronomy worker, no synopsis change."""
		now = self._clock.now().value
		zone = self._timezones.get_timezone(location.timezone_id)
		return lunar_horizon_events(now.astimezone(zone).date(), location.latitude, location.longitude, zone)

	def read_lunar_transit(self, location: Location) -> LunarTransitDay:
		"""Opt-in task 2.2; run on astronomy worker, existing synopsis unchanged."""
		now = self._clock.now().value
		zone = self._timezones.get_timezone(location.timezone_id)
		return lunar_transit_day(now.astimezone(zone).date(), location.latitude, location.longitude, zone)

	def read_daylight(self, location: Location) -> SeasonalDaylight:
		"""Opt-in task 1.2 facts; existing synopsis read/output remains unchanged.

		Call on the application's astronomy worker, like other astronomy reads.
		The bounded per-service cache includes year, coordinates and actual zone.
		"""
		now = self._clock.now().value
		zone = self._timezones.get_timezone(location.timezone_id)
		year = now.astimezone(zone).year
		annual = self._annual_daylight(year, location.latitude, location.longitude, zone)
		return seasonal_daylight(now, location.latitude, location.longitude, zone, annual=annual)

	def read(self, location: Location, *, include_daily_details: bool = False) -> AstronomyReading:
		now = self._clock.now().value
		zone = self._timezones.get_timezone(location.timezone_id)
		local_now = now.astimezone(zone)
		# The supported civil-year contract follows the location's local date.
		# Passing local_now keeps UTC instants just outside an endpoint available
		# solely as internal auxiliary calculations.
		season, started = season_at(local_now, location.latitude)
		next_event = next_seasonal_event(local_now)
		local_date = local_now.date()
		# A season's local civil date is day one even when the event instant is
		# later on that date.  Advance the classification without waiting for 24
		# elapsed hours or asking a formatter to infer it from prose.
		if next_event.at_utc.astimezone(zone).date() == local_date:
			started = next_event
			season = _season_started_by(next_event.event, location.latitude)
			next_event = next_seasonal_event(next_event.at_utc + timedelta(microseconds=1))
		solar = _solar_day_for_local_date(local_date, location, zone)
		previous_date = local_date - timedelta(days=1)
		daylight_change = None
		if previous_date.year >= ASTRONOMY_MIN_YEAR:
			previous_solar = _solar_day_for_local_date(previous_date, location, zone)
			daylight_change = solar.daylight - previous_solar.daylight
		lunar = lunar_facts(local_now)
		details = None
		if include_daily_details:
			# Reuse this request's instant and zone, never call the clock again.
			# Each optional failure remains absent; never invent an event or zero.
			def optional(calculate, *args, **kwargs):
				try:
					return calculate(*args, **kwargs)
				except (ArithmeticError, ValueError):
					return None
			annual = optional(self._annual_daylight, local_date.year, location.latitude, location.longitude, zone)
			daylight = (optional(seasonal_daylight, now, location.latitude, location.longitude, zone, annual=annual)
				if annual is not None else None)
			args = (local_date, location.latitude, location.longitude, zone)
			details = DailyAstronomyDetails(daylight, optional(sun_distance, now),
				optional(self._daily_horizon, *args), optional(self._daily_transit, *args),
				optional(lunar_distance, now), optional(upcoming_lunar_phases, now, zone))
		return AstronomyReading(
			local_date=local_date,
			observed_at_local=local_now,
			current_season=season,
			current_season_started=started,
			season_day=(local_date - started.at_utc.astimezone(zone).date()).days + 1,
			next_seasonal_event=next_event,
			next_seasonal_event_local=next_event.at_utc.astimezone(zone),
			solar_day=solar,
			daylight_change_from_previous_day=daylight_change,
			sunrise_local=solar.sunrise_utc.astimezone(zone) if solar.sunrise_utc else None,
			sunset_local=solar.sunset_utc.astimezone(zone) if solar.sunset_utc else None,
			lunar=lunar,
			daily_details=details,
			next_new_moon_local=lunar.next_new_moon_utc.astimezone(zone),
			next_full_moon_local=lunar.next_full_moon_utc.astimezone(zone),
		)


def _solar_day_for_local_date(day: date, location: Location, zone: tzinfo) -> SolarDay:
	"""Use the established local-date anchoring policy for any compared day."""
	return solar_day_for_local_date(day, location.latitude, location.longitude, zone)


def _season_started_by(event: SeasonEvent, latitude: float) -> Season:
	north = {
		SeasonEvent.MARCH_EQUINOX: Season.SPRING,
		SeasonEvent.JUNE_SOLSTICE: Season.SUMMER,
		SeasonEvent.SEPTEMBER_EQUINOX: Season.AUTUMN,
		SeasonEvent.DECEMBER_SOLSTICE: Season.WINTER,
	}
	south = {
		SeasonEvent.MARCH_EQUINOX: Season.AUTUMN,
		SeasonEvent.JUNE_SOLSTICE: Season.WINTER,
		SeasonEvent.SEPTEMBER_EQUINOX: Season.SPRING,
		SeasonEvent.DECEMBER_SOLSTICE: Season.SUMMER,
	}
	return (north if latitude >= 0 else south)[event]
