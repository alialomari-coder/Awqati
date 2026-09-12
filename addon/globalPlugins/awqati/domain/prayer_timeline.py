"""Pure timeline concepts derived from calculated prayer times."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .prayer import PrayerCalculationMetadata, PrayerTimes


class PrayerEventKind(Enum):
	"""Semantic event category, independent of translated display names."""

	PRAYER = "prayer"
	TIME = "time"


class PrayerEventName(Enum):
	FAJR = "fajr"
	SUNRISE = "sunrise"
	DHUHR = "dhuhr"
	ASR = "asr"
	MAGHRIB = "maghrib"
	ISHA = "isha"
	MIDNIGHT = "midnight"
	LAST_THIRD = "lastThird"


PRAYER_EVENT_NAMES = frozenset({
	PrayerEventName.FAJR,
	PrayerEventName.DHUHR,
	PrayerEventName.ASR,
	PrayerEventName.MAGHRIB,
	PrayerEventName.ISHA,
})


def _require_aware(value: datetime, field_name: str) -> None:
	if value.tzinfo is None or value.utcoffset() is None:
		raise ValueError(f"{field_name} must be timezone-aware")


def _utc(value: datetime) -> datetime:
	return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PrayerEvent:
	"""One of the eight dated events used by the prayer timeline."""

	name: PrayerEventName
	occurs_at: datetime

	def __post_init__(self) -> None:
		_require_aware(self.occurs_at, "occurs_at")

	@property
	def kind(self) -> PrayerEventKind:
		return PrayerEventKind.PRAYER if self.name in PRAYER_EVENT_NAMES else PrayerEventKind.TIME


@dataclass(frozen=True, slots=True)
class NightTimes:
	"""Night divisions between local Maghrib and the explicitly supplied next Fajr."""

	midnight: datetime
	last_third_start: datetime

	def __post_init__(self) -> None:
		_require_aware(self.midnight, "midnight")
		_require_aware(self.last_third_start, "last_third_start")


def calculate_night_times(maghrib: datetime, next_fajr: datetime) -> NightTimes:
	"""Calculate half and two-thirds of the actual elapsed night duration."""

	_require_aware(maghrib, "maghrib")
	_require_aware(next_fajr, "next_fajr")
	maghrib_utc = _utc(maghrib)
	next_fajr_utc = _utc(next_fajr)
	if next_fajr_utc <= maghrib_utc:
		raise ValueError("next_fajr must be after maghrib")
	duration = next_fajr_utc - maghrib_utc
	return NightTimes(
		midnight=(maghrib_utc + duration / 2).astimezone(maghrib.tzinfo),
		last_third_start=(maghrib_utc + duration * 2 / 3).astimezone(maghrib.tzinfo),
	)


@dataclass(frozen=True, slots=True)
class DailyPrayerTimes:
	"""The eight timezone-aware events belonging to one calculated prayer day."""

	fajr: datetime
	sunrise: datetime
	dhuhr: datetime
	asr: datetime
	maghrib: datetime
	isha: datetime
	midnight: datetime
	last_third_start: datetime
	metadata: PrayerCalculationMetadata

	def __post_init__(self) -> None:
		for field_name in (
			"fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha", "midnight", "last_third_start",
		):
			_require_aware(getattr(self, field_name), field_name)

	@property
	def events(self) -> tuple[PrayerEvent, ...]:
		values = {
			PrayerEventName.FAJR: self.fajr,
			PrayerEventName.SUNRISE: self.sunrise,
			PrayerEventName.DHUHR: self.dhuhr,
			PrayerEventName.ASR: self.asr,
			PrayerEventName.MAGHRIB: self.maghrib,
			PrayerEventName.ISHA: self.isha,
			PrayerEventName.MIDNIGHT: self.midnight,
			PrayerEventName.LAST_THIRD: self.last_third_start,
		}
		return tuple(sorted(
			(PrayerEvent(name, value) for name, value in values.items()),
			key=lambda event: _utc(event.occurs_at),
		))


def complete_prayer_times(prayer_times: PrayerTimes, next_fajr: datetime) -> DailyPrayerTimes:
	"""Add night divisions without calculating or guessing the next day's context."""

	night = calculate_night_times(prayer_times.maghrib, next_fajr)
	return DailyPrayerTimes(
		fajr=prayer_times.fajr,
		sunrise=prayer_times.sunrise,
		dhuhr=prayer_times.dhuhr,
		asr=prayer_times.asr,
		maghrib=prayer_times.maghrib,
		isha=prayer_times.isha,
		midnight=night.midnight,
		last_third_start=night.last_third_start,
		metadata=prayer_times.metadata,
	)
