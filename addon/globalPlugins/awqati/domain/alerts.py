"""Platform-neutral alert event values used by the central scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum, Enum
from typing import Any

from .models import Instant


class AlertPriority(IntEnum):
	"""Stable ordering; lower numeric values are more important."""

	PRAYER_TIME = 1
	SUNRISE_NIGHT = 2
	PRAYER_PRE_IQAMA_POST = 3
	CLOCK = 4
	TIMED_ADHKAR_WIRD = 5
	RECURRING_DHIKR = 6


class AlertEventType(Enum):
	PRAYER_TIME = "prayerTime"
	SUNRISE = "sunrise"
	MIDNIGHT = "midnight"
	LAST_THIRD = "lastThird"
	PRAYER_PRE_ALERT = "prayerPreAlert"
	IQAMA = "iqama"
	IQAMA_PRE_ALERT = "iqamaPreAlert"
	PRAYER_POST_ALERT = "prayerPostAlert"
	CLOCK = "clock"
	MORNING_ADHKAR = "morningAdhkar"
	EVENING_ADHKAR = "eveningAdhkar"
	FRIDAY_HOUR = "fridayHour"
	DAILY_WIRD = "dailyWird"
	RECURRING_DHIKR = "recurringDhikr"


_TYPE_ORDER = {kind: index for index, kind in enumerate(AlertEventType)}


@dataclass(frozen=True, slots=True, init=False)
class AlertEvent:
	"""A complete, language-neutral scheduled alert description."""

	event_id: str
	event_type: AlertEventType
	scheduled_at: Instant
	priority: AlertPriority
	action: Any
	message_id: str | None
	sound_ref: str | None
	grace_period: timedelta
	dedup_key: str
	source: str
	scope: str
	expires_at: Instant | None
	reference_at: Instant | None
	metadata: dict[str, Any]

	def __init__(self, event_id: str, event_type: AlertEventType,
		scheduled_at: Instant | datetime, priority: AlertPriority,
		action: Any = None, message_id: str | None = None,
		sound_ref: str | None = None, grace_period: timedelta | None = None,
		dedup_key: str | None = None, source: str = "unknown", scope: str = "general",
		expires_at: Instant | datetime | None = None,
		reference_at: Instant | datetime | None = None,
		metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
		if "execution_at" in kwargs:
			scheduled_at = kwargs.pop("execution_at")
		if kwargs:
			raise TypeError(f"unknown AlertEvent fields: {', '.join(kwargs)}")
		if not isinstance(event_type, AlertEventType):
			event_type = AlertEventType(event_type)
		if not isinstance(priority, AlertPriority):
			priority = AlertPriority(priority)
		for value in (scheduled_at, expires_at, reference_at):
			if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
				raise ValueError("alert times must be timezone-aware")
		def instant(value: Instant | datetime | None) -> Instant | None:
			return value if value is None or isinstance(value, Instant) else Instant(value)
		when = instant(scheduled_at)
		assert when is not None
		if grace_period is None:
			minutes = {AlertEventType.CLOCK: 2, AlertEventType.MORNING_ADHKAR: 15, AlertEventType.EVENING_ADHKAR: 15, AlertEventType.FRIDAY_HOUR: 15, AlertEventType.DAILY_WIRD: 15, AlertEventType.RECURRING_DHIKR: 0}.get(event_type, 10)
			grace_period = timedelta(minutes=minutes)
		if grace_period < timedelta(0):
			raise ValueError("grace_period must not be negative")
		key = dedup_key or event_id
		if not key:
			raise ValueError("dedup_key must not be empty")
		object.__setattr__(self, "event_id", event_id)
		object.__setattr__(self, "event_type", event_type)
		object.__setattr__(self, "scheduled_at", when)
		object.__setattr__(self, "priority", priority)
		object.__setattr__(self, "action", action)
		object.__setattr__(self, "message_id", message_id)
		object.__setattr__(self, "sound_ref", sound_ref)
		object.__setattr__(self, "grace_period", grace_period)
		object.__setattr__(self, "dedup_key", key)
		object.__setattr__(self, "source", source)
		object.__setattr__(self, "scope", scope)
		object.__setattr__(self, "expires_at", instant(expires_at))
		object.__setattr__(self, "reference_at", instant(reference_at))
		object.__setattr__(self, "metadata", dict(metadata or {}))
		if self.event_type in {AlertEventType.PRAYER_PRE_ALERT, AlertEventType.IQAMA_PRE_ALERT} and self.reference_at and self.expires_at is None:
			object.__setattr__(self, "expires_at", self.reference_at)

	@property
	def execution_at(self) -> Instant:
		return self.scheduled_at

	@property
	def type_order(self) -> int:
		return _TYPE_ORDER[self.event_type]

	def is_valid_at(self, now: Instant) -> bool:
		if now.value < self.scheduled_at.value:
			return False
		if self.expires_at is not None and now.value >= self.expires_at.value:
			return False
		return now.value <= self.scheduled_at.value + self.grace_period