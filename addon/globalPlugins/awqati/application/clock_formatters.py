"""Arabic and English clock formatting independent from NVDA."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from ..domain import (
	AnnouncementStyle,
	ClockFormatOptions,
	ClockReading,
	ClockType,
	HourSystem,
	TimeRepresentation,
)


@runtime_checkable
class ClockFormatter(Protocol):
	"""Language-specific rendering contract kept outside the neutral Domain."""

	language: str
	representation: TimeRepresentation

	def format_time(self, reading: ClockReading, clock_type: ClockType,
			options: ClockFormatOptions) -> str:
		...

	def format_announcement(self, reading: ClockReading, clock_type: ClockType,
			options: ClockFormatOptions, *, ghurubi_formatter: ClockFormatter | None = None,
			ghurubi_options: ClockFormatOptions | None = None) -> str:
		...


class _BaseClockFormatter:
	language: str
	representation: TimeRepresentation

	def format_civil_announcement(self, value: datetime, options: ClockFormatOptions) -> str:
		"""Render civil time without inventing a Maghrib-based reading."""
		if value.tzinfo is None or value.utcoffset() is None:
			raise ValueError("civil time must be timezone-aware")
		return self._single_template(ClockType.ZAWALI, options.style, self._format_zawali(value, options))

	def format_time(self, reading: ClockReading, clock_type: ClockType,
			options: ClockFormatOptions) -> str:
		if not isinstance(clock_type, ClockType):
			raise TypeError("clock_type must be a ClockType")
		if clock_type is ClockType.ZAWALI:
			return self._format_zawali(reading.zawali, options)
		return self._format_ghurubi(reading.ghurubi_elapsed, options)

	def format_announcement(self, reading: ClockReading, clock_type: ClockType,
			options: ClockFormatOptions, *, ghurubi_formatter: ClockFormatter | None = None,
			ghurubi_options: ClockFormatOptions | None = None) -> str:
		if options.style is AnnouncementStyle.DOUBLE:
			if clock_type is not ClockType.ZAWALI:
				raise ValueError("DOUBLE is not valid for standalone Ghurubi time")
			if ghurubi_formatter is None or ghurubi_options is None:
				raise ValueError("DOUBLE requires explicit Ghurubi formatter and options")
			if ghurubi_formatter.language != self.language:
				raise ValueError("DOUBLE formatters must use the same language")
			zawali = self.format_time(reading, ClockType.ZAWALI, options)
			ghurubi = ghurubi_formatter.format_time(reading, ClockType.GHURUBI, ghurubi_options)
			return self._double_template(zawali, ghurubi)
		value = self.format_time(reading, clock_type, options)
		return self._single_template(clock_type, options.style, value)

	def _format_zawali(self, value: datetime, options: ClockFormatOptions) -> str:
		raise NotImplementedError

	def _format_ghurubi(self, value: timedelta, options: ClockFormatOptions) -> str:
		raise NotImplementedError

	def _double_template(self, zawali: str, ghurubi: str) -> str:
		raise NotImplementedError

	def _single_template(self, clock_type: ClockType, style: AnnouncementStyle, value: str) -> str:
		raise NotImplementedError


class _ArabicTemplates(_BaseClockFormatter):
	language = "ar"

	def _double_template(self, zawali: str, ghurubi: str) -> str:
		return f"الساعة الآن هي: {zawali} حسب التوقيت الزوالي، {ghurubi} حسب التوقيت الغروبي."

	def _single_template(self, clock_type: ClockType, style: AnnouncementStyle, value: str) -> str:
		if clock_type is ClockType.ZAWALI:
			templates = {
				AnnouncementStyle.FULL: "الساعة الآن هي: {value} حسب التوقيت الزوالي.",
				AnnouncementStyle.MODERATE: "الساعة: {value}.",
				AnnouncementStyle.SHORT: "{value}.",
			}
		else:
			templates = {
				AnnouncementStyle.FULL: "الساعة الغروبية: {value}.",
				AnnouncementStyle.MODERATE: "الغروبي: {value}.",
				AnnouncementStyle.SHORT: "{value}.",
			}
		try:
			return templates[style].format(value=value)
		except KeyError as error:
			raise ValueError("DOUBLE is not valid for standalone Ghurubi time") from error


class _EnglishTemplates(_BaseClockFormatter):
	language = "en"

	def _double_template(self, zawali: str, ghurubi: str) -> str:
		return f"The time now is: {zawali} in Zawali time, {ghurubi} in Ghurubi time."

	def _single_template(self, clock_type: ClockType, style: AnnouncementStyle, value: str) -> str:
		if clock_type is ClockType.ZAWALI:
			templates = {
				AnnouncementStyle.FULL: "The time now is: {value} in Zawali time.",
				AnnouncementStyle.MODERATE: "Time: {value}.",
				AnnouncementStyle.SHORT: "{value}.",
			}
		else:
			templates = {
				AnnouncementStyle.FULL: "Ghurubi time: {value}.",
				AnnouncementStyle.MODERATE: "Ghurubi: {value}.",
				AnnouncementStyle.SHORT: "{value}.",
			}
		try:
			return templates[style].format(value=value)
		except KeyError as error:
			raise ValueError("DOUBLE is not valid for standalone Ghurubi time") from error


class NumericClockFormatter(_BaseClockFormatter):
	"""Return the numeric formatter for an ISO language tag supported in 4.0."""

	representation = TimeRepresentation.NUMERIC

	def __new__(cls, language: str):
		if cls is NumericClockFormatter:
			implementation = {
				"ar": _ArabicNumericClockFormatter,
				"en": _EnglishNumericClockFormatter,
			}.get(language)
			if implementation is None:
				raise ValueError("unsupported clock language")
			return super().__new__(implementation)
		return super().__new__(cls)

	def __init__(self, language: str) -> None:
		if not isinstance(language, str):
			raise TypeError("language must be an ISO language tag")


class _ArabicNumericClockFormatter(NumericClockFormatter, _ArabicTemplates):
	language = "ar"

	def _format_zawali(self, value: datetime, options: ClockFormatOptions) -> str:
		hour = value.hour
		period = _civil_period(hour, "ar")
		if options.hour_system is HourSystem.TWELVE:
			hour = hour % 12 or 12
			suffix = f" {period}"
		else:
			suffix = ""
		return _numeric_civil(hour, value.minute, value.second, options, suffix, arabic=True)

	def _format_ghurubi(self, value: timedelta, options: ClockFormatOptions) -> str:
		hour, minute, second = _elapsed_parts(value)
		if options.hour_system is HourSystem.TWENTY_FOUR:
			return _numeric_elapsed(hour, minute, second, options, arabic=True)
		period = "ليلية" if value < timedelta(hours=12) else "نهارية"
		display_hour = hour % 12 or 12
		parts = [str(display_hour)]
		if minute or options.speak_zero_minute:
			parts.append(_arabic_unit_phrase(minute, "minute", words=False))
		if options.show_seconds:
			parts.append(_arabic_unit_phrase(second, "second", words=False))
		return " و".join(parts) + f"، {period}"


class _EnglishNumericClockFormatter(NumericClockFormatter, _EnglishTemplates):
	language = "en"

	def _format_zawali(self, value: datetime, options: ClockFormatOptions) -> str:
		hour = value.hour
		suffix = ""
		if options.hour_system is HourSystem.TWELVE:
			suffix = " " + _civil_period(hour, "en")
			hour = hour % 12 or 12
		return _numeric_civil(hour, value.minute, value.second, options, suffix, arabic=False)

	def _format_ghurubi(self, value: timedelta, options: ClockFormatOptions) -> str:
		hour, minute, second = _elapsed_parts(value)
		if options.hour_system is HourSystem.TWENTY_FOUR:
			return _numeric_elapsed(hour, minute, second, options, arabic=False)
		period = "nighttime" if value < timedelta(hours=12) else "daytime"
		display_hour = hour % 12 or 12
		parts = [_english_unit_phrase(display_hour, "hour", words=False)]
		if minute or options.speak_zero_minute:
			parts.append(_english_unit_phrase(minute, "minute", words=False))
		if options.show_seconds:
			parts.append(_english_unit_phrase(second, "second", words=False))
		return ", ".join(parts) + f", {period}"


class ArabicWordClockFormatter(_ArabicTemplates):
	representation = TimeRepresentation.WORDS

	def _format_zawali(self, value: datetime, options: ClockFormatOptions) -> str:
		if options.hour_system is HourSystem.TWELVE:
			hour = value.hour % 12 or 12
			result = f"{_arabic_hour_word(hour)} {_civil_period(value.hour, 'ar')}"
		else:
			result = _arabic_hour_word(value.hour)
		return _append_arabic_units(result, value.minute, value.second, options)

	def _format_ghurubi(self, value: timedelta, options: ClockFormatOptions) -> str:
		hour, minute, second = _elapsed_parts(value)
		if options.hour_system is HourSystem.TWELVE:
			display_hour = hour % 12 or 12
			period = "ليلًا" if value < timedelta(hours=12) else "نهارًا"
			result = f"{_arabic_hour_word(display_hour)} {period}"
		else:
			result = _arabic_hour_word(hour)
		return _append_arabic_units(result, minute, second, options)


class EnglishWordClockFormatter(_EnglishTemplates):
	representation = TimeRepresentation.WORDS

	def _format_zawali(self, value: datetime, options: ClockFormatOptions) -> str:
		hour = value.hour
		period = _civil_period(hour, "en")
		if options.hour_system is HourSystem.TWELVE:
			hour = hour % 12 or 12
			result = f"{_english_number(hour)} {period}"
		else:
			result = _english_unit_phrase(hour, "hour", words=True)
		return _append_english_units(result, value.minute, value.second, options)

	def _format_ghurubi(self, value: timedelta, options: ClockFormatOptions) -> str:
		hour, minute, second = _elapsed_parts(value)
		if options.hour_system is HourSystem.TWELVE:
			display_hour = hour % 12 or 12
			period = "nighttime" if value < timedelta(hours=12) else "daytime"
			result = f"{_english_number(display_hour)} {period}"
		else:
			result = _english_unit_phrase(hour, "hour", words=True)
		return _append_english_units(result, minute, second, options)


def _civil_period(original_hour: int, language: str) -> str:
	"""Derive AM/PM from the original 24-hour value before display conversion."""
	if not 0 <= original_hour <= 23:
		raise ValueError("civil hour must be from 0 through 23")
	periods = {"ar": ("صباحًا", "مساءً"), "en": ("AM", "PM")}
	try:
		return periods[language][original_hour >= 12]
	except KeyError as error:
		raise ValueError("unsupported clock language") from error
def _elapsed_parts(value: timedelta) -> tuple[int, int, int]:
	total_seconds = int(value.total_seconds())
	hour, remainder = divmod(total_seconds, 3600)
	minute, second = divmod(remainder, 60)
	return hour, minute, second


def _numeric_elapsed(hour: int, minute: int, second: int, options: ClockFormatOptions,
		*, arabic: bool) -> str:
	parts = [str(hour) if arabic else _english_unit_phrase(hour, "hour", words=False)]
	if minute or options.speak_zero_minute:
		parts.append(_arabic_unit_phrase(minute, "minute", words=False) if arabic else
			_english_unit_phrase(minute, "minute", words=False))
	if options.show_seconds:
		parts.append(_arabic_unit_phrase(second, "second", words=False) if arabic else
			_english_unit_phrase(second, "second", words=False))
	return (" و" if arabic else " and ").join(parts)


def _numeric_civil(hour: int, minute: int, second: int, options: ClockFormatOptions,
		suffix: str, *, arabic: bool) -> str:
	parts = [str(hour)]
	if minute or options.speak_zero_minute:
		parts.append(_arabic_unit_phrase(minute, "minute", words=False) if arabic else
			_english_unit_phrase(minute, "minute", words=False))
	if options.show_seconds:
		parts.append(_arabic_unit_phrase(second, "second", words=False) if arabic else
			_english_unit_phrase(second, "second", words=False))
	return (" و" if arabic else " and ").join(parts) + suffix


_ARABIC_HOURS = {
	0: "الصفر", 1: "الواحدة", 2: "الثانية", 3: "الثالثة", 4: "الرابعة", 5: "الخامسة",
	6: "السادسة", 7: "السابعة", 8: "الثامنة", 9: "التاسعة", 10: "العاشرة",
	11: "الحادية عشرة", 12: "الثانية عشرة", 13: "الثالثة عشرة", 14: "الرابعة عشرة",
	15: "الخامسة عشرة", 16: "السادسة عشرة", 17: "السابعة عشرة", 18: "الثامنة عشرة",
	19: "التاسعة عشرة", 20: "العشرون", 21: "الحادية والعشرون", 22: "الثانية والعشرون",
	23: "الثالثة والعشرون", 24: "الرابعة والعشرون", 25: "الخامسة والعشرون",
}


def _arabic_hour_word(hour: int) -> str:
	try:
		return _ARABIC_HOURS[hour]
	except KeyError as error:
		raise ValueError("word formatting supports elapsed hours from 0 through 25") from error


_ARABIC_ONES = {3: "ثلاث", 4: "أربع", 5: "خمس", 6: "ست", 7: "سبع", 8: "ثمانٍ", 9: "تسع"}
_ARABIC_TENS = {20: "عشرون", 30: "ثلاثون", 40: "أربعون", 50: "خمسون"}


def _arabic_number(value: int) -> str:
	if value == 0:
		return "صفر"
	if value == 1:
		return "إحدى"
	if value == 2:
		return "اثنتان"
	if value == 8:
		return "ثماني"
	if 3 <= value <= 9:
		return _ARABIC_ONES[value]
	if value == 10:
		return "عشر"
	if value == 11:
		return "إحدى عشرة"
	if value == 12:
		return "اثنتا عشرة"
	if value == 18:
		return "ثماني عشرة"
	if 13 <= value <= 19:
		return f"{_ARABIC_ONES[value - 10]} عشرة"
	if value in _ARABIC_TENS:
		return _ARABIC_TENS[value]
	if 21 <= value <= 59:
		ones = {1: "إحدى", 2: "اثنتان", **_ARABIC_ONES}[value % 10]
		return f"{ones} و{_ARABIC_TENS[value - value % 10]}"
	raise ValueError("Arabic number must be from 0 through 59")


def _arabic_unit_phrase(value: int, unit: str, *, words: bool) -> str:
	if unit == "minute":
		one, two, plural = "دقيقة واحدة", "دقيقتان", "دقائق"
	else:
		one, two, plural = "ثانية واحدة", "ثانيتان", "ثوانٍ"
	if value == 0:
		return "صفر دقيقة" if unit == "minute" else "صفر ثانية"
	if value == 1:
		return one
	if value == 2:
		return two
	number = _arabic_number(value) if words else str(value)
	return f"{number} {plural if 3 <= value <= 10 else ('دقيقة' if unit == 'minute' else 'ثانية')}"


def _append_arabic_units(result: str, minute: int, second: int, options: ClockFormatOptions) -> str:
	if minute or options.speak_zero_minute:
		result += " و" + _arabic_unit_phrase(minute, "minute", words=True)
	if options.show_seconds:
		result += " و" + _arabic_unit_phrase(second, "second", words=True)
	return result


_ENGLISH_SMALL = (
	"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
	"eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
)
_ENGLISH_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty"}


def _english_number(value: int) -> str:
	if 0 <= value < 20:
		return _ENGLISH_SMALL[value]
	if 20 <= value <= 59:
		tens, ones = divmod(value, 10)
		return _ENGLISH_TENS[tens * 10] + (f"-{_ENGLISH_SMALL[ones]}" if ones else "")
	raise ValueError("English number must be from 0 through 59")


def _english_unit_phrase(value: int, unit: str, *, words: bool) -> str:
	number = _english_number(value) if words else str(value)
	return f"{number} {unit if value == 1 else unit + 's'}"


def _append_english_units(result: str, minute: int, second: int, options: ClockFormatOptions) -> str:
	parts: list[str] = []
	if minute or options.speak_zero_minute:
		parts.append(_english_unit_phrase(minute, "minute", words=True))
	if options.show_seconds:
		parts.append(_english_unit_phrase(second, "second", words=True))
	if parts:
		result += " and " + " and ".join(parts)
	return result
