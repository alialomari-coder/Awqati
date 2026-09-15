"""NVDA speech adapter with explicit start, completion, and cancellation."""

from __future__ import annotations

from threading import RLock
from typing import Callable

from ..application.alert_presenter import OutputResult


class SpeechService:
	"""Speak one message and learn its lifecycle from NVDA speech callbacks."""

	def __init__(self, *, speak_sequence=None, callback_command=None,
			cancel_speech=None, speech_canceled=None) -> None:
		self._speak_sequence = speak_sequence
		self._callback_command = callback_command
		self._cancel_speech = cancel_speech
		self._speech_canceled = speech_canceled
		self._lock = RLock()
		self._generation = 0
		self._busy = False
		self._started = False
		self._cancel_listener = None

	@property
	def busy(self) -> bool:
		with self._lock:
			return self._busy

	def speak(self, text: str, on_started: Callable[[], None],
			on_finished: Callable[[OutputResult], None]) -> bool:
		if not isinstance(text, str) or not text.strip():
			return False
		with self._lock:
			if self._busy:
				return False
			self._busy = True
			self._started = False
			self._generation += 1
			generation = self._generation
		try:
			speak_sequence, command, canceled = self._apis()
			listener = lambda: self._reached_cancel(generation, on_finished)
			with self._lock:
				self._cancel_listener = (canceled, listener) if canceled is not None else None
			if canceled is not None:
				canceled.register(listener)
			# OneCore can stall on an index-only prefix. Put the start callback
			# after the first spoken word so it proves that speech was reached.
			first, separator, remainder = text.strip().partition(" ")
			sequence = [
				first,
				command(lambda: self._reached_start(generation, on_started), name="Awqati alert start"),
			]
			if separator and remainder:
				sequence.append(remainder)
			sequence.append(command(
				lambda: self._reached_end(generation, on_finished), name="Awqati alert complete",
			))
			speak_sequence(sequence)
		except Exception as error:
			self._end_generation(generation)
			on_finished(OutputResult(False, False, False, error))
			return False
		return True

	def _apis(self):
		if self._speak_sequence is not None and self._callback_command is not None:
			return self._speak_sequence, self._callback_command, self._speech_canceled
		import speech
		from speech.commands import CallbackCommand
		from speech.extensions import speechCanceled
		return speech.speak, CallbackCommand, speechCanceled

	def _reached_start(self, generation: int, callback) -> None:
		with self._lock:
			if generation != self._generation or not self._busy or self._started:
				return
			self._started = True
		callback()

	def _reached_end(self, generation: int, callback) -> None:
		with self._lock:
			if generation != self._generation or not self._busy:
				return
			started = self._started
		self._end_generation(generation)
		callback(OutputResult(started, True))

	def _reached_cancel(self, generation: int, callback) -> None:
		with self._lock:
			if generation != self._generation or not self._busy:
				return
			started = self._started
		self._end_generation(generation)
		callback(OutputResult(started, False, cancelled=True))

	def _end_generation(self, generation: int) -> None:
		with self._lock:
			if generation != self._generation:
				return
			listener = self._cancel_listener
			self._cancel_listener = None
			self._busy = False
			self._started = False
		if listener is not None:
			try: listener[0].unregister(listener[1])
			except Exception: pass

	def cancel(self) -> None:
		with self._lock:
			if not self._busy:
				return
			generation = self._generation
		self._end_generation(generation)
		with self._lock:
			self._generation += 1
		try:
			cancel = self._cancel_speech
			if cancel is None:
				import speech
				cancel = speech.cancelSpeech
			cancel()
		except Exception:
			pass

	close = cancel
