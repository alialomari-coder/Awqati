"""Pure, neutral clock readings and formatting options."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class ClockType(Enum):
	ZAWALI = "zawali"
	GHURUBI = "ghurubi"


class HourSystem(Enum):
	TWELVE = 12
	TWENTY_FOUR = 24


class TimeRepresentation(Enum):
	NUMERIC = "numeric"
	WORDS = "words"


class AnnouncementStyle(Enum):
	DOUBLE = "double"
	FULL = "full"
	MODERATE = "moderate"
	SHORT = "short"


@dataclass(frozen=True, slots=True)
class ClockFormatOptions:
	hour_system: HourSystem = HourSystem.TWELVE
	show_seconds: bool = False
	speak_zero_minute: bool = False
	style: AnnouncementStyle = AnnouncementStyle.FULL

	def __post_init__(self) -> None:
		if not isinstance(self.hour_system, HourSystem):
			raise TypeError("hour_system must be an HourSystem")
		if not isinstance(self.show_seconds, bool):
			raise TypeError("show_seconds must be boolean")
		if not isinstance(self.speak_zero_minute, bool):
			raise TypeError("speak_zero_minute must be boolean")
		if not isinstance(self.style, AnnouncementStyle):
			raise TypeError("style must be an AnnouncementStyle")


@dataclass(frozen=True, slots=True)
class ClockReading:
	"""One civil instant and its real elapsed duration from the selected Maghrib."""

	zawali: datetime
	ghurubi_elapsed: timedelta
	maghrib_reference: datetime

	def __post_init__(self) -> None:
		for field_name in ("zawali", "maghrib_reference"):
			value = getattr(self, field_name)
			if value.tzinfo is None or value.utcoffset() is None:
				raise ValueError(f"{field_name} must be timezone-aware")
		if self.ghurubi_elapsed < timedelta(0):
			raise ValueError("ghurubi_elapsed must not be negative")
