"""Serialize alert audio and speech using the scheduler's single queue."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Callable, Protocol

from ..domain import AlertAction, AlertEvent, AlertEventType
from .alert_formatters import format_adhkar_alert, format_clock_alert, format_prayer_alert


@dataclass(frozen=True, slots=True)
class OutputResult:
	"""Final state reported by an asynchronous output adapter."""

	started: bool
	completed: bool
	cancelled: bool = False
	error: Exception | None = None


class AudioOutput(Protocol):
	def play(self, event: AlertEvent, on_started: Callable[[], None],
			on_finished: Callable[[OutputResult], None]) -> bool:
		...

	def cancel(self) -> None:
		...


class SpeechOutput(Protocol):
	def speak(self, text: str, on_started: Callable[[], None],
			on_finished: Callable[[OutputResult], None]) -> bool:
		...

	def cancel(self) -> None:
		...


def format_alert_message(event: AlertEvent, language: str) -> str:
	"""Route an event to its existing formatter without duplicating templates."""
	if event.event_type is AlertEventType.COUNTDOWN:
		return ("انتهى مؤقت {name}" if language.startswith("ar") else "Timer {name} finished.").format(name=event.metadata["name"])
	if event.event_type is AlertEventType.PERSONAL_ALARM:
		return event.metadata["name"]
	if event.event_type is AlertEventType.CLOCK:
		return format_clock_alert(event, language)
	if event.event_type in {
		AlertEventType.MORNING_ADHKAR,
		AlertEventType.EVENING_ADHKAR,
		AlertEventType.FRIDAY_HOUR,
		AlertEventType.DAILY_WIRD,
		AlertEventType.RECURRING_DHIKR,
	}:
		return format_adhkar_alert(event, language)
	return format_prayer_alert(event, language)


class AlertPresenter:
	"""Own the one active presentation lease; Scheduler owns all waiting events."""

	def __init__(self, scheduler, audio: AudioOutput, speech: SpeechOutput, *,
			language_provider: Callable[[], str] = lambda: "ar",
			message_formatter: Callable[[AlertEvent, str], str] = format_alert_message,
			on_error: Callable[[Exception], None] | None = None,
			on_claim=None, on_finish=None) -> None:
		self._scheduler = scheduler
		self._audio = audio
		self._speech = speech
		self._language_provider = language_provider
		self._format = message_formatter
		self._on_error = on_error or (lambda error: None)
		self._lock = RLock()
		self._event: AlertEvent | None = None
		self._message = ""
		self._phase = 0
		self._presented = False
		self._last_event: AlertEvent | None = None
		self._last_message = ""
		self._closed = False
		self._on_claim = on_claim or (lambda event: None)
		self._on_finish = on_finish or (lambda event, outcome: None)
		self._alarm_deadline = None
		self._personal_audio_attempted = False

	@property
	def current(self) -> AlertEvent | None:
		with self._lock:
			return self._event

	def present_next(self, now=None, *, reserved=None) -> bool:
		"""Claim and start the next still-valid event, if no lease is active."""
		with self._lock:
			if self._closed:
				return False
			if self._event is not None:
				if self._event.event_type is AlertEventType.COUNTDOWN:
					pending = self._scheduler.next_due(now)
					if not self._scheduler._is_enabled(self._event) or self._scheduler._quiet(self._event, now or self._scheduler._now()):
						self.cancel_current(outcome="suppressed")
					elif pending and pending.priority < self._event.priority:
						interrupted = self._event
						self.cancel_current(outcome="interruptedByHigherPriority")
						# Preserve the name announcement in the central queue. Do not
						# replay a custom WAV or reserve another repetition attempt.
						self._scheduler.schedule(AlertEvent(interrupted.event_id + ".deferred",
							AlertEventType.COUNTDOWN, interrupted.scheduled_at,
							action=AlertAction.SPEECH, scope=interrupted.scope,
							source=interrupted.source, metadata=interrupted.metadata))
					elif self._alarm_deadline is not None and monotonic() >= self._alarm_deadline:
						self.cancel_current(outcome="durationElapsed")
			if self._event is not None:
				if self._event.event_type is AlertEventType.PERSONAL_ALARM:
					next_event = self._scheduler.next_due(now)
					if next_event and next_event.priority < self._event.priority:
						prayer = next_event.event_type in {
							AlertEventType.PRAYER_TIME, AlertEventType.PRAYER_PRE_ALERT,
							AlertEventType.IQAMA_PRE_ALERT, AlertEventType.PRAYER_POST_ALERT,
						}
						self.cancel_current(outcome="interruptedByPrayer" if prayer else "interruptedByTimeAlert")
					elif self._scheduler.current is None or not self._scheduler._is_enabled(self._event) or self._scheduler._quiet(self._event, now or self._scheduler._now()):
						self.cancel_current(outcome="suppressed")
					elif self._alarm_deadline is not None and monotonic() >= self._alarm_deadline:
						self.cancel_current(outcome="durationElapsed")
				if self._event is not None:
					return False
			event = reserved or self._scheduler.claim_for_presentation(now)
			if reserved is not None and self._scheduler.current is not reserved:
				return False
			if event is None:
				return False
			self._event = event
			self._phase += 1
			token = self._phase
			self._presented = False
			self._personal_audio_attempted = False
			self._alarm_deadline = (monotonic() + event.metadata["duration"] if event.event_type is AlertEventType.PERSONAL_ALARM
				else monotonic() + 30 if event.event_type is AlertEventType.COUNTDOWN else None)
			try:
				self._on_claim(event)
				self._message = self._format(event, self._language_provider())
			except Exception as error:
				self._report(error)
				self._finish(token)
				return False
		action = event.action
		if action is AlertAction.SILENT:
			self._finish(token)
		elif action is AlertAction.SPEECH:
			self._start_speech(token)
		elif event.event_type is AlertEventType.PERSONAL_ALARM and action is AlertAction.SOUND_AND_SPEECH:
			self._start_speech(token)
		elif action in (AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH):
			self._start_audio(token, speech_after=action is AlertAction.SOUND_AND_SPEECH)
		else:
			self._report(ValueError("unsupported alert action"))
			self._finish(token)
		return True

	def _start_audio(self, token: int, *, speech_after: bool) -> None:
		self._personal_audio_attempted = True
		try:
			accepted = self._audio.play(
				self._event,
				lambda: self._mark_started(token),
				lambda result: self._audio_finished(token, speech_after, result),
			)
		except Exception as error:
			self._report(error)
			accepted = False
		if not accepted:
			self._start_speech(token)

	def _audio_finished(self, token: int, speech_after: bool, result: OutputResult) -> None:
		with self._lock:
			if not self._active(token):
				return
		if result.error is not None:
			self._report(result.error)
		if result.completed and result.started:
			if speech_after:
				self._start_speech(token)
			else:
				self._finish(token)
		elif not result.cancelled:
			# SOUND also speaks once when no usable output was produced.
			self._start_speech(token)
		else:
			self._finish(token)

	def _start_speech(self, token: int) -> None:
		with self._lock:
			if not self._active(token):
				return
			message = self._message
		try:
			accepted = self._speech.speak(
				message,
				lambda: self._mark_started(token),
				lambda result: self._speech_finished(token, result),
			)
		except Exception as error:
			self._report(error)
			accepted = False
		if not accepted:
			self._finish(token)

	def _speech_finished(self, token: int, result: OutputResult) -> None:
		with self._lock:
			if not self._active(token):
				return
		if result.error is not None:
			self._report(result.error)
		if self._event.event_type is AlertEventType.PERSONAL_ALARM:
			if self._event.action is AlertAction.SOUND_AND_SPEECH and not self._personal_audio_attempted:
				self._start_audio(token, speech_after=False)
			return  # Speech-only cycles remain controllable until duration expires.
		self._finish(token)

	def _mark_started(self, token: int) -> None:
		with self._lock:
			if not self._active(token) or self._presented:
				return
			event_id = self._event.event_id
			if self._scheduler.mark_presented(event_id):
				self._presented = True
				self._last_event = self._event
				self._last_message = self._message

	@property
	def last_presented(self) -> AlertEvent | None:
		with self._lock:
			return self._last_event

	def replay_last(self) -> bool:
		"""Repeat Awqati's last actually-started alert as a manual request."""
		with self._lock:
			if self._closed or self._event is not None or self._last_event is None:
				return False
			event, message = self._last_event, self._last_message
		def finished(_result):
			return None
		if event.action in (AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH):
			try:
				accepted = self._audio.play(event, lambda: None,
					lambda result: self._speech.speak(message, lambda: None, finished)
					if event.action is AlertAction.SOUND_AND_SPEECH and result.completed else None)
			except Exception as error:
				self._report(error)
				accepted = False
			if accepted:
				return True
		return self._speech.speak(message, lambda: None, finished)

	def _finish(self, token: int) -> None:
		with self._lock:
			if not self._active(token):
				return
			event_id = self._event.event_id
			try:
				self._on_finish(self._event, "completed")
			except Exception as error:
				self._report(error)
			# mark_presented occurs only at actual output start. Avoid acknowledging
			# a formatter or adapter failure that produced nothing.
			self._scheduler.complete(event_id, presented=False)
			self._event = None
			self._message = ""
			self._presented = False
		if not self._closed:
			self.present_next()

	def cancel_current(self, *, outcome="stopped") -> bool:
		with self._lock:
			if self._event is None:
				return False
			event_id = self._event.event_id
			try:
				self._on_finish(self._event, outcome)
			except Exception as error:
				self._report(error)
			self._phase += 1
			self._event = None
			self._message = ""
			self._presented = False
		self._audio.cancel()
		self._speech.cancel()
		return self._scheduler.cancel(event_id)

	def close(self) -> None:
		with self._lock:
			if self._closed:
				return
			self._closed = True
		self.cancel_current()
		self._audio.cancel()
		self._speech.cancel()
		self._last_event = None
		self._last_message = ""

	def _active(self, token: int) -> bool:
		return not self._closed and self._event is not None and token == self._phase

	def _report(self, error: Exception) -> None:
		try:
			self._on_error(error)
		except Exception:
			pass
