"""Application model and calculation for the current prayer timeline state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

from ..domain.models import Instant
from ..domain.prayer_timeline import PRAYER_EVENT_NAMES, PrayerEvent, PrayerEventName
from ..domain.settings import (
	DEFAULT_CURRENT_PRAYER_DURATION_MINUTES,
	DEFAULT_EVENT_PRE_ALERT_MINUTES,
	DEFAULT_IQAMA_ALERT_BEFORE_MINUTES,
	DEFAULT_IQAMA_DELAYS_MINUTES,
)
from .ports import NowProvider


MAX_CURRENT_PRAYER_DURATION_MINUTES = 180


def _whole_nonnegative(value: int, field_name: str) -> None:
	if isinstance(value, bool) or not isinstance(value, int):
		raise TypeError(f"{field_name} must be whole minutes")
	if value < 0:
		raise ValueError(f"{field_name} must not be negative")


def _utc(value: datetime) -> datetime:
	return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class IqamaRule:
	"""Estimated Iqama timing for one prayer, with zero disabling each feature."""

	delay_minutes: int
	alert_before_minutes: int = DEFAULT_IQAMA_ALERT_BEFORE_MINUTES

	def __post_init__(self) -> None:
		_whole_nonnegative(self.delay_minutes, "delay_minutes")
		_whole_nonnegative(self.alert_before_minutes, "alert_before_minutes")
		if self.delay_minutes > 0 and self.alert_before_minutes >= self.delay_minutes:
			raise ValueError("alert_before_minutes must be less than delay_minutes")

	@property
	def enabled(self) -> bool:
		return self.delay_minutes > 0

	def iqama_at(self, prayer_at: datetime) -> datetime | None:
		return prayer_at + timedelta(minutes=self.delay_minutes) if self.enabled else None

	def alert_at(self, prayer_at: datetime) -> datetime | None:
		iqama = self.iqama_at(prayer_at)
		if iqama is None or self.alert_before_minutes == 0:
			return None
		return iqama - timedelta(minutes=self.alert_before_minutes)


def _default_iqama_rules() -> Mapping[PrayerEventName, IqamaRule]:
	return MappingProxyType({
		name: IqamaRule(delay) for name, delay in DEFAULT_IQAMA_DELAYS_MINUTES.items()
	})


@dataclass(frozen=True, slots=True)
class IqamaSettings:
	rules: Mapping[PrayerEventName, IqamaRule] = field(default_factory=_default_iqama_rules)

	def __post_init__(self) -> None:
		if set(self.rules) != set(PRAYER_EVENT_NAMES):
			raise ValueError("Iqama settings must define exactly the five prayers")
		object.__setattr__(self, "rules", MappingProxyType(dict(self.rules)))


def _default_pre_alerts() -> Mapping[PrayerEventName, int]:
	return MappingProxyType({name: DEFAULT_EVENT_PRE_ALERT_MINUTES for name in PrayerEventName})


@dataclass(frozen=True, slots=True)
class EventPreAlertSettings:
	"""Pre-alert minutes also used as waiting-window lengths."""

	minutes: Mapping[PrayerEventName, int] = field(default_factory=_default_pre_alerts)

	def __post_init__(self) -> None:
		if set(self.minutes) != set(PrayerEventName):
			raise ValueError("pre-alert settings must define all eight events")
		for value in self.minutes.values():
			_whole_nonnegative(value, "pre-alert minutes")
		object.__setattr__(self, "minutes", MappingProxyType(dict(self.minutes)))


class PrayerStatePriority(Enum):
	WAITING = "waiting"
	CURRENT_PRAYER = "currentPrayer"
	NEXT_EVENT = "nextEvent"


@dataclass(frozen=True, slots=True)
class WaitingWindow:
	event: PrayerEvent
	starts_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentPrayer:
	event: PrayerEvent
	ends_at: datetime


@dataclass(frozen=True, slots=True)
class PrayerTimelineState:
	"""One complete snapshot; priority selects a view without discarding facts."""

	as_of: Instant
	previous_event: PrayerEvent | None
	next_event: PrayerEvent | None
	waiting_window: WaitingWindow | None
	current_prayer: CurrentPrayer | None
	iqama_at: datetime | None
	priority: PrayerStatePriority


class PrayerStateService:
	"""Derive previous, next, waiting, current-prayer, and Iqama state."""

	def __init__(self, now_provider: NowProvider) -> None:
		self._now_provider = now_provider

	def snapshot(self, events: Iterable[PrayerEvent], *,
			pre_alerts: EventPreAlertSettings | None = None,
			iqama: IqamaSettings | None = None,
			current_prayer_duration_minutes: int = DEFAULT_CURRENT_PRAYER_DURATION_MINUTES,
		) -> PrayerTimelineState:
		_whole_nonnegative(current_prayer_duration_minutes, "current_prayer_duration_minutes")
		if current_prayer_duration_minutes > MAX_CURRENT_PRAYER_DURATION_MINUTES:
			raise ValueError("current_prayer_duration_minutes must be at most 180")
		pre_alerts = pre_alerts or EventPreAlertSettings()
		iqama = iqama or IqamaSettings()
		ordered = tuple(sorted(events, key=lambda event: _utc(event.occurs_at)))
		if not ordered:
			raise ValueError("at least one timeline event is required")

		as_of = self._now_provider.now()
		now_utc = _utc(as_of.value)
		previous = next((event for event in reversed(ordered) if _utc(event.occurs_at) <= now_utc), None)
		next_event = next((event for event in ordered if _utc(event.occurs_at) > now_utc), None)

		waiting: WaitingWindow | None = None
		if next_event is not None:
			minutes = pre_alerts.minutes[next_event.name]
			if minutes > 0:
				starts_at = next_event.occurs_at - timedelta(minutes=minutes)
				if _utc(starts_at) <= now_utc < _utc(next_event.occurs_at):
					waiting = WaitingWindow(next_event, starts_at)

		current, iqama_at = self._current_prayer(
			ordered, now_utc, iqama, current_prayer_duration_minutes)
		priority = (PrayerStatePriority.WAITING if waiting is not None else
			PrayerStatePriority.CURRENT_PRAYER if current is not None else PrayerStatePriority.NEXT_EVENT)
		return PrayerTimelineState(as_of, previous, next_event, waiting, current, iqama_at, priority)

	@staticmethod
	def _current_prayer(events: tuple[PrayerEvent, ...], now_utc: datetime,
			iqama: IqamaSettings, duration_minutes: int,
		) -> tuple[CurrentPrayer | None, datetime | None]:
		started = [event for event in events
			if event.name in PRAYER_EVENT_NAMES and _utc(event.occurs_at) <= now_utc]
		if not started:
			return None, None
		prayer = started[-1]
		rule = iqama.rules[prayer.name]
		iqama_at = rule.iqama_at(prayer.occurs_at)
		base = iqama_at if iqama_at is not None else prayer.occurs_at
		end = base + timedelta(minutes=duration_minutes)

		boundaries = [event.occurs_at for event in events
			if event.name in PRAYER_EVENT_NAMES and _utc(event.occurs_at) > _utc(prayer.occurs_at)]
		if prayer.name is PrayerEventName.FAJR:
			boundaries.extend(event.occurs_at for event in events
				if event.name is PrayerEventName.SUNRISE and _utc(event.occurs_at) > _utc(prayer.occurs_at))
		if boundaries:
			end = min((end, *boundaries), key=_utc)
		if not (_utc(prayer.occurs_at) <= now_utc < _utc(end)):
			return None, None
		return CurrentPrayer(prayer, end), iqama_at
