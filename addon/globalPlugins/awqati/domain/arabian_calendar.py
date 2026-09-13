"""Language-neutral models for the versioned Arabian calendar data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .astronomy import AstronomyReading


class SuhailCycleType(Enum):
	COMMON = "common"
	LEAP = "leap"


@dataclass(frozen=True, slots=True)
class MonthDay:
	month: int
	day: int


@dataclass(frozen=True, slots=True)
class ArabianSaying:
	id: str
	text: str


@dataclass(frozen=True, slots=True)
class ArabianMansion:
	name: str
	name_origin: str | None
	description: str | None


@dataclass(frozen=True, slots=True)
class ArabianNaw:
	description: str


@dataclass(frozen=True, slots=True)
class ArabianTalaa:
	id: str
	order: int
	name: str
	aliases: tuple[str, ...]
	start: MonthDay
	end: MonthDay
	common_length: int
	leap_length: int
	season_id: str
	folk_subdivision: str | None
	heritage_notes: tuple[str, ...]
	sayings: tuple[ArabianSaying, ...]
	overlap_period_ids: tuple[str, ...]
	source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArabianSeason:
	id: str
	name: str
	start: MonthDay
	end: MonthDay
	common_length: int
	leap_length: int
	notes: tuple[str, ...]
	talaa_ids: tuple[str, ...]
	source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArabianOverlapPeriod:
	id: str
	name: str
	start: MonthDay
	end: MonthDay
	description: str
	talaa_ids: tuple[str, ...]
	source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArabianStartEvent:
	id: str
	type: str
	text: str


@dataclass(frozen=True, slots=True)
class ArabianCalendarReading:
	local_date: date
	cycle_anchor: date
	cycle_type: SuhailCycleType
	cycle_length: int
	suhail_day: int
	days_remaining: int
	talaa_day: int
	talaa_length: int
	season_day: int
	season_length: int
	folk_subdivision: str | None
	talaa: ArabianTalaa
	mansion: ArabianMansion | None
	naw: ArabianNaw | None
	season: ArabianSeason
	overlapping_periods: tuple[ArabianOverlapPeriod, ...]
	short_saying: ArabianSaying | None
	start_events: tuple[ArabianStartEvent, ...]
	data_version: str


@dataclass(frozen=True, slots=True)
class DailyInfoReading:
	"""Keep scientific astronomy and heritage data as separate results."""

	scientific: AstronomyReading
	heritage: ArabianCalendarReading | None
