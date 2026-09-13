"""Language-specific presentation for scientific and combined daily information."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from ..domain import AstronomyReading, DailyInfoReading, MoonPhase, Season, SeasonEvent
from .arabian_calendar_formatters import ArabianCalendarFormatter, ArabicArabianCalendarFormatter


@runtime_checkable
class DailyInfoFormatter(Protocol):
	"""Present astronomy alone or a combined scientific-and-heritage reading."""

	def format_scientific(self, reading: AstronomyReading) -> str:
		...

	def format(self, reading: DailyInfoReading) -> str:
		...


_SEASONS = {
	Season.SPRING: "الربيع",
	Season.SUMMER: "الصيف",
	Season.AUTUMN: "الخريف",
	Season.WINTER: "الشتاء",
}
_SEASON_EVENTS = {
	SeasonEvent.MARCH_EQUINOX: "الاعتدال الربيعي",
	SeasonEvent.JUNE_SOLSTICE: "الانقلاب الصيفي",
	SeasonEvent.SEPTEMBER_EQUINOX: "الاعتدال الخريفي",
	SeasonEvent.DECEMBER_SOLSTICE: "الانقلاب الشتوي",
}
_MOON_PHASES = {
	MoonPhase.NEW_MOON: "المحاق",
	MoonPhase.WAXING_CRESCENT: "الهلال المتزايد",
	MoonPhase.FIRST_QUARTER: "التربيع الأول",
	MoonPhase.WAXING_GIBBOUS: "الأحدب المتزايد",
	MoonPhase.FULL_MOON: "البدر",
	MoonPhase.WANING_GIBBOUS: "الأحدب المتناقص",
	MoonPhase.LAST_QUARTER: "التربيع الأخير",
	MoonPhase.WANING_CRESCENT: "الهلال المتناقص",
}
_MONTHS = {
	1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
	7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


class ArabicDailyInfoFormatter:
	"""Arabic formatter with visibly separate scientific and heritage sections."""

	language = "ar"

	def __init__(self, arabian_calendar: ArabianCalendarFormatter | None = None) -> None:
		self._arabian_calendar = arabian_calendar or ArabicArabianCalendarFormatter()

	def format_scientific(self, reading: AstronomyReading) -> str:
		return "\n".join((
			"المعلومات الفلكية العلمية:",
			f"الفصل الفلكي الحالي: {_SEASONS[reading.current_season]}.",
			(
				f"الاعتدال أو الانقلاب القادم: "
				f"{_SEASON_EVENTS[reading.next_seasonal_event.event]}، "
				f"{_format_local_datetime(reading.next_seasonal_event_local)}."
			),
			f"طول النهار: {_format_duration(reading.solar_day.daylight)}.",
			f"طول الليل: {_format_duration(reading.solar_day.night)}.",
			f"طور القمر: {_MOON_PHASES[reading.lunar.phase]}.",
			f"عمر القمر التقريبي: {reading.lunar.age_days:.1f} يوم.",
			f"نسبة الإضاءة: {reading.lunar.illumination_fraction * 100:.1f} بالمئة.",
			f"المحاق القادم: {_format_local_datetime(reading.next_new_moon_local)}.",
			f"البدر القادم: {_format_local_datetime(reading.next_full_moon_local)}.",
		))

	def format(self, reading: DailyInfoReading) -> str:
		sections = [self.format_scientific(reading.scientific)]
		if reading.heritage is not None:
			sections.append(
				"معلومات التقويم العربي:\n"
				+ self._arabian_calendar.format_detailed(reading.heritage)
			)
		return "\n\n".join(sections)


def _format_duration(value: timedelta) -> str:
	total_minutes = max(0, round(value.total_seconds() / 60))
	hours, minutes = divmod(total_minutes, 60)
	if hours and minutes:
		return f"{hours} ساعة و{minutes} دقيقة"
	if hours:
		return f"{hours} ساعة"
	return f"{minutes} دقيقة"


def _format_local_datetime(value: datetime) -> str:
	offset = value.utcoffset()
	if offset is None:
		raise ValueError("local astronomy event datetime must include a UTC offset")
	total_minutes = round(offset.total_seconds() / 60)
	sign = "+" if total_minutes >= 0 else "-"
	offset_hours, offset_minutes = divmod(abs(total_minutes), 60)
	return (
		f"{value.day} {_MONTHS[value.month]} {value.year}، "
		f"الساعة {value:%H:%M} بالتوقيت المحلي "
		f"(UTC{sign}{offset_hours:02d}:{offset_minutes:02d})"
	)
