"""Language-neutral calendar identities, values, and pure calendar algorithms."""

from __future__ import annotations

import calendar as _gregorian_rules
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


class CalendarId(Enum):
	GREGORIAN = "GREGORIAN"
	HIJRI_UMM_AL_QURA = "HIJRI_UMM_AL_QURA"
	SAUDI_SOLAR_HIJRI = "SAUDI_SOLAR_HIJRI"
	PERSIAN_SOLAR_HIJRI = "PERSIAN_SOLAR_HIJRI"
	AFGHAN_SOLAR_HIJRI = "AFGHAN_SOLAR_HIJRI"


class DateFormat(Enum):
	DOUBLE = "double"
	FULL = "full"
	MODERATE = "moderate"
	SHORT = "short"


class PrimaryCalendar(Enum):
	HIJRI_UMM_AL_QURA = CalendarId.HIJRI_UMM_AL_QURA.value
	GREGORIAN = CalendarId.GREGORIAN.value

	@property
	def calendar_id(self) -> CalendarId:
		return CalendarId(self.value)


class CalendarError(ValueError):
	"""Base error for a calendar request that cannot be represented."""


class CalendarOutOfRangeError(CalendarError):
	"""The requested date is outside a provider's documented range."""


class UnsupportedCalendarError(CalendarError):
	"""No explicitly registered provider owns the requested identity."""


class InvalidHijriAdjustmentError(CalendarError):
	"""The visible lunar correction is not an integer from -2 through +2."""


@dataclass(frozen=True, slots=True)
class CalendarDate:
	year: int
	month: int
	day: int
	calendar_id: CalendarId

	def __post_init__(self) -> None:
		for field_name in ("year", "month", "day"):
			value = getattr(self, field_name)
			if not isinstance(value, int) or isinstance(value, bool):
				raise TypeError(f"{field_name} must be an integer")
		if self.year < 1:
			raise ValueError("year must be positive")
		if not 1 <= self.month <= 12:
			raise ValueError("month must be from 1 through 12")
		if self.day < 1:
			raise ValueError("day must be positive")
		if not isinstance(self.calendar_id, CalendarId):
			raise TypeError("calendar_id must be a CalendarId")


@dataclass(frozen=True, slots=True)
class CalendarReading:
	"""Dates derived from one unchanged local civil day."""

	civil_date: date
	weekday: int
	selected: CalendarDate
	gregorian: CalendarDate
	lunar_base: CalendarDate
	lunar_visible: CalendarDate
	hijri_adjustment: int


class GregorianProvider:
	calendar_id = CalendarId.GREGORIAN

	def from_gregorian(self, value: date) -> CalendarDate:
		_require_date(value)
		return CalendarDate(value.year, value.month, value.day, self.calendar_id)

	def to_gregorian(self, value: CalendarDate) -> date:
		_require_identity(value, self.calendar_id)
		try:
			return date(value.year, value.month, value.day)
		except ValueError as error:
			raise CalendarOutOfRangeError(str(error)) from error


class SaudiSolarHijriProvider:
	calendar_id = CalendarId.SAUDI_SOLAR_HIJRI
	saudi_solar_hijri_algorithm_version = "awqati-saudi-solar-1-mizan-23-september-v1"

	@staticmethod
	def is_leap_year(year: int) -> bool:
		return _gregorian_rules.isleap(year + 622)

	def month_length(self, year: int, month: int) -> int:
		if not 1 <= month <= 12:
			raise ValueError("month must be from 1 through 12")
		if month <= 5:
			return 30
		if month == 6:
			return 30 if self.is_leap_year(year) else 29
		return 31

	def from_gregorian(self, value: date) -> CalendarDate:
		_require_date(value)
		year = value.year - (621 if (value.month, value.day) >= (9, 23) else 622)
		try:
			start = date(year + 621, 9, 23)
		except ValueError as error:
			raise CalendarOutOfRangeError("Saudi Solar Hijri date is not representable") from error
		return _from_offset(value, start, year, self)

	def to_gregorian(self, value: CalendarDate) -> date:
		_require_identity(value, self.calendar_id)
		_validate_day(value, self.month_length(value.year, value.month))
		try:
			return date(value.year + 621, 9, 23) + timedelta(
				days=sum(self.month_length(value.year, month) for month in range(1, value.month)) + value.day - 1)
		except (OverflowError, ValueError) as error:
			raise CalendarOutOfRangeError("Saudi Solar Hijri date is not representable") from error


