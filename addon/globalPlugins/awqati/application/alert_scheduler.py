"""Central deterministic scheduler and presentation queue for automatic alerts."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from ..domain import AlertEvent, AlertEventType, AlertPriority, AwqatiSettings, Instant, LocationChanged, SettingsApplied, SystemTimeChanged
from .events import EventDispatcher
from .general_policy import automatic_alert_policy, AutomaticAlertKind
from ..domain.alerts import GRACE_PERIODS, priority_for, utc


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
		candidate = (local.replace(second=0, microsecond=0) + timedelta(minutes=minutes)).replace(tzinfo=tz, fold=0)
		back = candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
		if back == local.replace(second=0, microsecond=0) + timedelta(minutes=minutes):
			return candidate
	raise ValueError("civil time could not be resolved")


@dataclass(frozen=True, slots=True)
class PresentationLease:
	event: AlertEvent


# A scope of None means all automatic alerts. Sources must return fresh events.
RebuildSource = Callable[[Instant, str, str | None], Iterable[AlertEvent]]


def in_scope(event_scope: str, scope: str | None) -> bool:
	return scope is None or event_scope == scope or event_scope.startswith(scope + ".")


class AlertScheduler:
	"""Single-threaded logical scheduler, driven by its owner, without I/O.

	claim hands a lease off once. mark_presented acknowledges actual output;
	complete defaults to successful output. Cancellation before acknowledgement
	does not record success. After complete/cancel, the owner claims again.
	"""

	def __init__(self, now_provider: Callable[[], Instant] | object | None = None,
			settings: AwqatiSettings | Callable[[], AwqatiSettings] | None = None, *, rebuild_source: RebuildSource | None = None,
			local_time_provider: Callable[[Instant], datetime] | None = None) -> None:
		self._now_provider = now_provider
		self._settings = settings
		self._rebuild_source = rebuild_source
		# The adapter supplies conversion to the effective location timezone.
		# Without it, instants must carry that local timezone for quiet hours.
		self._local_time = local_time_provider or (lambda instant: instant.value)
		self._events: dict[str, AlertEvent] = {}
		self._dedup: dict[str, Instant] = {}
		self._suppressed: dict[str, Instant] = {}
		self._waiting: list[str] = []
		self._current: PresentationLease | None = None
		self._closed = False
		self._wakeup_at: Instant | None = None

	def _now(self) -> Instant:
		if self._now_provider is None:
			return Instant(datetime.now(timezone.utc))
		return self._now_provider() if callable(self._now_provider) else self._now_provider.now()

	@property
	def settings(self) -> AwqatiSettings | None:
		"""A provider (for example SettingsService.runtime_settings) avoids stale copies."""
		return self._settings() if callable(self._settings) else self._settings

	@property
	def wakeup_at(self) -> Instant | None:
		return self._wakeup_at

	@property
	def current(self) -> AlertEvent | None:
		return self._current.event if self._current else None

	@property
	def waiting(self) -> tuple[AlertEvent, ...]:
		return tuple(self._events[key] for key in self._waiting)

	def schedule(self, event: AlertEvent) -> bool:
		self._ensure_open()
		self._expire(self._now())
		if event.event_id in self._events or (self.current and self.current.event_id == event.event_id):
			return False
		if self._was_handled(event) or (self.current and self.current.dedup_key == event.dedup_key):
			return False
		if any(other.dedup_key == event.dedup_key for other in self._events.values()):
			return False
		if not self._is_enabled(event):
			return False
		self._events[event.event_id] = event
		self._recompute_wakeup()
		return True

	def schedule_many(self, events: Iterable[AlertEvent]) -> int:
		return sum(self.schedule(event) for event in events)

	def _was_handled(self, event: AlertEvent) -> bool:
		return event.dedup_key in self._dedup or event.dedup_key in self._suppressed

	def due(self, now: Instant | None = None) -> tuple[AlertEvent, ...]:
		self._ensure_open()
		now = now or self._now()
		self._expire(now)
		ready = []
		for event in tuple(self._events.values()):
			if not self._is_enabled(event) or self._was_handled(event):
				self.cancel(event.event_id)
			elif utc(event.scheduled_at) <= utc(now):
				if self._quiet(event, now) or self._quiet(event, event.scheduled_at):
					self._suppressed[event.dedup_key] = now
					self.cancel(event.event_id)
				else:
					ready.append(event)
		self._waiting = [event.event_id for event in sorted(ready, key=self._sort_key)]
		self._recompute_wakeup()
		return self.waiting

	def next_due(self, now: Instant | None = None) -> AlertEvent | None:
		due = self.due(now)
		return due[0] if due else None

	def claim_for_presentation(self, now: Instant | None = None) -> AlertEvent | None:
		self._ensure_open()
		now = now or self._now()
		ready = self.due(now)
		if self.current and (not self._is_enabled(self.current) or self._quiet(self.current, now)):
			self.cancel(self.current.event_id)
		if self.current:
			return None  # Never hand the same lease to a presenter twice.
		for event in ready:
			# Validate at the handoff boundary as well as admission to waiting.
			if event.is_valid_at(now) and self._is_enabled(event) and not self._was_handled(event):
				self._events.pop(event.event_id)
				self._waiting.remove(event.event_id)
				self._current = PresentationLease(event)
				self._recompute_wakeup()
				return event
		return None

	def mark_presented(self, event_id: str, now: Instant | None = None) -> bool:
		self._ensure_open()
		if not self.current or self.current.event_id != event_id:
			return False
		self._dedup[self.current.dedup_key] = now or self._now()
		return True

	def complete(self, event_id: str | None = None, *, presented: bool = True,
			now: Instant | None = None) -> bool:
		self._ensure_open()
		if not self.current or (event_id is not None and self.current.event_id != event_id):
			return False
		if presented:
			self.mark_presented(self.current.event_id, now)
		self._current = None
		self.due(now)
		return True

	def cancel(self, event_id: str) -> bool:
		self._ensure_open()
		removed = self._events.pop(event_id, None) is not None
		self._waiting = [key for key in self._waiting if key != event_id]
		if self.current and self.current.event_id == event_id:
			self._current = None
			removed = True
		self._recompute_wakeup()
		return removed

	def cancel_scope(self, scope: str | None) -> int:
		self._ensure_open()
		ids = [event.event_id for event in self._events.values() if in_scope(event.scope, scope)]
		if self.current and in_scope(self.current.scope, scope):
			ids.append(self.current.event_id)
		return sum(self.cancel(event_id) for event_id in ids)

	def rebuild(self, events: Iterable[AlertEvent], from_now: Instant | None = None,
			*, scope: str | None = None, preserve_current: bool = False, strictly_future: bool = False) -> int:
		self._ensure_open()
		now = from_now or self._now()
		# Materialize before mutation: a source failure must not erase the old queue.
		events = tuple(events)
		lease = self._current if preserve_current else None
		self.cancel_scope(scope)
		if lease:
			self._current = lease
		self._cleanup_dedup(now)
		return self.schedule_many(event for event in events
			if in_scope(event.scope, scope) and (utc(event.scheduled_at) > utc(now)
			if strictly_future else utc(event.scheduled_at) >= utc(now)))

	def resume(self, now: Instant | None = None, *, rebuild_source: RebuildSource | None = None) -> AlertEvent | None:
		self._ensure_open()
		now = now or self._now()
		source = rebuild_source or self._rebuild_source
		if source is None:
			raise ValueError("resume requires a rebuild source")
		future = tuple(source(now, "resume", None))
		chosen = self.claim_for_presentation(now)
		self.rebuild(future, now, preserve_current=True, strictly_future=True)
		return chosen

	def shutdown(self) -> None:
		if self._closed:
			return
		self._closed = True
		self._events.clear()
		self._waiting.clear()
		self._dedup.clear()
		self._suppressed.clear()
		self._current = None
		self._wakeup_at = None
		self._rebuild_source = None

	@staticmethod
	def _sort_key(event: AlertEvent) -> tuple:
		return (event.priority, utc(event.scheduled_at), event.type_order, event.event_id)

	def _expire(self, now: Instant) -> None:
		for event_id, event in tuple(self._events.items()):
			if utc(event.scheduled_at) <= utc(now) and not event.is_valid_at(now):
				self.cancel(event_id)
		self._cleanup_dedup(now)

	def _cleanup_dedup(self, now: Instant) -> None:
		cutoff = utc(now) - timedelta(days=2)
		self._dedup = {key: instant for key, instant in self._dedup.items() if utc(instant) > cutoff}
		self._suppressed = {key: instant for key, instant in self._suppressed.items() if utc(instant) > cutoff}

	def _recompute_wakeup(self) -> None:
		future = [event.scheduled_at for event in self._events.values() if event.event_id not in self._waiting]
		self._wakeup_at = min(future, key=utc) if future else None

	def _quiet(self, event: AlertEvent, now: Instant) -> bool:
		settings = self.settings
		if settings is None:
			return False
		kind = AutomaticAlertKind.PRAYER if event.priority <= AlertPriority.PRAYER_PRE_IQAMA_POST else AutomaticAlertKind.OTHER
		return automatic_alert_policy(settings, kind, self._local_time(now).time()).suppressed_by_quiet_hours

	def _is_enabled(self, event: AlertEvent) -> bool:
		return self.scope_enabled(event.scope)

	def scope_enabled(self, scope: str | None) -> bool:
		settings = self.settings
		if settings is None:
			return True
		if not settings.general.all_automatic_alerts_enabled:
			return False
		if scope is None:
			return True
		if in_scope(scope, "prayer"):
			return settings.prayer.alerts_enabled
		if in_scope(scope, "clock"):
			return settings.clock.automatic_alert_enabled
		if in_scope(scope, "adhkar"):
			if not settings.adhkar.alerts_enabled:
				return False
			for name, config in (("morning", settings.adhkar.morning), ("evening", settings.adhkar.evening),
					("friday", settings.adhkar.friday_hour), ("dailyWird", settings.adhkar.daily_wird),
					("daily_wird", settings.adhkar.daily_wird)):
				if in_scope(scope, "adhkar." + name):
					return config.enabled
			if in_scope(scope, "adhkar.recurring"):
				if not settings.adhkar.recurring.enabled:
					return False
				if scope == "adhkar.recurring":
					return True
				item = scope[len("adhkar.recurring."):]
				return any(identity.value == item and config.enabled for identity, config in settings.adhkar.recurring.items.items())
		return True

	def _ensure_open(self) -> None:
		if self._closed:
			raise RuntimeError("AlertScheduler is shut down")


class AlertCoordinator:
	"""Own event subscriptions and scope-aware rebuild orchestration.

	The scheduler's settings provider must return the committed runtime graph.
	Sources receive (from_now, reason, scope); None denotes the entire schedule.
	No producer or Windows/NVDA monitor is installed by this class.
	"""

	def __init__(self, scheduler: AlertScheduler, dispatcher: EventDispatcher, rebuild: RebuildSource) -> None:
		if not callable(scheduler._settings):
			raise ValueError("AlertCoordinator requires a runtime settings provider")
		self.scheduler = scheduler
		self._rebuild = rebuild
		self._previous = deepcopy(scheduler.settings)
		self._closed = False
		self._unsubscribers = [
			dispatcher.subscribe(SettingsApplied, self._settings_applied),
			dispatcher.subscribe(LocationChanged, self._location_changed),
			dispatcher.subscribe(SystemTimeChanged, self._system_time_changed),
		]

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		for unsubscribe in self._unsubscribers:
			unsubscribe()
		self._unsubscribers.clear()
		self.scheduler.shutdown()

	def resume(self, now: Instant | None = None) -> AlertEvent | None:
		if self._closed:
			raise RuntimeError("AlertCoordinator is closed")
		return self.scheduler.resume(now, rebuild_source=self._rebuild)

	def _run_rebuild(self, instant: Instant, reason: str, scope: str | None = None) -> None:
		self.scheduler.rebuild(self._rebuild(instant, reason, scope), instant, scope=scope)

	def _settings_applied(self, event: SettingsApplied) -> None:
		if self._closed:
			return
		current = deepcopy(self.scheduler.settings)
		previous = self._previous
		if current is None or previous is None:
			raise ValueError("SettingsApplied requires a runtime settings provider")
		now = event.automatic_alerts_rebuild_from or event.occurred_at
		scopes = self._changed_scopes(previous, current)
		for scope in scopes:
			if self.scheduler.scope_enabled(scope):
				self._run_rebuild(now, "settingsApplied", scope)
			else:
				self.scheduler.cancel_scope(scope)
		self._previous = current

	@staticmethod
	def _changed_scopes(old: AwqatiSettings, new: AwqatiSettings) -> list[str | None]:
		if old.general.all_automatic_alerts_enabled != new.general.all_automatic_alerts_enabled or old.location != new.location:
			return [None]
		scopes = []
		calculation = ("calculation_method", "asr_method", "high_latitude_rule", "corrections_minutes")
		if any(getattr(old.prayer, key) != getattr(new.prayer, key) for key in calculation):
			scopes.extend(["prayer", "clock", "adhkar.morning", "adhkar.evening", "adhkar.friday"])
		if old.prayer.alerts_enabled != new.prayer.alerts_enabled or old.prayer.events != new.prayer.events:
			scopes.append("prayer")
		if old.clock != new.clock:
			scopes.append("clock")
		if old.adhkar.alerts_enabled != new.adhkar.alerts_enabled:
			scopes.append("adhkar")
		for scope, attr in (("morning", "morning"), ("evening", "evening"), ("friday", "friday_hour"), ("dailyWird", "daily_wird")):
			if getattr(old.adhkar, attr) != getattr(new.adhkar, attr):
				scopes.append("adhkar." + scope)
		a, b = old.adhkar.recurring, new.adhkar.recurring
		if a.enabled != b.enabled or a.interval_minutes != b.interval_minutes:
			scopes.append("adhkar.recurring")
		else:
			for identity in a.items:
				if a.items[identity] != b.items[identity]:
					scopes.append("adhkar.recurring." + identity.value)
		if old.general.quiet_hours != new.general.quiet_hours:
			scopes.extend(["clock", "adhkar"])
			if old.general.quiet_hours.apply_to_prayer_alerts or new.general.quiet_hours.apply_to_prayer_alerts:
				scopes.append("prayer")
		return [scope for scope in dict.fromkeys(scopes) if not any(other != scope and in_scope(scope, other) for other in scopes)]

	def _location_changed(self, event: LocationChanged) -> None:
		if not self._closed:
			self._run_rebuild(event.occurred_at, "locationChanged")
			# SettingsService publishes location first; the full rebuild covers its graph.
			self._previous = deepcopy(self.scheduler.settings)

	def _system_time_changed(self, event: SystemTimeChanged) -> None:
		if not self._closed:
			self._run_rebuild(event.occurred_at, "systemTimeChanged")
