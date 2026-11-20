"""The single NVDA-owned alert runtime and its lifecycle timers."""

from __future__ import annotations

from datetime import timezone, timedelta
from time import monotonic
from pathlib import Path
from threading import RLock

from ..application import (
	AlertCoordinator, AlertPresenter, AlertScheduler, PrayerClockRebuildSource,
	timer_delivery_instant,
)
from ..application.personal_alarms import PersonalAlarmService, CombinedAlarmSource
from ..infrastructure.alarm_repository import AlarmRepository
from ..infrastructure.computer_timezone import ComputerTimezone
from ..domain import AlertEventType, LocationChanged, SettingsApplied, SystemTimeChanged
from ..domain.alerts import utc
from ..infrastructure import SoundFileService
from .audio_service import AudioService
from .speech_service import SpeechService
from . import compat


class AwqatiRuntime:
	"""Own exactly one scheduler, coordinator and presenter."""

	def __init__(self, settings, now, zones, prayers, *, user_data_root: Path,
			addon_root: Path, language_provider, on_error, on_alarm_fallback=None,
			on_alarm_data_error=None, on_alarm_read_error=None) -> None:
		self.settings, self.now, self.zones = settings, now, zones
		runtime_settings = lambda: settings.runtime_settings
		self._alarm_error_reported = False
		def alarm_error(error):
			on_error(error)
			if not self._alarm_error_reported and on_alarm_data_error:
				self._alarm_error_reported = True
				compat.call_after(on_alarm_data_error)
		self._alarm_error = alarm_error
		self._alarm_read_error_reported = False
		def read_error(error):
			on_error(error)
			notice = on_alarm_read_error or on_alarm_data_error
			if not self._alarm_read_error_reported and notice:
				self._alarm_read_error_reported = True
				compat.call_after(notice)
		self.alarms = PersonalAlarmService(AlarmRepository(user_data_root / "personal_alarms.json", read_error),
			ComputerTimezone(zones), now, read_error)
		self.alarms.diagnostic = alarm_error  # Subsequent diagnostics are write failures.
		self.last_snooze_minutes = None
		self._last_snooze = None
		self.source = CombinedAlarmSource(PrayerClockRebuildSource.from_services(runtime_settings, prayers, zones), self.alarms)
		def local_time(instant):
			stored = settings.runtime_settings.location
			zone = zones.get_timezone(stored.location.timezone_id) if stored else timezone.utc
			return instant.value.astimezone(zone)
		self.scheduler = AlertScheduler(now, runtime_settings,
			rebuild_source=self.source, local_time_provider=local_time,
			personal_local_time_provider=lambda instant: utc(instant).astimezone(self.alarms.zone_provider()),
			on_discard=self._discard)
		self.coordinator = AlertCoordinator(self.scheduler, settings.events, self.source)
		self.audio = AudioService(SoundFileService(user_data_root, addon_root),
			dispatch=compat.call_after, diagnostic=on_error, on_fallback=on_alarm_fallback)
		self.speech = SpeechService()
		self.previews = set()
		self.presenter = AlertPresenter(self.scheduler, self.audio, self.speech,
			language_provider=language_provider, on_error=on_error,
			on_claim=self._claim, on_finish=self.alarms.finish)
		self._lock, self._timer, self._generation, self._closed = RLock(), None, 0, False
		self._day_boundary = None
		self._last_wall = self.now.now()
		self._last_tick = monotonic()
		self._last_zone = str(self.alarms.zone_provider())
		self._unsubscribers = [
			settings.events.subscribe(SettingsApplied, self._changed),
			settings.events.subscribe(LocationChanged, self._changed),
			settings.events.subscribe(SystemTimeChanged, self._changed),
		]
		instant = now.now()
		self.scheduler.rebuild(self.source(instant, "startup", None), instant)
		self.presenter.present_next(instant)
		self._reschedule()

	def _changed(self, _event) -> None:
		if not self.settings.runtime_settings.general.all_automatic_alerts_enabled:
			try:
				self.clear_snoozes()
			except OSError as error:
				self._alarm_error(error)
		self.presenter.present_next()
		self._reschedule()

	def _discard(self, event, outcome):
		self.alarms.discarded(event, outcome)
		if getattr(self, "countdowns", None):
			try:
				self.countdowns.handled(event, outcome)
			except OSError:
				# The timer controller reports its storage_error. A failed
				# timer write must not prevent expiry of unrelated alerts.
				pass

	def _claim(self, event):
		AudioService.cancel_previews()
		for preview in tuple(self.previews):
			preview.cancel()
		if getattr(self, "countdowns", None):
			self.countdowns.handled(event)
		try:
			self.alarms.claimed(event)
		except OSError as error:
			self._alarm_error(error)
			raise
		if event.event_type is AlertEventType.PERSONAL_ALARM and not event.metadata["snooze"]:
			# A new weekly occurrence supersedes snoozes of the previous cycle.
			self.scheduler.cancel_scope(event.scope, include_current=False)

	def clear_snoozes(self):
		from copy import deepcopy
		state = deepcopy(self.alarms.state)
		changed = False
		for row in state.values():
			if row.get("snooze"):
				row.update(snooze=None, outcome="globalDisabled")
				changed = True
		if changed:
			self.alarms._commit(dict(self.alarms.alarms), state)

	def alarms_changed(self):
		current = self.presenter.current
		if current and current.event_type is AlertEventType.PERSONAL_ALARM:
			definition = self.alarms.alarms.get(current.metadata["alarm_id"])
			if definition is None or not definition.enabled or self.alarms._event(definition, current.scheduled_at, snooze=current.metadata["snooze"]).metadata != current.metadata:
				self.presenter.cancel_current(outcome="editedOrDisabled")
		now = self.now.now()
		self.scheduler.rebuild(self.alarms.events(now), now, scope="personal", preserve_current=True)
		self.presenter.present_next(now)
		self._reschedule()

	def stop_alarm(self):
		current = self.presenter.current
		if not current or current.event_type is not AlertEventType.PERSONAL_ALARM:
			if self._last_snooze and self.alarms.cancel_snooze(*self._last_snooze):
				self._last_snooze = None
				self.alarms_changed()
				return True
			return False
		self.presenter.cancel_current()
		self.alarms_changed()
		return True

	def snooze_alarm(self):
		self.last_snooze_minutes = None
		self._last_snooze = None
		event = self.alarms.active
		started_at = self.now.now()
		if not self.settings.runtime_settings.general.all_automatic_alerts_enabled:
			return False
		if not self.alarms.snooze(started_at):
			return False
		identity = event.metadata["alarm_id"]
		deadline = self.alarms.state[identity]["snooze"]
		from datetime import datetime
		delay = (datetime.fromisoformat(deadline) - utc(started_at)).total_seconds()
		self.presenter.cancel_current(outcome="snoozed")
		self.alarms_changed()
		when = type(started_at)(datetime.fromisoformat(deadline))
		pending_event = self.alarms._event(self.alarms.alarms[identity], when, snooze=True)
		if pending_event.event_id not in self.scheduler._events:
			self.alarms.cancel_snooze(identity, deadline)
			return False
		self._last_snooze = (identity, deadline)
		self.last_snooze_minutes = int(delay // 60)
		return True

	def _reschedule(self) -> None:
		with self._lock:
			if self._closed:
				return
			self._generation += 1
			generation = self._generation
			if self._timer is not None:
				self._timer.cancel()
				self._timer = None
			now = self.now.now()
			self._day_boundary = self.source.next_rebuild_at(now)
			alert_deadline = self.scheduler.wakeup_at
			poll = type(now)(utc(now) + timedelta(seconds=0.25 if self.alarms.active else 30))
			deadlines = [value for value in (alert_deadline, self._day_boundary, poll) if value]
			if not deadlines:
				return
			deadline = min(deadlines, key=utc)
			delay = max(1, int((utc(deadline) - utc(now)).total_seconds() * 1000))
			is_alert_wakeup = alert_deadline is not None and utc(deadline) == utc(alert_deadline)
			self._timer = compat.schedule(
				delay, lambda: self._wake(generation, deadline, is_alert_wakeup))

	def _wake(self, generation: int, deadline, is_alert_wakeup: bool) -> None:
		with self._lock:
			if self._closed or generation != self._generation:
				return
			self._timer = None
		now = self.now.now()
		elapsed = monotonic() - self._last_tick
		wall_elapsed = (utc(now) - utc(self._last_wall)).total_seconds()
		zone = str(self.alarms.zone_provider())
		if abs(elapsed - wall_elapsed) > 2 or zone != self._last_zone or elapsed > 45:
			self.scheduler.rebuild(self.alarms.events(now, include_recent=True), now,
				scope="personal", preserve_current=True)
		self._last_wall, self._last_tick, self._last_zone = now, monotonic(), zone
		boundary = self._day_boundary
		if boundary is not None and utc(now) >= utc(boundary):
			self.coordinator.renew_day(now)
		delivery_now = timer_delivery_instant(now, deadline) if is_alert_wakeup else now
		self.presenter.present_next(delivery_now)
		self._reschedule()

	def resume(self) -> None:
		if self._closed:
			return
		now = self.now.now()
		reserved = self.coordinator.resume(now)
		self.presenter.present_next(now, reserved=reserved)
		self._reschedule()

	def system_time_changed(self) -> None:
		if not self._closed:
			self.settings.events.publish(SystemTimeChanged(self.now.now()))

	def close(self) -> None:
		with self._lock:
			if self._closed:
				return
			self._closed = True
			self._generation += 1
			if self._timer is not None:
				self._timer.cancel()
				self._timer = None
		for unsubscribe in self._unsubscribers:
			unsubscribe()
		self._unsubscribers.clear()
		self.presenter.close()
		for preview in tuple(self.previews):
			preview.close()
		self.previews.clear()
		self.coordinator.close()
		self.audio.close()
		self.speech.close()