class PersianSolarHijriProvider:
	calendar_id = CalendarId.PERSIAN_SOLAR_HIJRI
	persian_solar_hijri_algorithm_version = "icu-78.3-persian-33-year-1304-1468"
	MIN_YEAR = 1304
	MAX_YEAR = 1468
	_PERSIAN_EPOCH = 1948320
	_JDN_ORDINAL_OFFSET = 1721425

	@staticmethod
	def is_leap_year(year: int) -> bool:
		PersianSolarHijriProvider._require_year(year)
		return (year * 25 + 11) % 33 < 8

	@classmethod
	def _start(cls, year: int) -> date:
		cls._require_year(year)
		first_julian_of_year = 365 * (year - 1) + (8 * year + 21) // 33
		return date.fromordinal(cls._PERSIAN_EPOCH + first_julian_of_year - cls._JDN_ORDINAL_OFFSET)

	@classmethod
	def _require_year(cls, year: int) -> None:
		if not cls.MIN_YEAR <= year <= cls.MAX_YEAR:
			raise CalendarOutOfRangeError("Persian Solar Hijri year must be from 1304 through 1468")

	def month_length(self, year: int, month: int) -> int:
		self._require_year(year)
		if not 1 <= month <= 12:
			raise ValueError("month must be from 1 through 12")
		if month <= 6:
			return 31
		if month <= 11:
			return 30
		return 30 if self.is_leap_year(year) else 29

	def from_gregorian(self, value: date) -> CalendarDate:
		_require_date(value)
		year = value.year - 621
		if year > self.MAX_YEAR or (year == self.MAX_YEAR and value < self._start(year)):
			year -= 1
		elif year >= self.MIN_YEAR and value < self._start(year):
			year -= 1
		self._require_year(year)
		if year == self.MAX_YEAR:
			last = self._start(year) + timedelta(days=365 if self.is_leap_year(year) else 364)
			if value > last:
				raise CalendarOutOfRangeError("date is after Persian Solar Hijri year 1468")
		return _from_offset(value, self._start(year), year, self)

	def to_gregorian(self, value: CalendarDate) -> date:
		_require_identity(value, self.calendar_id)
		self._require_year(value.year)
		_validate_day(value, self.month_length(value.year, value.month))
		return self._start(value.year) + timedelta(
			days=sum(self.month_length(value.year, month) for month in range(1, value.month)) + value.day - 1)


class AfghanSolarHijriProvider:
	calendar_id = CalendarId.AFGHAN_SOLAR_HIJRI
	afghan_solar_hijri_algorithm_version = "undp-unicode-2003-afghanistan-x-plus-621-anchor-1382-v1"

	@staticmethod
	def is_leap_year(year: int) -> bool:
		return _gregorian_rules.isleap(year + 621)

	@classmethod
	def _start(cls, year: int) -> date:
		gregorian_year = year + 621
		return date(gregorian_year, 3, 20 if _gregorian_rules.isleap(gregorian_year) else 21)

	def month_length(self, year: int, month: int) -> int:
		if not 1 <= month <= 12:
			raise ValueError("month must be from 1 through 12")
		if month <= 6:
			return 31
		if month <= 11:
			return 30
		return 30 if self.is_leap_year(year) else 29

	def from_gregorian(self, value: date) -> CalendarDate:
		_require_date(value)
		year = value.year - 621
		if value < self._start(year):
			year -= 1
		if year < 1:
			raise CalendarOutOfRangeError("Afghan Solar Hijri year is not representable")
		return _from_offset(value, self._start(year), year, self)

	def to_gregorian(self, value: CalendarDate) -> date:
		_require_identity(value, self.calendar_id)
		_validate_day(value, self.month_length(value.year, value.month))
		try:
			return self._start(value.year) + timedelta(
				days=sum(self.month_length(value.year, month) for month in range(1, value.month)) + value.day - 1)
		except (OverflowError, ValueError) as error:
			raise CalendarOutOfRangeError("Afghan Solar Hijri date is not representable") from error


def _require_date(value: date) -> None:
	if not isinstance(value, date) or isinstance(value, datetime):
		raise TypeError("value must be a Gregorian date")


def _require_identity(value: CalendarDate, identity: CalendarId) -> None:
	if not isinstance(value, CalendarDate):
		raise TypeError("value must be a CalendarDate")
	if value.calendar_id is not identity:
		raise ValueError(f"expected {identity.value} date")


def _validate_day(value: CalendarDate, month_length: int) -> None:
	if value.day > month_length:
		raise ValueError("day exceeds the selected calendar month")


def _from_offset(value: date, start: date, year: int, provider) -> CalendarDate:
	offset = (value - start).days
	month = 1
	while offset >= provider.month_length(year, month):
		offset -= provider.month_length(year, month)
		month += 1
	return CalendarDate(year, month, offset + 1, provider.calendar_id)
