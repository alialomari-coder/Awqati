"""Language-specific presentation for scientific and combined daily information."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from ..domain import AstronomyReading, DailyInfoReading, MoonPhase, Season, SeasonEvent, SolarDayState
from .arabian_calendar_formatters import (
	ArabianCalendarFormatter,
	ArabicArabianCalendarFormatter,
	EnglishArabianCalendarFormatter,
	arabic_ordinal,
	english_ordinal,
)


@runtime_checkable
class DailyInfoFormatter(Protocol):
	def format_scientific(self, reading: AstronomyReading) -> str:
		...

	def format(self, reading: DailyInfoReading) -> str:
		...


_SEASONS = {
	Season.SPRING: "الربيع", Season.SUMMER: "الصيف",
	Season.AUTUMN: "الخريف", Season.WINTER: "الشتاء",
}
_ENGLISH_SEASONS = {
	Season.SPRING: "spring", Season.SUMMER: "summer",
	Season.AUTUMN: "autumn", Season.WINTER: "winter",
}
_NEXT_SEASON = {
	Season.SPRING: Season.SUMMER, Season.SUMMER: Season.AUTUMN,
	Season.AUTUMN: Season.WINTER, Season.WINTER: Season.SPRING,
}
_SEASON_EVENTS = {
	SeasonEvent.MARCH_EQUINOX: "الاعتدال الربيعي",
	SeasonEvent.JUNE_SOLSTICE: "الانقلاب الصيفي",
	SeasonEvent.SEPTEMBER_EQUINOX: "الاعتدال الخريفي",
	SeasonEvent.DECEMBER_SOLSTICE: "الانقلاب الشتوي",
}
_ENGLISH_SEASON_EVENTS = {
	SeasonEvent.MARCH_EQUINOX: "the March equinox",
	SeasonEvent.JUNE_SOLSTICE: "the June solstice",
	SeasonEvent.SEPTEMBER_EQUINOX: "the September equinox",
	SeasonEvent.DECEMBER_SOLSTICE: "the December solstice",
}
_MOON_PHASES = {
	MoonPhase.NEW_MOON: "المحاق", MoonPhase.WAXING_CRESCENT: "الهلال المتزايد",
	MoonPhase.FIRST_QUARTER: "التربيع الأول", MoonPhase.WAXING_GIBBOUS: "الأحدب المتزايد",
	MoonPhase.FULL_MOON: "البدر", MoonPhase.WANING_GIBBOUS: "الأحدب المتناقص",
	MoonPhase.LAST_QUARTER: "التربيع الأخير", MoonPhase.WANING_CRESCENT: "الهلال المتناقص",
}
_ENGLISH_MOON_PHASES = {
	MoonPhase.NEW_MOON: "new moon", MoonPhase.WAXING_CRESCENT: "waxing crescent",
	MoonPhase.FIRST_QUARTER: "first quarter", MoonPhase.WAXING_GIBBOUS: "waxing gibbous",
	MoonPhase.FULL_MOON: "full moon", MoonPhase.WANING_GIBBOUS: "waning gibbous",
	MoonPhase.LAST_QUARTER: "last quarter", MoonPhase.WANING_CRESCENT: "waning crescent",
}
_MONTHS = {
	1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
	7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}
_ENGLISH_MONTHS = (
	"", "January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
)


class ArabicDailyInfoFormatter:
	language = "ar"

	def __init__(self, arabian_calendar: ArabianCalendarFormatter | None = None) -> None:
		self._arabian_calendar = arabian_calendar or ArabicArabianCalendarFormatter()

	def format_scientific(self, reading: AstronomyReading) -> str:
		remaining = _remaining(reading)
		season_text = (
			f"اليوم هو اليوم {arabic_ordinal(reading.season_day)} من فصل {_SEASONS[reading.current_season]}، "
			f"والذي بقي على انتهائه {_format_remaining(remaining)}. إذ سيدخل فصل "
			f"{_SEASONS[_NEXT_SEASON[reading.current_season]]} مع "
			f"{_SEASON_EVENTS[reading.next_seasonal_event.event]} يوم "
			f"{_format_day_month(reading.next_seasonal_event_local)}، "
			f"{_format_clock(reading.next_seasonal_event_local)} بالتوقيت المحلي."
		)
		moon_text = (
			f"القمر في طور {_MOON_PHASES[reading.lunar.phase]}، وعمره التقريبي "
			f"{_format_approximate_moon_age(reading.lunar.age_days)}، وتبلغ نسبة إضاءته "
			f"{reading.lunar.illumination_fraction * 100:.1f} بالمئة."
		)
		moon_events = (
			f"المحاق القادم يوم {_format_day_month(reading.next_new_moon_local)}، "
			f"والبدر القادم يوم {_format_day_month(reading.next_full_moon_local)}."
		)
		return "\n".join((season_text, _format_solar_summary(reading), moon_text, moon_events))

	def format(self, reading: DailyInfoReading) -> str:
		sections = [self.format_scientific(reading.scientific)]
		if reading.heritage is not None:
			sections.append(self._arabian_calendar.format_combined(reading.heritage))
		return "\n\n".join(sections)


class EnglishDailyInfoFormatter:
	language = "en"

	def __init__(self, arabian_calendar: ArabianCalendarFormatter | None = None) -> None:
		self._arabian_calendar = arabian_calendar or EnglishArabianCalendarFormatter()

	def format_scientific(self, reading: AstronomyReading) -> str:
		remaining = _remaining(reading)
		season_text = (
			f"Today is the {english_ordinal(reading.season_day)} day of {_ENGLISH_SEASONS[reading.current_season]}, "
			f"with {_format_remaining_en(remaining)} remaining. "
			f"{_ENGLISH_SEASONS[_NEXT_SEASON[reading.current_season]].capitalize()} begins at "
			f"{_ENGLISH_SEASON_EVENTS[reading.next_seasonal_event.event]} on "
			f"{_format_day_month_en(reading.next_seasonal_event_local)} at "
			f"{_format_clock_en(reading.next_seasonal_event_local)} local time."
		)
		moon_text = (
			f"The Moon is in its {_ENGLISH_MOON_PHASES[reading.lunar.phase]} phase, approximately "
			f"{round(reading.lunar.age_days)} days old, and {reading.lunar.illumination_fraction * 100:.1f} percent illuminated."
		)
		moon_events = (
			f"The next new moon is on {_format_day_month_en(reading.next_new_moon_local)}, "
			f"and the next full moon is on {_format_day_month_en(reading.next_full_moon_local)}."
		)
		return "\n".join((season_text, _format_solar_summary_en(reading), moon_text, moon_events))

	def format(self, reading: DailyInfoReading) -> str:
		sections = [self.format_scientific(reading.scientific)]
		if reading.heritage is not None:
			sections.append(self._arabian_calendar.format_combined(reading.heritage))
		return "\n\n".join(sections)


def _remaining(reading: AstronomyReading) -> timedelta:
	return reading.next_seasonal_event_local.astimezone(timezone.utc) - reading.observed_at_local.astimezone(timezone.utc)


def _format_solar_summary(reading: AstronomyReading) -> str:
	change = _format_daylight_change(reading.daylight_change_from_previous_day)
	if reading.solar_day.state is SolarDayState.POLAR_DAY:
		return "تسود حالة اليوم القطبي؛ يستمر ضوء النهار طوال 24 ساعة، ولا يوجد شروق أو غروب شمسي اعتيادي اليوم." + change
	if reading.solar_day.state is SolarDayState.POLAR_NIGHT:
		return "تسود حالة الليل القطبي؛ يستمر الليل طوال 24 ساعة، ولا يوجد شروق أو غروب شمسي اعتيادي اليوم." + change
	if reading.sunrise_local is None or reading.sunset_local is None:
		raise ValueError("normal solar day requires local sunrise and sunset")
	return (
		f"طول النهار اليوم {_format_duration(reading.solar_day.daylight)}، وطول الليل "
		f"{_format_duration(reading.solar_day.night)}،{change} حيث كان شروق الشمس عند "
		f"{_format_clock(reading.sunrise_local)}، وغروبها عند {_format_clock(reading.sunset_local)}."
	)


def _format_solar_summary_en(reading: AstronomyReading) -> str:
	change = _format_daylight_change_en(reading.daylight_change_from_previous_day)
	if reading.solar_day.state is SolarDayState.POLAR_DAY:
		return "This is a polar day with 24 hours of daylight and no ordinary sunrise or sunset today." + change
	if reading.solar_day.state is SolarDayState.POLAR_NIGHT:
		return "This is a polar night with 24 hours of night and no ordinary sunrise or sunset today." + change
	if reading.sunrise_local is None or reading.sunset_local is None:
		raise ValueError("normal solar day requires local sunrise and sunset")
	return (
		f"Daylight lasts {_format_duration_en(reading.solar_day.daylight)}, and night lasts "
		f"{_format_duration_en(reading.solar_day.night)}.{change} Sunrise was at "
		f"{_format_clock_en(reading.sunrise_local)}, and sunset was at {_format_clock_en(reading.sunset_local)}."
	)


def _format_daylight_change(value: timedelta | None) -> str:
	if value is None:
		return ""
	minutes = round(abs(value.total_seconds()) / 60)
	if minutes == 0:
		return " ولم يتغير طول النهار عن أمس تغيرًا ملحوظًا؛"
	direction = "طال" if value > timedelta(0) else "قصر"
	return f" وقد {direction} النهار عن أمس بنحو {_format_approximate_minutes(minutes)}؛"


def _format_daylight_change_en(value: timedelta | None) -> str:
	if value is None:
		return ""
	minutes = round(abs(value.total_seconds()) / 60)
	if minutes == 0:
		return " Daylight is effectively unchanged from yesterday."
	direction = "longer" if value > timedelta(0) else "shorter"
	return f" Daylight is about {minutes} minute{'s' if minutes != 1 else ''} {direction} than yesterday."


def _format_duration(value: timedelta) -> str:
	total_minutes = max(0, round(value.total_seconds() / 60))
	hours, minutes = divmod(total_minutes, 60)
	parts = []
	if hours:
		parts.append(_format_count(hours, "ساعة واحدة", "ساعتان", "ساعات", "ساعة"))
	if minutes:
		parts.append(_format_count(minutes, "دقيقة واحدة", "دقيقتان", "دقائق", "دقيقة"))
	return " و".join(parts) if parts else "صفر دقيقة"


def _format_duration_en(value: timedelta) -> str:
	total_minutes = max(0, round(value.total_seconds() / 60))
	hours, minutes = divmod(total_minutes, 60)
	parts = []
	if hours:
		parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
	if minutes:
		parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
	return " and ".join(parts) if parts else "zero minutes"


def _format_remaining(value: timedelta) -> str:
	total_minutes = max(0, int(value.total_seconds() // 60))
	days, remaining_minutes = divmod(total_minutes, 24 * 60)
	hours, minutes = divmod(remaining_minutes, 60)
	parts = []
	if days:
		parts.append(_format_count(days, "يوم واحد", "يومان", "أيام", "يومًا"))
	if hours:
		parts.append(_format_count(hours, "ساعة واحدة", "ساعتان", "ساعات", "ساعة"))
	if not days and minutes:
		parts.append(_format_count(minutes, "دقيقة واحدة", "دقيقتان", "دقائق", "دقيقة"))
	return " و".join(parts) if parts else "أقل من دقيقة"


def _format_remaining_en(value: timedelta) -> str:
	total_minutes = max(0, int(value.total_seconds() // 60))
	days, remaining_minutes = divmod(total_minutes, 24 * 60)
	hours, minutes = divmod(remaining_minutes, 60)
	parts = []
	if days:
		parts.append(f"{days} day{'s' if days != 1 else ''}")
	if hours:
		parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
	if not days and minutes:
		parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
	return " and ".join(parts) if parts else "less than a minute"


def _format_approximate_moon_age(value: float) -> str:
	days = round(value)
	if days <= 0:
		return "أقل من يوم"
	return _format_count(days, "يوم واحد", "يومان", "أيام", "يومًا")


def _format_approximate_minutes(value: int) -> str:
	return _format_count(value, "دقيقة واحدة", "دقيقتين", "دقائق", "دقيقة")


def _format_count(value: int, one: str, two: str, plural: str, singular: str) -> str:
	if value == 1:
		return one
	if value == 2:
		return two
	if 3 <= value <= 10:
		return f"{value} {plural}"
	return f"{value} {singular}"


def _format_day_month(value: datetime) -> str:
	return f"{value.day} {_MONTHS[value.month]}"


def _format_day_month_en(value: datetime) -> str:
	return f"{_ENGLISH_MONTHS[value.month]} {value.day}"


def _format_clock(value: datetime) -> str:
	if value.utcoffset() is None:
		raise ValueError("local astronomy datetime must include a UTC offset")
	value = (value + timedelta(seconds=30)).replace(second=0, microsecond=0)
	hour = value.hour % 12 or 12
	period = "صباحًا" if value.hour < 12 else "مساءً"
	if value.minute:
		minutes = _format_count(value.minute, "دقيقة واحدة", "دقيقتان", "دقائق", "دقيقة")
		return f"الساعة {hour} و{minutes} {period}"
	return f"الساعة {hour} {period}"


def _format_clock_en(value: datetime) -> str:
	if value.utcoffset() is None:
		raise ValueError("local astronomy datetime must include a UTC offset")
	value = (value + timedelta(seconds=30)).replace(second=0, microsecond=0)
	hour = value.hour % 12 or 12
	period = "AM" if value.hour < 12 else "PM"
	return f"{hour}:{value.minute:02d} {period}"
