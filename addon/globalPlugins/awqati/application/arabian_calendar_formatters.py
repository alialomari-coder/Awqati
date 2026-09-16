"""Language-specific presentation for Arabian calendar readings."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import ArabianCalendarReading, MonthDay


@runtime_checkable
class ArabianCalendarFormatter(Protocol):
	def format_short(self, reading: ArabianCalendarReading) -> str:
		...

	def format_detailed(self, reading: ArabianCalendarReading) -> str:
		...

	def format_combined(self, reading: ArabianCalendarReading) -> str:
		...


_ORDINAL_ONES = {
	1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس",
	6: "السادس", 7: "السابع", 8: "الثامن", 9: "التاسع",
}
_ORDINAL_TEENS = {
	10: "العاشر", 11: "الحادي عشر", 12: "الثاني عشر", 13: "الثالث عشر",
	14: "الرابع عشر", 15: "الخامس عشر", 16: "السادس عشر", 17: "السابع عشر",
	18: "الثامن عشر", 19: "التاسع عشر",
}
_ORDINAL_TENS = {
	20: "العشرون", 30: "الثلاثون", 40: "الأربعون", 50: "الخمسون",
	60: "الستون", 70: "السبعون", 80: "الثمانون", 90: "التسعون",
}
_MONTHS = {
	1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
	7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}
_ENGLISH_MONTHS = (
	"", "January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
)


def arabic_ordinal(value: int) -> str:
	"""Return a readable masculine Arabic ordinal for supported calendar days."""
	if value <= 0 or value > 399:
		raise ValueError("Arabic ordinal must be from 1 through 399")
	if value < 10:
		return _ORDINAL_ONES[value]
	if value < 20:
		return _ORDINAL_TEENS[value]
	if value < 100:
		tens, ones = divmod(value, 10)
		return _ORDINAL_TENS[tens * 10] if not ones else f"{_ORDINAL_ONES[ones]} و{_ORDINAL_TENS[tens * 10]}"
	hundreds, remainder = divmod(value, 100)
	hundred = {1: "المئة", 2: "المئتان", 3: "الثلاثمئة"}[hundreds]
	if not remainder:
		return hundred
	connector = "المئة" if hundreds == 1 else ("المئتين" if hundreds == 2 else "الثلاثمئة")
	return f"{arabic_ordinal(remainder)} بعد {connector}"


def english_ordinal(value: int) -> str:
	if 10 <= value % 100 <= 20:
		suffix = "th"
	else:
		suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
	return f"{value}{suffix}"


class ArabicArabianCalendarFormatter:
	language = "ar"

	def format_short(self, reading: ArabianCalendarReading) -> str:
		season = reading.season.name
		if reading.folk_subdivision:
			season += f": {reading.folk_subdivision}"
		text = (
			f"سنة سهيل: اليوم {reading.suhail_day}. الطالع: {reading.talaa.name}، "
			f"اليوم {arabic_ordinal(reading.talaa_day)} منه. وهو من موسم {season}."
		)
		if reading.short_saying:
			text += f" ومن المأثور فيه: {reading.short_saying.text}"
		return text

	def format_detailed(self, reading: ArabianCalendarReading) -> str:
		return self._format(reading, combined=False)

	def format_combined(self, reading: ArabianCalendarReading) -> str:
		return self._format(reading, combined=True)

	def _format(self, reading: ArabianCalendarReading, *, combined: bool) -> str:
		prefix = "وفي التقويم العربي: " if combined else ""
		sections = [f"{prefix}اليوم هو {arabic_ordinal(reading.suhail_day)} من سنة سهيل."]
		talaa = reading.talaa
		sections.append("\n".join((
			f"الطالع الحالي: {talaa.name}.",
			f"الفترة: من {_month_day(talaa.start)} إلى {_month_day(talaa.end)}.",
			f"اليوم {reading.talaa_day} من {reading.talaa_length}.",
		)))
		season_lines = [f"الموسم الجامع: {reading.season.name}."]
		if reading.folk_subdivision:
			season_lines.append(f"التقسيم الشعبي: {reading.folk_subdivision}.")
		season_lines.extend(reading.season.notes)
		sections.append("\n".join(season_lines))
		mansion = []
		if reading.mansion and reading.mansion.description:
			mansion.append(f"المنزلة: {reading.mansion.description}")
		if reading.mansion and reading.mansion.name_origin:
			mansion.append(f"أصل الاسم: {reading.mansion.name_origin}")
		if mansion:
			sections.append("\n".join(mansion))
		if talaa.heritage_notes:
			sections.append("المادة التراثية:\n" + "\n".join(talaa.heritage_notes))
		if reading.naw:
			sections.append("النوء القديم:\n" + reading.naw.description)
		if talaa.sayings:
			sections.append("الأقوال المأثورة:\n" + "\n".join(s.text for s in talaa.sayings))
		if reading.overlapping_periods:
			lines = [
				f"{period.name}: من {_month_day(period.start)} إلى {_month_day(period.end)}. {period.description}"
				for period in reading.overlapping_periods
			]
			sections.append("الفترات المتداخلة:\n" + "\n".join(lines))
		if reading.start_events:
			sections.append("أحداث البداية:\n" + "\n".join(e.text for e in reading.start_events))
		return "\n\n".join(sections)


class EnglishArabianCalendarFormatter:
	language = "en"

	def format_short(self, reading: ArabianCalendarReading) -> str:
		text = (
			f"Suhail year: day {reading.suhail_day}. Current Talaa: {reading.talaa.name}; "
			f"day {reading.talaa_day}. Season: {reading.season.name}."
		)
		if reading.short_saying:
			text += f" Traditional saying: {reading.short_saying.text}"
		return text

	def format_detailed(self, reading: ArabianCalendarReading) -> str:
		return self._format(reading, combined=False)

	def format_combined(self, reading: ArabianCalendarReading) -> str:
		return self._format(reading, combined=True)

	def _format(self, reading: ArabianCalendarReading, *, combined: bool) -> str:
		prefix = "In the Arabian calendar, " if combined else ""
		lead = "In the Arabian calendar, today" if combined else "Today"
		sections = [f"{lead} is the {english_ordinal(reading.suhail_day)} day of the Suhail year."]
		talaa = reading.talaa
		sections.append("\n".join((
			f"Current Talaa: {talaa.name}.",
			f"Period: {_english_month_day(talaa.start)} to {_english_month_day(talaa.end)}.",
			f"Day {reading.talaa_day} of {reading.talaa_length}.",
			f"Season: {reading.season.name}.",
		)))
		if reading.folk_subdivision:
			sections.append(f"Traditional subdivision: {reading.folk_subdivision}.")
		if talaa.heritage_notes:
			sections.append("Heritage notes:\n" + "\n".join(talaa.heritage_notes))
		if reading.naw:
			sections.append("Traditional Naw:\n" + reading.naw.description)
		if talaa.sayings:
			sections.append("Traditional sayings:\n" + "\n".join(s.text for s in talaa.sayings))
		return "\n\n".join(sections)


def _month_day(value: MonthDay) -> str:
	return f"{value.day} {_MONTHS[value.month]}"


def _english_month_day(value: MonthDay) -> str:
	return f"{_ENGLISH_MONTHS[value.month]} {value.day}"
