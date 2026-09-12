"""Arabic and English rendering for the five explicit calendar identities."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import CalendarDate, CalendarId, CalendarReading, DateFormat, PrimaryCalendar


@runtime_checkable
class DateFormatter(Protocol):
	language: str

	def format_primary(self, reading: CalendarReading,
			primary: PrimaryCalendar = PrimaryCalendar.HIJRI_UMM_AL_QURA,
			style: DateFormat = DateFormat.DOUBLE) -> str:
		...

	def format_calendar(self, reading: CalendarReading,
			style: DateFormat = DateFormat.DOUBLE) -> str:
		...


_AR_WEEKDAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_AR_MONTHS = {
	CalendarId.GREGORIAN: ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"),
	CalendarId.HIJRI_UMM_AL_QURA: ("محرم", "صفر", "ربيع الأول", "ربيع الثاني", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"),
	CalendarId.SAUDI_SOLAR_HIJRI: ("الميزان", "العقرب", "القوس", "الجدي", "الدلو", "الحوت", "الحمل", "الثور", "الجوزاء", "السرطان", "الأسد", "السنبلة"),
	CalendarId.PERSIAN_SOLAR_HIJRI: ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"),
	CalendarId.AFGHAN_SOLAR_HIJRI: ("حمل", "ثور", "جوزا", "سرطان", "أسد", "سنبلة", "ميزان", "عقرب", "قوس", "جدي", "دلو", "حوت"),
}
_EN_MONTHS = {
	CalendarId.GREGORIAN: ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
	CalendarId.HIJRI_UMM_AL_QURA: ("Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani", "Jumada al-Ula", "Jumada al-Akhirah", "Rajab", "Shaban", "Ramadan", "Shawwal", "Dhu al-Qadah", "Dhu al-Hijjah"),
	CalendarId.SAUDI_SOLAR_HIJRI: ("al-Mizan", "al-Aqrab", "al-Qaws", "al-Jadi", "al-Dalw", "al-Hut", "al-Hamal", "al-Thawr", "al-Jawza", "al-Saratan", "al-Asad", "al-Sunbula"),
	CalendarId.PERSIAN_SOLAR_HIJRI: ("Farvardin", "Ordibehesht", "Khordad", "Tir", "Mordad", "Shahrivar", "Mehr", "Aban", "Azar", "Dey", "Bahman", "Esfand"),
	CalendarId.AFGHAN_SOLAR_HIJRI: ("Hamal", "Sawr", "Jawza", "Saratan", "Asad", "Sonbola", "Mizan", "Aqrab", "Qaws", "Jadi", "Dalw", "Hut"),
}
_SYRIAC_MONTHS = ("كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول")


class _BaseDateFormatter:
	language: str
	months: dict[CalendarId, tuple[str, ...]]
	weekdays: tuple[str, ...]

	def format_primary(self, reading: CalendarReading,
			primary: PrimaryCalendar = PrimaryCalendar.HIJRI_UMM_AL_QURA,
			style: DateFormat = DateFormat.DOUBLE) -> str:
		if not isinstance(primary, PrimaryCalendar):
			raise TypeError("primary must be a PrimaryCalendar")
		if not isinstance(style, DateFormat):
			raise TypeError("style must be a DateFormat")
		if style is DateFormat.DOUBLE:
			first, second = ((reading.lunar_visible, reading.gregorian)
				if primary is PrimaryCalendar.HIJRI_UMM_AL_QURA
				else (reading.gregorian, reading.lunar_visible))
			return self._double(reading.weekday, first, second)
		selected = reading.lunar_visible if primary is PrimaryCalendar.HIJRI_UMM_AL_QURA else reading.gregorian
		return self._single(reading.weekday, selected, style)

	def format_calendar(self, reading: CalendarReading,
			style: DateFormat = DateFormat.DOUBLE) -> str:
		if not isinstance(style, DateFormat):
			raise TypeError("style must be a DateFormat")
		if style is DateFormat.DOUBLE:
			if reading.selected.calendar_id is CalendarId.GREGORIAN:
				return self._double(reading.weekday, reading.gregorian, reading.lunar_visible)
			if reading.selected.calendar_id is CalendarId.HIJRI_UMM_AL_QURA:
				return self._double(reading.weekday, reading.lunar_visible, reading.gregorian)
			return self._double(reading.weekday, reading.selected, reading.lunar_visible)
		return self._single(reading.weekday, reading.selected, style)

	def _date(self, value: CalendarDate, *, gregorian_syrian: bool = False) -> str:
		raise NotImplementedError

	def _double(self, weekday: int, first: CalendarDate, second: CalendarDate) -> str:
		raise NotImplementedError

	def _single(self, weekday: int, value: CalendarDate, style: DateFormat) -> str:
		raise NotImplementedError


class ArabicDateFormatter(_BaseDateFormatter):
	language = "ar"
	months = _AR_MONTHS
	weekdays = _AR_WEEKDAYS

	def _date(self, value: CalendarDate, *, gregorian_syrian: bool = False) -> str:
		month = self.months[value.calendar_id][value.month - 1]
		if gregorian_syrian and value.calendar_id is CalendarId.GREGORIAN:
			month += f" ({_SYRIAC_MONTHS[value.month - 1]})"
		era = {
			CalendarId.GREGORIAN: "ميلاديًا",
			CalendarId.HIJRI_UMM_AL_QURA: "هجريًا",
			CalendarId.SAUDI_SOLAR_HIJRI: "هجري شمسي",
			CalendarId.PERSIAN_SOLAR_HIJRI: "هجري شمسي فارسي",
			CalendarId.AFGHAN_SOLAR_HIJRI: "هجري شمسي أفغاني",
		}[value.calendar_id]
		return f"{value.day} {month} {value.year} {era}"

	def _double(self, weekday: int, first: CalendarDate, second: CalendarDate) -> str:
		return f"اليوم هو: {self.weekdays[weekday]} {self._date(first)}، الموافق {self._date(second)}."

	def _single(self, weekday: int, value: CalendarDate, style: DateFormat) -> str:
		if style is DateFormat.SHORT:
			return f"{value.day} {self.months[value.calendar_id][value.month - 1]}."
		include_syrian = style is DateFormat.FULL and value.calendar_id is CalendarId.GREGORIAN
		body = f"{self.weekdays[weekday]} {self._date(value, gregorian_syrian=include_syrian)}"
		if style is DateFormat.FULL:
			return f"اليوم هو: {body}."
		if style is DateFormat.MODERATE:
			return body + "."
		raise ValueError("unsupported date format")


class EnglishDateFormatter(_BaseDateFormatter):
	language = "en"
	months = _EN_MONTHS
	weekdays = _EN_WEEKDAYS

	def _date(self, value: CalendarDate, *, gregorian_syrian: bool = False) -> str:
		month = self.months[value.calendar_id][value.month - 1]
		era = {
			CalendarId.GREGORIAN: "CE",
			CalendarId.HIJRI_UMM_AL_QURA: "AH",
			CalendarId.SAUDI_SOLAR_HIJRI: "Solar AH",
			CalendarId.PERSIAN_SOLAR_HIJRI: "Persian Solar AH",
			CalendarId.AFGHAN_SOLAR_HIJRI: "Afghan Solar AH",
		}[value.calendar_id]
		if value.calendar_id is CalendarId.GREGORIAN:
			return f"{month} {value.day}, {value.year} {era}"
		return f"{value.day} {month} {value.year} {era}"

	def _double(self, weekday: int, first: CalendarDate, second: CalendarDate) -> str:
		return f"Today is: {self.weekdays[weekday]}, {self._date(first)}, corresponding to {self._date(second)}."

	def _single(self, weekday: int, value: CalendarDate, style: DateFormat) -> str:
		if style is DateFormat.SHORT:
			month = self.months[value.calendar_id][value.month - 1]
			return f"{month} {value.day}." if value.calendar_id is CalendarId.GREGORIAN else f"{value.day} {month}."
		body = f"{self.weekdays[weekday]}, {self._date(value)}"
		if style is DateFormat.FULL:
			return f"Today is: {body}."
		if style is DateFormat.MODERATE:
			return body + "."
		raise ValueError("unsupported date format")
