"""Task 4.2 composition with one civil-day horizon and prepared service data."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Callable

from ..domain import AlertEvent, AwqatiSettings, Instant, PrayerCalculationRequest, complete_prayer_times
from ..domain.alerts import utc
from ..domain.prayer import PrayerCorrections, PrayerName
from ..domain.prayer_timeline import PrayerEvent, PrayerEventName
from .alert_scheduler import in_scope, resolve_civil_time
from .clock_alert_producer import ClockAlertProducer
from .clock_service import ClockService
from .prayer_alert_producer import PrayerAlertProducer


def next_local_midnight(from_now: Instant, zone) -> Instant:
	"""Exclusive civil boundary, including 23/25-hour days and midnight gaps."""
	day = from_now.value.astimezone(zone).date() + timedelta(days=1)
	return Instant(resolve_civil_time(datetime.combine(day, time()), zone))


class PrayerClockRebuildSource:
	"""Use the published location for the common prayer/clock horizon.

	The 5.1 owner wakes at min(scheduler.wakeup_at, next_rebuild_at(now)) and
	calls coordinator.renew_day at the day boundary. No fake alert or timer.
	"""

	def __init__(self, prayer: PrayerAlertProducer, clock: ClockAlertProducer,
			settings: Callable[[], AwqatiSettings], zone: Callable, *, prepare: Callable | None = None) -> None:
		self._prayer, self._clock = prayer, clock
		self._settings, self._zone = settings, zone
		self._prepare = prepare

	@classmethod
	def from_services(cls, settings, prayers, timezones):
		"""Prepare calculator/I/O results before invoking either pure producer.

	The adapter must run potentially cold service preparation off its UI thread.
	Cache lifetime is one rebuild, so Apply/location changes cannot use stale data.
	"""
		data = _PreparedAlertData(settings, prayers, timezones)
		return cls(PrayerAlertProducer(settings, data.timeline),
			ClockAlertProducer(settings, data.get_timezone, data.reading_at),
			settings, timezones.get_timezone, prepare=data.prepare)

	def next_rebuild_at(self, from_now: Instant) -> Instant | None:
		stored = self._settings().location
		if stored is None:
			return None
		return next_local_midnight(from_now, self._zone(stored.location.timezone_id))

	def __call__(self, from_now: Instant, reason: str, scope: str | None) -> tuple[AlertEvent, ...]:
		producers = [producer for name, producer in
			(("prayer", self._prayer), ("clock", self._clock)) if in_scope(name, scope)]
		if not producers:
			return ()
		until = self.next_rebuild_at(from_now)
		if until is None:
			return ()
		if self._prepare:
			self._prepare(from_now, until, scope)
		# All computation succeeds before the scheduler replaces its old queue.
		return tuple(event for producer in producers for event in producer.produce(from_now, until))


class _PreparedAlertData:
	"""One rebuild's in-memory bridge between existing services and producers."""

	def __init__(self, settings, prayers, timezones):
		self._settings, self._prayers, self._timezones = settings, prayers, timezones

	def prepare(self, start, end, scope):
		settings = self._settings()
		self._stored = settings.location
		self._config = settings.prayer
		self._start = start
		self._zone = self._timezones.get_timezone(self._stored.location.timezone_id)
		self._days = {}
		self._events = ()
		prayer_enabled = in_scope("prayer", scope) and settings.prayer.alerts_enabled
		intervals = settings.clock.intervals
		clock_enabled = in_scope("clock", scope) and settings.clock.automatic_alert_enabled and any((
			intervals.on_hour, intervals.on_quarter, intervals.on_half, intervals.on_three_quarters))
		if not prayer_enabled and not clock_enabled:
			return
		# Offset look-around derives from saved settings, not an arbitrary horizon.
		configs = tuple(self._config.events.values())
		before = max(config.pre_alert_minutes for config in configs) if prayer_enabled else 0
		after = max(max(config.post_alert_minutes or 0,
			config.iqama.delay_minutes if config.iqama else 0) for config in configs) if prayer_enabled else 0
		correction = max(abs(value) for value in self._config.corrections_minutes.values())
		first = (utc(start) - timedelta(minutes=after + correction)).astimezone(self._zone).date()
		last = (utc(end) + timedelta(minutes=before + correction)).astimezone(self._zone).date()
		# Previous Maghrib is needed for the current day's night and clock.
		first -= timedelta(days=1)
		day = first
		while day <= last + timedelta(days=1):
			request = self._request(day, self._stored.location)
			self._days[day] = self._prayers.calculate(request)
			day += timedelta(days=1)
		if prayer_enabled:
			events = []
			day = first
			while day <= last:
				completed = complete_prayer_times(self._days[day], self._days[day + timedelta(days=1)].fajr)
				for event in completed.events:
					# Six prayer corrections were already applied by PrayerCalculator.
					if event.name in (PrayerEventName.MIDNIGHT, PrayerEventName.LAST_THIRD):
						at = utc(Instant(event.occurs_at)) + timedelta(minutes=self._config.corrections_minutes[event.name])
						event = PrayerEvent(event.name, at.astimezone(self._zone))
					events.append(event)
				day += timedelta(days=1)
			self._events = tuple(events)
		self._clock = ClockService(self, self, self, self._request)

	def _request(self, day, location):
		return PrayerCalculationRequest(day, location.latitude, location.longitude, location.timezone_id,
			self._config.calculation_method, self._config.asr_method, self._config.high_latitude_rule,
			country_code=self._stored.country_code, corrections=PrayerCorrections(**{
				name.value: self._config.corrections_minutes[PrayerEventName(name.value)] for name in PrayerName}))

	def now(self):
		return self._start

	def calculate(self, request):
		return self._days[request.local_date]

	def get_timezone(self, zone_id):
		if zone_id != self._stored.location.timezone_id:
			raise ValueError("prepared timezone does not match runtime location")
		return self._zone

	def timeline(self, start, end):
		return self._events

	def reading_at(self, instant):
		return self._clock.read_at(self._stored.location, instant)
