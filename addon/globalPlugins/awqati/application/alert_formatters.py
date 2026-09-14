"""Task 4.2 message resources and pure formatting, without presentation."""

from datetime import timedelta

from ..domain import AlertEvent, ClockFormatOptions, ClockType, TimeRepresentation
from .clock_formatters import ArabicWordClockFormatter, EnglishWordClockFormatter, NumericClockFormatter
from .daily_info_formatters import _format_duration


_ARABIC = {
	"alert.prayer.before": "اقترب دخول وقت صلاة {prayer}، وقد بقي عليه {duration}.",
	"alert.sunrise.before": "اقترب وقت شروق الشمس، وقد بقي عليه {duration}.",
	"alert.midnight.before": "اقترب وقت انتصاف الليل، وقد بقي عليه {duration}.",
	"alert.lastThird.before": "اقترب دخول وقت الثلث الأخير من الليل، وقد بقي عليه {duration}.",
	"alert.prayer.at": "حان الآن وقت صلاة {prayer}.",
	"alert.sunrise.at": "أشرقت الشمس.",
	"alert.midnight.at": "انتصف الليل.",
	"alert.lastThird.at": "دخل وقت الثلث الأخير من الليل.",
	"alert.prayer.iqamaBefore": "بقي على إقامة صلاة {prayer} {duration}.",
	"alert.sunrise.after": "مضى على شروق الشمس {duration}.",
	"alert.midnight.after": "مضى على انتصاف الليل {duration}.",
	"alert.lastThird.after": "مضى على حلول الثلث الأخير من الليل {duration}.",
}
_ENGLISH = {
	"alert.prayer.before": "The time for {prayer} prayer is approaching, with {duration} remaining.",
	"alert.sunrise.before": "Sunrise is approaching, with {duration} remaining.",
	"alert.midnight.before": "The middle of the night is approaching, with {duration} remaining.",
	"alert.lastThird.before": "The last third of the night is approaching, with {duration} remaining.",
	"alert.prayer.at": "It is now time for {prayer} prayer.",
	"alert.sunrise.at": "The sun has risen.",
	"alert.midnight.at": "It is the middle of the night.",
	"alert.lastThird.at": "The last third of the night has begun.",
	"alert.prayer.iqamaBefore": "There are {duration} until the estimated Iqama for {prayer} prayer.",
	"alert.sunrise.after": "It has been {duration} since sunrise.",
	"alert.midnight.after": "It has been {duration} since the middle of the night.",
	"alert.lastThird.after": "It has been {duration} since the last third of the night began.",
}
_PRAYERS = {
	"ar": {"fajr": "الفجر", "dhuhr": "الظهر", "asr": "العصر", "maghrib": "المغرب", "isha": "العشاء"},
	"en": {"fajr": "Fajr", "dhuhr": "Dhuhr", "asr": "Asr", "maghrib": "Maghrib", "isha": "Isha"},
}


def format_prayer_alert(event: AlertEvent, language: str = "ar") -> str:
	"""Format the scheduled message; no speech, sound or scheduler operations."""
	if language not in _PRAYERS:
		raise ValueError("unsupported alert language")
	minutes = event.metadata["duration_minutes"]
	if language == "ar":
		duration = _format_duration(timedelta(minutes=minutes))
	else:
		hours, remainder = divmod(minutes, 60)
		duration = " and ".join(f"{count} {unit}{'' if count == 1 else 's'}"
			for count, unit in ((hours, "hour"), (remainder, "minute")) if count) or "zero minutes"
	templates = _ARABIC if language == "ar" else _ENGLISH
	return templates[event.message_id].format(
		prayer=_PRAYERS[language].get(event.metadata["event_name"], ""), duration=duration)


def format_clock_alert(event: AlertEvent, language: str = "ar") -> str:
	"""Delegate all clock wording to the formatters already implemented in 2.1."""
	if language not in _PRAYERS or event.message_id != "alert.clock.time":
		raise ValueError("unsupported clock alert or language")
	settings = event.metadata["presentations"]

	def formatter(kind):
		if settings[kind].representation is TimeRepresentation.NUMERIC:
			return NumericClockFormatter(language)
		return ArabicWordClockFormatter() if language == "ar" else EnglishWordClockFormatter()

	def options(kind):
		config = settings[kind]
		return ClockFormatOptions(config.hour_system, config.speak_seconds, config.speak_zero_minute, config.style)

	return formatter(ClockType.ZAWALI).format_announcement(event.metadata["reading"],
		ClockType.ZAWALI, options(ClockType.ZAWALI),
		ghurubi_formatter=formatter(ClockType.GHURUBI), ghurubi_options=options(ClockType.GHURUBI))
