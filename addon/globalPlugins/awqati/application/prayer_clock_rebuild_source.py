"""Tasks 4.2 and 4.3 share one civil-day horizon and prepared service data."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Callable

from ..domain import AlertEvent, AwqatiSettings, Instant, PrayerCalculationRequest, complete_prayer_times
from ..domain.alerts import utc
from ..domain.prayer import PrayerCorrections, PrayerName
from ..domain.prayer_timeline import PrayerEvent, PrayerEventName
from .alert_scheduler import in_scope, resolve_civil_time
from .general_policy import alert_scope_enabled
from .clock_alert_producer import ClockAlertProducer
from .clock_service import ClockService
from .prayer_alert_producer import PrayerAlertProducer
from .adhkar_alert_producer import AdhkarAlertProducer
from .daily_wird_producer import DailyWirdProducer
from .recurring_dhikr_producer import RecurringDhikrProducer


def next_local_midnight(from_now: Instant, zone) -> Instant:
	"""Exclusive civil boundary, including 23/25-hour days and midnight gaps."""
	day = from_now.value.astimezone(zone).date() + timedelta(days=1)
	return Instant(resolve_civil_time(datetime.combine(day, time()), zone))


class PrayerClockRebuildSource:
	"""Use the published location for the common horizon of all five producers.

	The 5.1 owner wakes at min(scheduler.wakeup_at, next_rebuild_at(now)) and
	calls coordinator.renew_day at the day boundary. No fake alert or timer.
	"""

	def __init__(self, prayer: PrayerAlertProducer, clock: ClockAlertProducer,
			settings: Callable[[], AwqatiSettings], zone: Callable, *, prepare: Callable | None = None,
			adhkar=None, wird=None, recurring=None) -> None:
		self._prayer, self._clock = prayer, clock
		self._settings, self._zone = settings, zone
		self._prepare = prepare
		self._adhkar, self._wird, self._recurring = adhkar, wird, recurring

	@classmethod
	def from_services(cls, settings, prayers, timezones):
		"""Prepare calculator/I/O results before invoking the pure event producers.

	The adapter must run potentially cold service preparation off its UI thread.
	Cache lifetime is one rebuild, so Apply/location changes cannot use stale data.
	"""
		data = _PreparedAlertData(settings, prayers, timezones)
		return cls(PrayerAlertProducer(settings, data.timeline),
			ClockAlertProducer(settings, data.get_timezone, data.reading_at),
			settings, timezones.get_timezone, prepare=data.prepare,
			adhkar=AdhkarAlertProducer(settings, data.timeline, data.get_timezone),
			wird=DailyWirdProducer(settings, data.get_timezone), recurring=RecurringDhikrProducer(settings))

	def settings_changed(self, previous, current, now):
		if self._recurring is not None:
			self._recurring.settings_changed(previous, current, now)

	def next_rebuild_at(self, from_now: Instant) -> Instant | None:
		stored = self._settings().location
		if stored is None:
			return None
		return next_local_midnight(from_now, self._zone(stored.location.timezone_id))

	def __call__(self, from_now: Instant, reason: str, scope: str | None) -> tuple[AlertEvent, ...]:
		settings = self._settings()
		producers = [producer for name, producer in
			(("prayer", self._prayer), ("clock", self._clock)) if in_scope(name, scope) and alert_scope_enabled(settings, name)]
		adhkar = self._adhkar is not None and any(in_scope("adhkar." + name, scope)
			for name in ("morning", "evening", "friday"))
		wird = self._wird is not None and in_scope("adhkar.dailyWird", scope)
		recurring = self._recurring is not None and (in_scope("adhkar.recurring", scope)
			or (scope is not None and in_scope(scope, "adhkar.recurring")))
		if not producers and not (adhkar or wird or recurring):
			return ()
		until = self.next_rebuild_at(from_now)
		if until is None:
			return ()
		if self._prepare:
			self._prepare(from_now, until, scope)
		# All computation succeeds before the scheduler replaces its old queue.
		result = [event for producer in producers for event in producer.produce(from_now, until)]
		if adhkar:
			result.extend(self._adhkar.produce(from_now, until, scope))
		if wird:
			result.extend(self._wird.produce(from_now, until))
		# Commit recurrence only after all service-backed work has succeeded.
		if recurring:
			result.extend(self._recurring.produce(from_now, until, reason=reason, scope=scope))
		return tuple(result)


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
		prayer_enabled = in_scope("prayer", scope) and alert_scope_enabled(settings, "prayer")
		timed = tuple(config for name, config in (("morning", settings.adhkar.morning),
			("evening", settings.adhkar.evening), ("friday", settings.adhkar.friday_hour))
			if alert_scope_enabled(settings, "adhkar." + name) and in_scope("adhkar." + name, scope))
		intervals = settings.clock.intervals
		clock_enabled = in_scope("clock", scope) and alert_scope_enabled(settings, "clock") and any((
			intervals.on_hour, intervals.on_quarter, intervals.on_half, intervals.on_three_quarters))
		if not prayer_enabled and not clock_enabled and not timed:
			return
		# Offset look-around derives from saved settings, not an arbitrary horizon.
		configs = tuple(self._config.events.values())
		before = max(config.pre_alert_minutes for config in configs) if prayer_enabled else 0
		after = max(max(config.post_alert_minutes or 0,
			config.iqama.delay_minutes if config.iqama else 0) for config in configs) if prayer_enabled else 0
		before = max([before] + [config.minutes for config in timed if config.reference.value.startswith("before")])
		after = max([after] + [config.minutes for config in timed if config.reference.value.startswith("after")])
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
		if prayer_enabled or timed:
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
