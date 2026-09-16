"""Task 4.2 message resources and pure formatting, without presentation."""

from datetime import timedelta

from ..domain import AlertEvent, ClockFormatOptions, ClockType, TimeRepresentation
from ..domain.settings import DEFAULT_DAILY_WIRD_TEXT
from .clock_formatters import ArabicWordClockFormatter, EnglishWordClockFormatter, NumericClockFormatter
from .daily_info_formatters import _format_duration
from .islamic_terms import N_, normalize_language, term_text


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
	"alert.prayer.before": N_("The time for {prayer} prayer is approaching, with {duration} remaining."),
	"alert.sunrise.before": N_("Sunrise is approaching, with {duration} remaining."),
	"alert.midnight.before": N_("The middle of the night is approaching, with {duration} remaining."),
	"alert.lastThird.before": N_("The last third of the night is approaching, with {duration} remaining."),
	"alert.prayer.at": N_("It is now time for {prayer} prayer."),
	"alert.sunrise.at": N_("The sun has risen."),
	"alert.midnight.at": N_("It is the middle of the night."),
	"alert.lastThird.at": N_("The last third of the night has begun."),
	"alert.prayer.iqamaBefore": N_("There are {duration} until the estimated Iqama for {prayer} prayer."),
	"alert.sunrise.after": N_("It has been {duration} since sunrise."),
	"alert.midnight.after": N_("It has been {duration} since the middle of the night."),
	"alert.lastThird.after": N_("It has been {duration} since the last third of the night began."),
}
def format_prayer_alert(event: AlertEvent, language: str = "ar") -> str:
	"""Format the scheduled message; no speech, sound or scheduler operations."""
	language = normalize_language(language)
	minutes = event.metadata["duration_minutes"]
	if language == "ar":
		duration = _format_duration(timedelta(minutes=minutes))
	else:
		hours, remainder = divmod(minutes, 60)
		duration = " and ".join(f"{count} {unit}{'' if count == 1 else 's'}"
			for count, unit in ((hours, "hour"), (remainder, "minute")) if count) or "zero minutes"
	templates = _ARABIC if language == "ar" else _ENGLISH
	return templates[event.message_id].format(
		prayer=term_text(event.metadata["event_name"], language), duration=duration)


def format_clock_alert(event: AlertEvent, language: str = "ar") -> str:
	"""Delegate all clock wording to the formatters already implemented in 2.1."""
	language = normalize_language(language)
	if event.message_id != "alert.clock.time":
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


_ADHKAR_EVENT_MESSAGES = {
    "ar": {
        "alert.adhkar.morning": "حان وقت أذكار الصباح.",
        "alert.adhkar.evening": "حان وقت أذكار المساء.",
        "alert.adhkar.friday": "لا تنسَ ساعة الجمعة.",
    },
    "en": {
        "alert.adhkar.morning": N_("It is time for morning adhkar."),
        "alert.adhkar.evening": N_("It is time for evening adhkar."),
        "alert.adhkar.friday": N_("Remember the Friday hour."),
    },
}


def format_adhkar_alert(event: AlertEvent, language: str = "ar") -> str:
    """Return message text only; user-authored wird text is never translated."""
    language = normalize_language(language)
    if event.message_id == "alert.adhkar.dailyWird":
        text = event.metadata["text"]
        if text == DEFAULT_DAILY_WIRD_TEXT:
            return "لا تنس وردك اليومي." if language == "ar" else DEFAULT_DAILY_WIRD_TEXT
        return text
    identity = event.metadata["dhikr_id"] if event.message_id == "alert.adhkar.recurring" else event.message_id
    if event.message_id == "alert.adhkar.recurring":
        return term_text(identity, language)
    return _ADHKAR_EVENT_MESSAGES[language][identity]
