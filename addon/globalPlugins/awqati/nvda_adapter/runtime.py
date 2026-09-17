"""The single NVDA-owned alert runtime and its lifecycle timers."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from threading import RLock

from ..application import (
	AlertCoordinator, AlertPresenter, AlertScheduler, PrayerClockRebuildSource,
	timer_delivery_instant,
)
from ..domain import LocationChanged, SettingsApplied, SystemTimeChanged
from ..domain.alerts import utc
from ..infrastructure import SoundFileService
from .audio_service import AudioService
from .speech_service import SpeechService
from . import compat


class AwqatiRuntime:
	"""Own exactly one scheduler, coordinator and presenter."""

	def __init__(self, settings, now, zones, prayers, *, user_data_root: Path,
			addon_root: Path, language_provider, on_error) -> None:
		self.settings, self.now, self.zones = settings, now, zones
		runtime_settings = lambda: settings.runtime_settings
		self.source = PrayerClockRebuildSource.from_services(runtime_settings, prayers, zones)
		def local_time(instant):
			stored = settings.runtime_settings.location
			zone = zones.get_timezone(stored.location.timezone_id) if stored else timezone.utc
			return instant.value.astimezone(zone)
		self.scheduler = AlertScheduler(now, runtime_settings,
			rebuild_source=self.source, local_time_provider=local_time)
		self.coordinator = AlertCoordinator(self.scheduler, settings.events, self.source)
		self.audio = AudioService(SoundFileService(user_data_root, addon_root),
			dispatch=compat.call_after, diagnostic=on_error)
		self.speech = SpeechService()
		self.presenter = AlertPresenter(self.scheduler, self.audio, self.speech,
			language_provider=language_provider, on_error=on_error)
		self._lock, self._timer, self._generation, self._closed = RLock(), None, 0, False
		self._day_boundary = None
		self._unsubscribers = [
			settings.events.subscribe(SettingsApplied, self._changed),
			settings.events.subscribe(LocationChanged, self._changed),
			settings.events.subscribe(SystemTimeChanged, self._changed),
		]
		instant = now.now()
		self.scheduler.rebuild(self.source(instant, "startup", None), instant)
		self._reschedule()

	def _changed(self, _event) -> None:
		self._reschedule()

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
			deadlines = [value for value in (alert_deadline, self._day_boundary) if value]
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
		self.coordinator.resume(now)
		self.presenter.present_next(now)
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
		self.coordinator.close()
		self.audio.close()
		self.speech.close()
