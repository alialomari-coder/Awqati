"""Turn an existing, finite prayer timeline into neutral alert events."""

from __future__ import annotations

from datetime import timedelta
from typing import Callable, Iterable

from ..domain import AlertEvent, AlertEventType, AlertTiming, AwqatiSettings, Instant
from ..domain.alerts import utc
from ..domain.prayer_timeline import PRAYER_EVENT_NAMES, PrayerEvent, PrayerEventName
from ..domain.settings import AlertAction, AlertOutputSettings
from .prayer_state import IqamaRule


class PrayerAlertProducer:
	"""Read published settings and prepared timeline data; never calculate state.

	The timeline provider must supply references on both sides of the requested
	alert window when an offset moves their alerts into it. It must be fast and
	perform no I/O. The owner supplies an explicit, exclusive end, not a default
	number of days. Neither provider nor producer mutates the scheduler.
	"""

	def __init__(self, settings: Callable[[], AwqatiSettings],
			timeline: Callable[[Instant, Instant], Iterable[PrayerEvent]]) -> None:
		self._settings = settings
		self._timeline = timeline

	def produce(self, from_now: Instant, until: Instant) -> tuple[AlertEvent, ...]:
		if utc(until) <= utc(from_now):
			raise ValueError("alert window end must follow from_now")
		settings = self._settings().prayer
		if not settings.alerts_enabled:
			return ()
		result = []
		for reference in self._timeline(from_now, until):
			config = settings.events[reference.name]
			at = utc(Instant(reference.occurs_at))
			category = "prayer" if reference.name in PRAYER_EVENT_NAMES else reference.name.value

			def add(kind: AlertEventType, when, output: AlertOutputSettings,
					message_id: str, reference_at=at, minutes: int = 0) -> None:
				if output.action is AlertAction.SILENT or not utc(from_now) <= when < utc(until):
					return
				# Identity describes the occurrence, not wording, action or offset.
				key = f"prayer:{reference.name.value}:{at.isoformat()}:{kind.value}"
				metadata = {"event_name": reference.name.value, "event_kind": reference.kind.value,
					"duration_minutes": minutes, "prayer_at": Instant(at)}
				if kind is AlertEventType.IQAMA_PRE_ALERT:
					metadata["reference_kind"] = "userEstimatedIqama"
				else:
					metadata["reference_kind"] = "prayerTimeline"
				result.append(AlertEvent(key, kind, Instant(when), action=output.action,
					message_id=message_id, sound_ref=output.sound.value if output.sound else None,
					source="PrayerAlertProducer", scope="prayer", reference_at=Instant(reference_at),
					timing=AlertTiming.BEFORE if kind in (AlertEventType.PRAYER_PRE_ALERT,
						AlertEventType.IQAMA_PRE_ALERT) else AlertTiming.AT_OR_AFTER,
					metadata=metadata))

			if config.pre_alert_minutes > 0:
				add(AlertEventType.PRAYER_PRE_ALERT, at - timedelta(minutes=config.pre_alert_minutes),
					config.pre_alert, f"alert.{category}.before", minutes=config.pre_alert_minutes)
			kind = (AlertEventType.PRAYER_TIME if reference.name in PRAYER_EVENT_NAMES
				else AlertEventType(reference.name.value))
			add(kind, at, config.at_time_alert, f"alert.{category}.at")
			if reference.name in PRAYER_EVENT_NAMES:
				assert config.iqama is not None
				rule = IqamaRule(config.iqama.delay_minutes, config.iqama.alert_before_minutes)
				# Existing IqamaRule receives UTC so its duration arithmetic is elapsed time.
				when = rule.alert_at(at)
				if when is not None:
					add(AlertEventType.IQAMA_PRE_ALERT, when, config.iqama.alert,
						"alert.prayer.iqamaBefore", rule.iqama_at(at), rule.alert_before_minutes)
			elif config.post_alert_minutes:
				assert config.post_alert is not None
				add(AlertEventType.PRAYER_POST_ALERT, at + timedelta(minutes=config.post_alert_minutes),
					config.post_alert, f"alert.{category}.after", minutes=config.post_alert_minutes)
		return tuple(sorted(result, key=lambda event: (utc(event.scheduled_at), event.type_order, event.event_id)))
