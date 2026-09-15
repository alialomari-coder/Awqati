"""Civil-time daily wird descriptions without catch-up or presentation."""

from datetime import datetime, time, timedelta

from ..domain import AlertEvent, AlertEventType, Instant
from ..domain.alerts import utc
from ..domain.settings import DayPeriod
from .alert_scheduler import resolve_civil_time
from .general_policy import alert_scope_enabled


class DailyWirdProducer:
	def __init__(self, settings, zone):
		self._settings, self._zone = settings, zone

	def produce(self, from_now, until):
		if utc(until) <= utc(from_now):
			raise ValueError("alert window end must follow from_now")
		settings = self._settings()
		config = settings.adhkar.daily_wird
		if not alert_scope_enabled(settings, "adhkar.dailyWird") or settings.location is None:
			return ()
		zone_id = settings.location.location.timezone_id
		zone = self._zone(zone_id)
		hour = config.hour % 12 + (12 if config.period is DayPeriod.PM else 0)
		day = from_now.value.astimezone(zone).date()
		last = until.value.astimezone(zone).date()
		result = []
		while day <= last:
			civil = datetime.combine(day, time(hour, config.minute))
			when = Instant(resolve_civil_time(civil, zone))
			if utc(from_now) <= utc(when) < utc(until):
				key = f"adhkar:dailyWird:{zone_id}:{utc(when).isoformat()}"
				result.append(AlertEvent(key, AlertEventType.DAILY_WIRD, when,
					action=config.alert.action, message_id="alert.adhkar.dailyWird",
					sound_ref=config.alert.sound.value if config.alert.sound else None,
					source="DailyWirdProducer", scope="adhkar.dailyWird",
					metadata={"text": config.text, "timezone_id": zone_id, "civil_time": civil.isoformat()}))
			day += timedelta(days=1)
		return tuple(result)
