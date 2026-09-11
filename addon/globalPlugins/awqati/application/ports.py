"""External capabilities currently required by the application layer."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import Instant


@runtime_checkable
class NowProvider(Protocol):
	"""Provide the current instant without binding application code to a clock."""

	def now(self) -> Instant:
		"""Return the current instant."""
		...
