"""Race-safe multi-press recognition shared by all Awqati scripts."""

from __future__ import annotations

from threading import RLock
from typing import Callable


class MultiPressDispatcher:
	"""Delay dispatch until the press sequence is unambiguous.

	``schedule`` must return an object with ``cancel``.  The generation token is
	+kept even after cancellation because a platform timer may already be queued.
	"""

	def __init__(self, schedule: Callable[[int, Callable[[], None]], object], timeout_ms: int = 450) -> None:
		self._schedule = schedule
		self._timeout_ms = timeout_ms
		self._lock = RLock()
		self._generation = 0
		self._command: str | None = None
		self._count = 0
		self._maximum = 0
		self._handlers: tuple[Callable[[], None], ...] = ()
		self._timer = None
		self._closed = False

	def press(self, command: str, handlers: tuple[Callable[[], None], ...]) -> None:
		if len(handlers) < 2:
			raise ValueError("a multi-press command requires at least two handlers")
		callback = None
		with self._lock:
			if self._closed:
				return
			if self._command != command:
				self._cancel_locked()
				self._command, self._count = command, 0
			self._handlers, self._maximum = handlers, len(handlers)
			self._count = min(self._count + 1, self._maximum)
			self._generation += 1
			generation = self._generation
			self._cancel_timer_locked()
			if self._count == self._maximum:
				callback = self._take_locked(generation)
			else:
				self._timer = self._schedule(self._timeout_ms, lambda: self._expired(generation))
		if callback is not None:
			callback()

	def _expired(self, generation: int) -> None:
		callback = None
		with self._lock:
			if not self._closed and generation == self._generation:
				callback = self._take_locked(generation)
		if callback is not None:
			callback()

	def _take_locked(self, generation: int):
		if generation != self._generation or not self._handlers or not self._count:
			return None
		callback = self._handlers[self._count - 1]
		self._cancel_timer_locked()
		self._command, self._count, self._handlers = None, 0, ()
		return callback

	def _cancel_timer_locked(self) -> None:
		if self._timer is not None:
			try:
				self._timer.cancel()
			except Exception:
				pass
			self._timer = None

	def _cancel_locked(self) -> None:
		self._generation += 1
		self._cancel_timer_locked()
		self._command, self._count, self._handlers = None, 0, ()

	def close(self) -> None:
		with self._lock:
			if self._closed:
				return
			self._closed = True
			self._cancel_locked()
