"""Pure historical calendar arithmetic; no runtime configuration or I/O.

RD 1 is Gregorian 0001-01-01. All conversions share the closed interval
227015..3652059. Gregorian and Julian calendars are explicitly proleptic.
Mathematical reference: Reingold & Dershowitz, Calendrical Calculations,
CALENDRICA 4.0, Islamic/Julian Calendar sections (calendar.l, 2016-12-20):
https://raw.githubusercontent.com/EdReingold/calendar-code2/main/calendar.l
See HISTORICAL_CONVERTER_TASK1_REPORT.md for provenance and limitations.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class HistoricalCalendar(str, Enum):
	HIJRI_IIC = "HIJRI_TABULAR_IIC"
	GREGORIAN = "GREGORIAN_PROLEPTIC"
	JULIAN = "JULIAN_PROLEPTIC"


class ErrorCode(str, Enum):
	UNSUPPORTED_CALENDAR = "unsupported_calendar"
	INVALID_TYPE = "invalid_type"
	INVALID_YEAR = "invalid_year"
	INVALID_MONTH = "invalid_month"
	INVALID_DAY = "invalid_day"
	OUT_OF_RANGE = "out_of_range"


class HistoricalCalendarError(ValueError):
	"""Stable code and field for translation by a future presentation layer."""

	def __init__(self, code: ErrorCode, field: str):
		self.code = code
		self.field = field
		super().__init__(f"{code.value}: {field}")


@dataclass(frozen=True)
class MethodReference:
	identifier: str = "islamic-civil-IIc-v1"
	epoch_rd: int = 227015
	cycle_days: int = 10631
	leap_years: tuple[int, ...] = (2, 5, 7, 10, 13, 16, 18, 21, 24, 26, 29)
	source: str = "Reingold & Dershowitz, Calendrical Calculations / CALENDRICA 4.0"
	qualification: str = "Arithmetic correspondence; local historical dating may differ."


METHOD = MethodReference()
MIN_RD = METHOD.epoch_rd
MAX_RD = date.max.toordinal()


def _calendar(value: HistoricalCalendar) -> HistoricalCalendar:
	# Explicit enum identities prevent accidental reuse of the Umm al-Qura ID.
	if not isinstance(value, HistoricalCalendar):
		raise HistoricalCalendarError(ErrorCode.UNSUPPORTED_CALENDAR, "calendar")
	return value


def _integer(value: int, field: str) -> None:
	# bool is an int subclass but is not a date component.
	if type(value) is not int:
		raise HistoricalCalendarError(ErrorCode.INVALID_TYPE, field)


def _year(calendar: HistoricalCalendar, year: int) -> None:
	_integer(year, "year")
	if year <= 0:
		raise HistoricalCalendarError(ErrorCode.INVALID_YEAR, "year")
	if year > (9666 if calendar is HistoricalCalendar.HIJRI_IIC else 9999):
		raise HistoricalCalendarError(ErrorCode.OUT_OF_RANGE, "year")


def is_leap_year(calendar: HistoricalCalendar, year: int) -> bool:
	"""Calendar rule within the supported year numbers (not day-range validation)."""
	_calendar(calendar)
	_year(calendar, year)
	if calendar is HistoricalCalendar.HIJRI_IIC:
		return (14 + 11 * year) % 30 < 11
	if calendar is HistoricalCalendar.JULIAN:
		return year % 4 == 0
	return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def month_length(calendar: HistoricalCalendar, year: int, month: int) -> int:
	"""Natural month length; final supported months may be only partly convertible."""
	_calendar(calendar)
	_year(calendar, year)
	_integer(month, "month")
	if not 1 <= month <= 12:
		raise HistoricalCalendarError(ErrorCode.INVALID_MONTH, "month")
	if calendar is HistoricalCalendar.HIJRI_IIC:
		return 30 if month % 2 or (month == 12 and is_leap_year(calendar, year)) else 29
	if month == 2:
		return 29 if is_leap_year(calendar, year) else 28
	return 30 if month in (4, 6, 9, 11) else 31


def _raw_rd(calendar: HistoricalCalendar, year: int, month: int, day: int) -> int:
	"""Internal arithmetic on already validated components."""
	if calendar is HistoricalCalendar.GREGORIAN:
		return date(year, month, day).toordinal()
	if calendar is HistoricalCalendar.HIJRI_IIC:
		return MIN_RD - 1 + 354 * (year - 1) + (3 + 11 * year) // 30 + 29 * (month - 1) + month // 2 + day
	# Julian 0001-01-01 has RD -1; accumulate civil months with Julian leap rule.
	return -2 + 365 * (year - 1) + (year - 1) // 4 + sum(
		month_length(calendar, year, m) for m in range(1, month)
	) + day


def _range(rd: int) -> None:
	if not MIN_RD <= rd <= MAX_RD:
		raise HistoricalCalendarError(ErrorCode.OUT_OF_RANGE, "date")


@dataclass(frozen=True)
class HistoricalDate:
	calendar: HistoricalCalendar
	year: int
	month: int
	day: int

	def __post_init__(self) -> None:
		_calendar(self.calendar)
		length = month_length(self.calendar, self.year, self.month)
		_integer(self.day, "day")
		if not 1 <= self.day <= length:
			raise HistoricalCalendarError(ErrorCode.INVALID_DAY, "day")
		_range(_raw_rd(self.calendar, self.year, self.month, self.day))


def to_rd(value: HistoricalDate) -> int:
	if not isinstance(value, HistoricalDate):
		raise HistoricalCalendarError(ErrorCode.INVALID_TYPE, "date")
	return _raw_rd(value.calendar, value.year, value.month, value.day)


def from_rd(rd: int, calendar: HistoricalCalendar) -> HistoricalDate:
	_calendar(calendar)
	_integer(rd, "rd")
	_range(rd)
	if calendar is HistoricalCalendar.GREGORIAN:
		civil = date.fromordinal(rd)
		return HistoricalDate(calendar, civil.year, civil.month, civil.day)
	if calendar is HistoricalCalendar.HIJRI_IIC:
		year = (30 * (rd - MIN_RD) + 10646) // 10631
	else:
		# Positive Julian years, including the last day of each four-year cycle.
		year = (4 * (rd + 1) + 1464) // 1461
	remaining = rd - _raw_rd(calendar, year, 1, 1)
	month = 1
	while remaining >= month_length(calendar, year, month):
		remaining -= month_length(calendar, year, month)
		month += 1
	return HistoricalDate(calendar, year, month, remaining + 1)


@dataclass(frozen=True)
class ConversionResult:
	source: HistoricalDate
	target: HistoricalDate
	rd: int
	method: MethodReference = METHOD

	@property
	def early_islamic_proleptic(self) -> bool:
		"""Lets a future UI qualify correspondences in Hijri years 1 through 9."""
		return from_rd(self.rd, HistoricalCalendar.HIJRI_IIC).year < 10


def convert(source: HistoricalCalendar, target: HistoricalCalendar, *, year: int, month: int, day: int) -> ConversionResult:
	"""Validate and convert directly in any of the six directions (or identity).

	Components must be Python integers. Text parsing belongs to the calling layer.
	No calendar switch, user correction, or normalization is performed.
	"""
	_calendar(source)
	_calendar(target)
	original = HistoricalDate(source, year, month, day)
	rd = to_rd(original)
	return ConversionResult(original, from_rd(rd, target), rd)
