"""Small shared models needed at Awqati's architectural boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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
class Coordinates:
	"""A validated latitude/longitude pair without platform-specific details."""

	latitude: float
	longitude: float

	def __post_init__(self) -> None:
		if not math.isfinite(self.latitude) or not -90.0 <= self.latitude <= 90.0:
			raise ValueError("latitude must be finite and between -90 and 90")
		if not math.isfinite(self.longitude) or not -180.0 <= self.longitude <= 180.0:
			raise ValueError("longitude must be finite and between -180 and 180")


class LocationStatus(Enum):
	"""Typed outcomes exposed by the location use case."""

	ASSIGNED = "assigned"
	UNSET = "unset"
	DETECTION_FAILED = "detectionFailed"


class LocationDetectionFailure(Enum):
	"""Neutral reasons why an explicit platform-location attempt failed."""

	DENIED = "denied"
	UNAVAILABLE = "unavailable"
	TIMEOUT = "timeout"
	API_ERROR = "apiError"
	INVALID_COORDINATES = "invalidCoordinates"


@dataclass(frozen=True, slots=True)
class LocationState:
	"""The currently effective location, which is never a failed attempt."""

	status: LocationStatus
	location: Location | None = None

	def __post_init__(self) -> None:
		if self.status is LocationStatus.ASSIGNED and self.location is None:
			raise ValueError("an assigned state requires a location")
		if self.status is not LocationStatus.ASSIGNED and self.location is not None:
			raise ValueError("only an assigned state may contain a location")
		if self.status is LocationStatus.DETECTION_FAILED:
			raise ValueError("a failed detection is an attempt result, not current state")


@dataclass(frozen=True, slots=True)
class LocationDetectionResult:
	"""Result of one explicit detection while preserving the effective state."""

	status: LocationStatus
	location: Location | None = None
	failure: LocationDetectionFailure | None = None

	def __post_init__(self) -> None:
		if self.status is LocationStatus.ASSIGNED:
			if self.location is None or self.failure is not None:
				raise ValueError("a successful detection requires only a location")
		elif self.status is LocationStatus.DETECTION_FAILED:
			if self.failure is None:
				raise ValueError("a failed detection requires a reason")
		else:
			raise ValueError("detection results are assigned or failed")


@dataclass(frozen=True, slots=True)
class DomainEvent:
	"""Base value for a domain occurrence without defining future event types."""

	occurred_at: Instant


@dataclass(frozen=True, slots=True)
class LocationChanged(DomainEvent):
	"""The one neutral event emitted after the effective location changes."""

	previous_location: Location | None
	current_location: Location | None


@dataclass(frozen=True, slots=True)
class SettingsApplied(DomainEvent):
	"""Published after one validated settings graph becomes the runtime state."""

	schema_version: int
	automatic_alerts_rebuild_from: Instant | None = None


@dataclass(frozen=True, slots=True)
class SystemTimeChanged(DomainEvent):
	"""Contract for a future platform time-change monitor."""
