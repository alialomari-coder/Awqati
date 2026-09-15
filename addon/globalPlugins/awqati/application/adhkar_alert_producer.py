"""Timed adhkar over the existing prepared prayer timeline."""

from datetime import timedelta

from ..domain import AlertEvent, AlertEventType, AlertTiming, Instant
from ..domain.alerts import utc
from ..domain.settings import MorningReference, EveningReference, FridayReference
from ..domain.prayer_timeline import PrayerEventName
from .general_policy import in_scope, alert_scope_enabled


_REFERENCES = {
	MorningReference.AFTER_FAJR: (PrayerEventName.FAJR, False),
	MorningReference.BEFORE_SUNRISE: (PrayerEventName.SUNRISE, True),
	MorningReference.AFTER_SUNRISE: (PrayerEventName.SUNRISE, False),
	EveningReference.AFTER_ASR: (PrayerEventName.ASR, False),
	EveningReference.BEFORE_MAGHRIB: (PrayerEventName.MAGHRIB, True),
	EveningReference.AFTER_MAGHRIB: (PrayerEventName.MAGHRIB, False),
	FridayReference.AFTER_ASR: (PrayerEventName.ASR, False),
	FridayReference.BEFORE_MAGHRIB: (PrayerEventName.MAGHRIB, True),
}


class AdhkarAlertProducer:
	"""Providers return published settings, prepared references and a cached zone."""

	def __init__(self, settings, timeline, zone):
		self._settings, self._timeline, self._zone = settings, timeline, zone

	def produce(self, from_now, until, scope=None):
		if utc(until) <= utc(from_now):
			raise ValueError("alert window end must follow from_now")
		settings = self._settings()
		if settings.location is None:
			return ()
		zone = self._zone(settings.location.location.timezone_id)
		configs = (("morning", settings.adhkar.morning, AlertEventType.MORNING_ADHKAR),
			("evening", settings.adhkar.evening, AlertEventType.EVENING_ADHKAR),
			("friday", settings.adhkar.friday_hour, AlertEventType.FRIDAY_HOUR))
		configs = tuple(row for row in configs if alert_scope_enabled(settings, "adhkar." + row[0]) and in_scope("adhkar." + row[0], scope))
		if not configs:
			return ()
		result = []
		for reference in self._timeline(from_now, until):
			at = utc(Instant(reference.occurs_at))
			for name, config, kind in configs:
				reference_name, before = _REFERENCES[config.reference]
				if reference.name is not reference_name:
					continue
				if name == "friday" and at.astimezone(zone).weekday() != 4:
					continue
				when = at + timedelta(minutes=(-config.minutes if before else config.minutes))
				if not utc(from_now) <= when < utc(until):
					continue
				key = f"adhkar:{name}:{reference.name.value}:{at.isoformat()}"
				result.append(AlertEvent(key, kind, Instant(when), action=config.alert.action,
					message_id=f"alert.adhkar.{name}", sound_ref=config.alert.sound.value if config.alert.sound else None,
					source="AdhkarAlertProducer", scope="adhkar." + name, reference_at=Instant(at),
					timing=AlertTiming.BEFORE if before and config.minutes else AlertTiming.AT_OR_AFTER,
					metadata={"reference_kind": "prayerTimeline", "event_name": reference.name.value}))
		return tuple(sorted(result, key=lambda event: (utc(event.scheduled_at), event.type_order, event.event_id)))
