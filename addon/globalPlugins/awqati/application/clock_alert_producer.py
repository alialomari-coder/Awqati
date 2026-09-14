"""Civil clock occurrences using the scheduler's existing DST resolver."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timedelta, tzinfo
from typing import Callable

from ..domain import AlertEvent, AlertEventType, AwqatiSettings, ClockReading, Instant
from ..domain.alerts import utc
from .alert_scheduler import resolve_civil_time


class ClockAlertProducer:
	"""Consume prepared clock readings without output or I/O.

	reading_at supplies ClockService readings for the occurrence, not rebuild
	time. The owner must prepare backing data and supply an explicit end.
	"""

	def __init__(self, settings: Callable[[], AwqatiSettings],
			zone: Callable[[str], tzinfo], reading_at: Callable[[Instant], ClockReading]) -> None:
		self._settings = settings
		self._zone = zone
		self._reading_at = reading_at

	def produce(self, from_now: Instant, until: Instant) -> tuple[AlertEvent, ...]:
		if utc(until) <= utc(from_now):
			raise ValueError("alert window end must follow from_now")
		settings = self._settings()
		config = settings.clock
		intervals = config.intervals
		minutes = [minute for minute, enabled in ((0, intervals.on_hour),
			(15, intervals.on_quarter), (30, intervals.on_half), (45, intervals.on_three_quarters)) if enabled]
		if not config.automatic_alert_enabled or not minutes or settings.location is None:
			return ()
		zone_id = settings.location.location.timezone_id
		zone = self._zone(zone_id)
		day = from_now.value.astimezone(zone).date()
		last_day = until.value.astimezone(zone).date()
		result = []
		seen = set()
		while day <= last_day:
			for hour in range(24):
				for minute in minutes:
					civil = datetime.combine(day, time(hour, minute))
					instant = Instant(resolve_civil_time(civil, zone))
					when = utc(instant)
					if not utc(from_now) <= when < utc(until) or when in seen:
						continue
					# Missing slots resolving to one instant produce a single chime.
					seen.add(when)
					key = f"clock:{zone_id}:{when.isoformat()}"
					result.append(AlertEvent(key, AlertEventType.CLOCK, instant,
						action=config.alert.action, message_id="alert.clock.time",
						sound_ref=config.alert.sound.value if config.alert.sound else None,
						source="ClockAlertProducer", scope="clock", metadata={
							"timezone_id": zone_id, "civil_time": civil.isoformat(),
							"interval_minute": minute, "reading": self._reading_at(instant),
							"presentations": deepcopy(config.presentations),
						}))
			day += timedelta(days=1)
		return tuple(sorted(result, key=lambda event: utc(event.scheduled_at)))
