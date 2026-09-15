"""Serialize alert audio and speech using the scheduler's single queue."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
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
			on_error: Callable[[Exception], None] | None = None) -> None:
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
		self._closed = False

	@property
	def current(self) -> AlertEvent | None:
		with self._lock:
			return self._event

	def present_next(self, now=None) -> bool:
		"""Claim and start the next still-valid event, if no lease is active."""
		with self._lock:
			if self._closed or self._event is not None:
				return False
			event = self._scheduler.claim_for_presentation(now)
			if event is None:
				return False
			self._event = event
			self._phase += 1
			token = self._phase
			self._presented = False
			try:
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
		elif action in (AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH):
			self._start_audio(token, speech_after=action is AlertAction.SOUND_AND_SPEECH)
		else:
			self._report(ValueError("unsupported alert action"))
			self._finish(token)
		return True

	def _start_audio(self, token: int, *, speech_after: bool) -> None:
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
		self._finish(token)

	def _mark_started(self, token: int) -> None:
		with self._lock:
			if not self._active(token) or self._presented:
				return
			event_id = self._event.event_id
			if self._scheduler.mark_presented(event_id):
				self._presented = True

	def _finish(self, token: int) -> None:
		with self._lock:
			if not self._active(token):
				return
			event_id = self._event.event_id
			# mark_presented occurs only at actual output start. Avoid acknowledging
			# a formatter or adapter failure that produced nothing.
			self._scheduler.complete(event_id, presented=False)
			self._event = None
			self._message = ""
			self._presented = False
		if not self._closed:
			self.present_next()

	def cancel_current(self) -> bool:
		with self._lock:
			if self._event is None:
				return False
			event_id = self._event.event_id
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

	def _active(self, token: int) -> bool:
		return not self._closed and self._event is not None and token == self._phase

	def _report(self, error: Exception) -> None:
		try:
			self._on_error(error)
		except Exception:
			pass
