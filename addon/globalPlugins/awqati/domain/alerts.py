"""Platform-neutral alert event values used by the central scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum, Enum
from typing import Any
from types import MappingProxyType

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
	IQAMA_PRE_ALERT = "iqamaPreAlert"
	IQAMA = "iqamaPreAlert"  # Compatibility alias; no separate at-Iqama event.
	PRAYER_POST_ALERT = "prayerPostAlert"
	CLOCK = "clock"
	MORNING_ADHKAR = "morningAdhkar"
	EVENING_ADHKAR = "eveningAdhkar"
	FRIDAY_HOUR = "fridayHour"
	DAILY_WIRD = "dailyWird"
	RECURRING_DHIKR = "recurringDhikr"


def priority_for(event_type: AlertEventType) -> AlertPriority:
	if event_type is AlertEventType.PRAYER_TIME:
		return AlertPriority.PRAYER_TIME
	if event_type in {AlertEventType.SUNRISE, AlertEventType.MIDNIGHT, AlertEventType.LAST_THIRD}:
		return AlertPriority.SUNRISE_NIGHT
	if event_type in {AlertEventType.PRAYER_PRE_ALERT, AlertEventType.IQAMA, AlertEventType.IQAMA_PRE_ALERT, AlertEventType.PRAYER_POST_ALERT}:
		return AlertPriority.PRAYER_PRE_IQAMA_POST
	if event_type is AlertEventType.CLOCK:
		return AlertPriority.CLOCK
	if event_type is AlertEventType.RECURRING_DHIKR:
		return AlertPriority.RECURRING_DHIKR
	return AlertPriority.TIMED_ADHKAR_WIRD


class AlertTiming(Enum):
	AT_OR_AFTER = "atOrAfter"
	BEFORE = "before"


GRACE_PERIODS = MappingProxyType({kind: timedelta(minutes=(
	0 if kind is AlertEventType.RECURRING_DHIKR else
	2 if kind is AlertEventType.CLOCK else
	15 if priority_for(kind) is AlertPriority.TIMED_ADHKAR_WIRD else 10
)) for kind in AlertEventType})


def utc(instant: Instant) -> datetime:
	"""Compare elapsed instants, including different folds of the same zone."""
	return instant.value.astimezone(timezone.utc)


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
	timing: AlertTiming

	def __init__(self, event_id: str, event_type: AlertEventType,
		scheduled_at: Instant | datetime, priority: AlertPriority | None = None,
		action: Any = None, message_id: str | None = None,
		sound_ref: str | None = None, grace_period: timedelta | None = None,
		dedup_key: str | None = None, source: str = "unknown", scope: str = "general",
		expires_at: Instant | datetime | None = None,
		reference_at: Instant | datetime | None = None,
		metadata: dict[str, Any] | None = None, timing: AlertTiming = AlertTiming.AT_OR_AFTER, **kwargs: Any) -> None:
		if "execution_at" in kwargs:
			scheduled_at = kwargs.pop("execution_at")
		if kwargs:
			raise TypeError(f"unknown AlertEvent fields: {', '.join(kwargs)}")
		if not isinstance(event_type, AlertEventType):
			event_type = AlertEventType(event_type)
		if priority is not None and AlertPriority(priority) != priority_for(event_type):
			raise ValueError("priority must match event_type")
		priority = priority_for(event_type)
		timing = AlertTiming(timing)
		if event_type in {AlertEventType.PRAYER_PRE_ALERT, AlertEventType.IQAMA_PRE_ALERT}:
			timing = AlertTiming.BEFORE
		if timing is AlertTiming.BEFORE and reference_at is None:
			raise ValueError("before alerts require reference_at")
		if not isinstance(event_id, str) or not event_id.strip():
			raise ValueError("event_id must not be empty")
		if not isinstance(scope, str) or any(not part or not part.strip() for part in scope.split(".")):
			raise ValueError("scope must be a non-empty dotted path")
		if scope == "adhkar.daily_wird" or scope.startswith("adhkar.daily_wird."):
			scope = "adhkar.dailyWird" + scope[len("adhkar.daily_wird"):]
		for value in (scheduled_at, expires_at, reference_at):
			if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
				raise ValueError("alert times must be timezone-aware")
		def instant(value: Instant | datetime | None) -> Instant | None:
			return value if value is None or isinstance(value, Instant) else Instant(value)
		when = instant(scheduled_at)
		assert when is not None
		if grace_period is None:
			grace_period = GRACE_PERIODS[event_type]
		if grace_period < timedelta(0):
			raise ValueError("grace_period must not be negative")
		key = event_id if dedup_key is None else dedup_key
		if not isinstance(key, str) or not key.strip():
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
		object.__setattr__(self, "timing", timing)
		if timing is AlertTiming.BEFORE:
			if utc(self.reference_at) <= utc(self.scheduled_at):
				raise ValueError("before reference must follow scheduled_at; use AT_OR_AFTER for zero offset")
			if self.expires_at is None or utc(self.expires_at) > utc(self.reference_at):
				object.__setattr__(self, "expires_at", self.reference_at)

	@property
	def execution_at(self) -> Instant:
		return self.scheduled_at

	@property
	def type_order(self) -> int:
		return _TYPE_ORDER[self.event_type]

	def is_valid_at(self, now: Instant) -> bool:
		when, current = utc(self.scheduled_at), utc(now)
		if current < when:
			return False
		if self.expires_at is not None and current >= utc(self.expires_at):
			return False
		if self.timing is AlertTiming.BEFORE:
			return current < utc(self.reference_at)
		if self.event_type is AlertEventType.RECURRING_DHIKR:
			return current == when
		return current <= when + self.grace_period
