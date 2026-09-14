"""Central deterministic scheduler and presentation queue for automatic alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from ..domain import AlertEvent, AlertEventType, AlertPriority, AwqatiSettings, Instant, LocationChanged, SettingsApplied, SystemTimeChanged
from .events import EventDispatcher
from .general_policy import automatic_alert_policy


GRACE_PERIODS = {
	AlertEventType.PRAYER_TIME: timedelta(minutes=10),
	AlertEventType.PRAYER_POST_ALERT: timedelta(minutes=10),
	AlertEventType.CLOCK: timedelta(minutes=2),
	AlertEventType.MORNING_ADHKAR: timedelta(minutes=15),
	AlertEventType.EVENING_ADHKAR: timedelta(minutes=15),
	AlertEventType.FRIDAY_HOUR: timedelta(minutes=15),
	AlertEventType.DAILY_WIRD: timedelta(minutes=15),
	AlertEventType.RECURRING_DHIKR: timedelta(0),
}


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


def resolve_civil_time(local: datetime, tz: timezone | object) -> datetime:
	"""Resolve a civil wall time: skip a missing DST hour, choose first fold."""
	if local.tzinfo is not None:
		local = local.replace(tzinfo=None)
	for fold in (0, 1):
		candidate = local.replace(tzinfo=tz, fold=fold)
		back = candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
		if back == local:
			return candidate
	# A gap: advance minute-by-minute to the first representable local instant.
	for minutes in range(1, 181):
		candidate = (local + timedelta(minutes=minutes)).replace(tzinfo=tz, fold=0)
		back = candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
		if back == local + timedelta(minutes=minutes):
			return candidate
	raise ValueError("civil time could not be resolved")


@dataclass(frozen=True, slots=True)
class PresentationLease:
	event: AlertEvent


class AlertScheduler:
	"""The sole in-process scheduler; it never performs speech, sound, or I/O."""

	def __init__(self, now_provider: Callable[[], Instant] | object | None = None, settings: AwqatiSettings | None = None) -> None:
		self._now_provider = now_provider
		self._settings = settings
		self._events: dict[str, AlertEvent] = {}
		self._dedup: dict[str, Instant] = {}
		self._waiting: list[str] = []
		self._current: PresentationLease | None = None
		self._closed = False
		self._wakeup_at: Instant | None = None

	def _now(self) -> Instant:
		if self._now_provider is None:
			return Instant(datetime.now(timezone.utc))
		value = self._now_provider() if callable(self._now_provider) else self._now_provider.now()
		return value

	@property
	def wakeup_at(self) -> Instant | None:
		return self._wakeup_at

	@property
	def current(self) -> AlertEvent | None:
		return self._current.event if self._current else None

	@property
	def waiting(self) -> tuple[AlertEvent, ...]:
		return tuple(self._events[key] for key in self._waiting if key in self._events)

	def schedule(self, event: AlertEvent) -> bool:
		self._ensure_open()
		if event.dedup_key in self._dedup:
			return False
		self._events[event.event_id] = event
		self._recompute_wakeup()
		return True

	def schedule_many(self, events: Iterable[AlertEvent]) -> int:
		return sum(self.schedule(event) for event in events)

	def due(self, now: Instant | None = None) -> tuple[AlertEvent, ...]:
		now = now or self._now()
		self._expire(now)
		result = [event for event in self._events.values() if event.is_valid_at(now) and event.scheduled_at.value <= now.value]
		return tuple(sorted(result, key=self._sort_key))

	def next_due(self, now: Instant | None = None) -> AlertEvent | None:
		due = self.due(now)
		return due[0] if due else None

	def claim_for_presentation(self, now: Instant | None = None) -> AlertEvent | None:
		now = now or self._now()
		if self._current is not None:
			return self._current.event
		for event in self.due(now):
			if not self._is_enabled(event):
				self.cancel(event.event_id)
				continue
			self._current = PresentationLease(event)
			self._events.pop(event.event_id, None)
			self._dedup[event.dedup_key] = now
			self._recompute_wakeup()
			return event
		return None

	def complete(self, event_id: str | None = None) -> bool:
		if self._current is None or (event_id is not None and self._current.event.event_id != event_id):
			return False
		self._current = None
		self._recompute_wakeup()
		return True

	def cancel(self, event_id: str) -> bool:
		removed = self._events.pop(event_id, None) is not None
		self._waiting = [key for key in self._waiting if key != event_id]
		if self._current and self._current.event.event_id == event_id:
			self._current = None
		self._recompute_wakeup()
		return removed

	def cancel_scope(self, scope: str) -> int:
		ids = [event.event_id for event in self._events.values() if event.scope == scope or event.scope.startswith(scope + ".")]
		count = sum(self.cancel(event_id) for event_id in ids)
		if self._current and (self._current.event.scope == scope or self._current.event.scope.startswith(scope + ".")):
			self._current = None
		return count

	def rebuild(self, events: Iterable[AlertEvent], from_now: Instant | None = None) -> int:
		self._events.clear(); self._waiting.clear(); self._current = None
		if from_now is not None:
			self._dedup = {key: instant for key, instant in self._dedup.items() if instant.value >= from_now.value - timedelta(days=2)}
		count = self.schedule_many(events)
		self._cleanup_dedup(from_now or self._now())
		return count

	def resume(self, now: Instant | None = None) -> AlertEvent | None:
		now = now or self._now()
		candidate = self.next_due(now)
		if candidate is None:
			self.rebuild((), now); return None
		chosen = self.claim_for_presentation(now)
		self.rebuild((), now)
		return chosen

	def shutdown(self) -> None:
		self._closed = True; self._events.clear(); self._waiting.clear(); self._current = None; self._wakeup_at = None

	def _sort_key(self, event: AlertEvent) -> tuple[object, int, int, str]:
		return (event.priority, event.scheduled_at.value, event.type_order, event.event_id)

	def _expire(self, now: Instant) -> None:
		for event_id, event in tuple(self._events.items()):
			if event.scheduled_at.value <= now.value and not event.is_valid_at(now):
				self.cancel(event_id)
		self._cleanup_dedup(now)

	def _cleanup_dedup(self, now: Instant) -> None:
		cutoff = now.value - timedelta(days=2)
		self._dedup = {key: instant for key, instant in self._dedup.items() if instant.value >= cutoff}

	def _recompute_wakeup(self) -> None:
		future = [event.scheduled_at for event in self._events.values()]
		self._wakeup_at = min(future, key=lambda value: value.value) if future else None

	def _is_enabled(self, event: AlertEvent) -> bool:
		settings = self._settings
		if settings is None: return True
		if not settings.general.all_automatic_alerts_enabled: return False
		scope = event.scope
		if scope == "prayer" or scope.startswith("prayer."): return settings.prayer.alerts_enabled
		if scope == "clock" or scope.startswith("clock."): return settings.clock.automatic_alert_enabled
		if scope == "adhkar" or scope.startswith("adhkar."):
			if not settings.adhkar.alerts_enabled: return False
			if scope.startswith("adhkar.morning"): return settings.adhkar.morning.enabled
			if scope.startswith("adhkar.evening"): return settings.adhkar.evening.enabled
			if scope.startswith("adhkar.friday"): return settings.adhkar.friday_hour.enabled
			if scope.startswith(("adhkar.dailyWird", "adhkar.daily_wird")): return settings.adhkar.daily_wird.enabled
			if scope.startswith("adhkar.recurring"):
				if not settings.adhkar.recurring.enabled: return False
				item = scope.rsplit(".", 1)[-1]
				return any(identity.value == item and config.enabled for identity, config in settings.adhkar.recurring.items.items())
		return True

	def _ensure_open(self) -> None:
		if self._closed: raise RuntimeError("AlertScheduler is shut down")


class AlertCoordinator:
	"""Consumes existing application events and delegates all rebuilds to one scheduler."""

	def __init__(self, scheduler: AlertScheduler, dispatcher: EventDispatcher, rebuild: Callable[[Instant, str], Iterable[AlertEvent]] | None = None) -> None:
		self.scheduler = scheduler; self._rebuild = rebuild; self._unsubscribers = [
			dispatcher.subscribe(SettingsApplied, self._settings_applied),
			dispatcher.subscribe(LocationChanged, self._location_changed),
			dispatcher.subscribe(SystemTimeChanged, self._system_time_changed),
		]

	def close(self) -> None:
		for unsubscribe in self._unsubscribers: unsubscribe()
		self._unsubscribers.clear(); self.scheduler.shutdown()

	def _run_rebuild(self, instant: Instant, reason: str) -> None:
		self.scheduler.rebuild(self._rebuild(instant, reason) if self._rebuild else (), instant)

	def _settings_applied(self, event: SettingsApplied) -> None:
		self._run_rebuild(event.automatic_alerts_rebuild_from or event.occurred_at, "settingsApplied")

	def _location_changed(self, event: LocationChanged) -> None:
		self._run_rebuild(event.occurred_at, "locationChanged")

	def _system_time_changed(self, event: SystemTimeChanged) -> None:
		self._run_rebuild(event.occurred_at, "systemTimeChanged")