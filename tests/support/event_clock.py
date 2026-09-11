"""Deterministic clock used by tests that depend on the current time."""

from __future__ import annotations

from awqati.domain import Instant


class EventClock:
	"""A controllable implementation of NowProvider for tests."""

	def __init__(self, current: Instant) -> None:
		self._current = current

	def now(self) -> Instant:
		return self._current

	def set(self, current: Instant) -> None:
		self._current = current
