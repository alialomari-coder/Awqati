"""Shared cancellation primitives for explicit long-running operations."""

from __future__ import annotations

import threading


class OperationCancelled(RuntimeError):
	"""Raised when the user cancels an explicit operation."""


class CancellationToken:
	"""Thread-safe cooperative cancellation token with no platform dependency."""

	def __init__(self) -> None:
		self._event = threading.Event()

	@property
	def cancelled(self) -> bool:
		return self._event.is_set()

	def cancel(self) -> None:
		self._event.set()

	def raise_if_cancelled(self) -> None:
		if self.cancelled:
			raise OperationCancelled("operation cancelled")
