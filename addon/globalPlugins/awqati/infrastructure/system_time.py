"""System-backed implementation of the current-time boundary."""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain import Instant


class SystemNowProvider:
	"""Read the host clock only at the infrastructure boundary."""

	def now(self) -> Instant:
		return Instant(datetime.now(timezone.utc))
