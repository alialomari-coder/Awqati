"""Small shared models needed at Awqati's architectural boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True, slots=True)
class Instant:
	"""An unambiguous point in time represented by an aware datetime."""

	value: datetime

	def __post_init__(self) -> None:
		if self.value.tzinfo is None or self.value.utcoffset() is None:
			raise ValueError("Instant requires a timezone-aware datetime")


@dataclass(frozen=True, slots=True)
class Location:
	"""A platform-neutral location accepted by Awqati's core."""

	location_id: str
	name: str
	latitude: float
	longitude: float
	timezone_id: str

	def __post_init__(self) -> None:
		for field_name in ("location_id", "name", "timezone_id"):
			if not getattr(self, field_name).strip():
				raise ValueError(f"{field_name} must not be empty")
		if not math.isfinite(self.latitude) or not -90.0 <= self.latitude <= 90.0:
			raise ValueError("latitude must be finite and between -90 and 90")
		if not math.isfinite(self.longitude) or not -180.0 <= self.longitude <= 180.0:
			raise ValueError("longitude must be finite and between -180 and 180")


@dataclass(frozen=True, slots=True)
class DomainEvent:
	"""Base value for a domain occurrence without defining future event types."""

	occurred_at: Instant
