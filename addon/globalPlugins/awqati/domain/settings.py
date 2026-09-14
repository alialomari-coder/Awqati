"""Language-neutral settings schema and pure validation for Awqati 4.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from types import MappingProxyType

from .calendar import CalendarId, DateFormat
from .clock import AnnouncementStyle, ClockType, HourSystem, TimeRepresentation
from .models import Location
from .prayer import AsrMethod, CalculationMethod, HighLatitudeRule
from .prayer_timeline import PRAYER_EVENT_NAMES, PrayerEventName


SETTINGS_SCHEMA_VERSION = 1
DEFAULT_EVENT_PRE_ALERT_MINUTES = 10
DEFAULT_IQAMA_ALERT_BEFORE_MINUTES = 5
DEFAULT_CURRENT_PRAYER_DURATION_MINUTES = 20
DEFAULT_IQAMA_DELAYS_MINUTES = MappingProxyType({
	PrayerEventName.FAJR: 25,
	PrayerEventName.DHUHR: 20,
	PrayerEventName.ASR: 20,
	PrayerEventName.MAGHRIB: 10,
	PrayerEventName.ISHA: 20,
})
MIN_USER_CORRECTION_MINUTES = -30
MAX_USER_CORRECTION_MINUTES = 30
MAX_DURATION_MINUTES = 180
DEFAULT_DAILY_WIRD_TEXT = "لا تنس وردك اليومي."


class SettingsValidationError(ValueError):
	"""The complete settings value violates the published schema."""

	def __init__(self, message: str, *, path: str = "settings", code: str = "invalidValue") -> None:
		super().__init__(message)
		self.path = path
		self.code = code


class AlertAction(Enum):
	SILENT = "silent"
	SPEECH = "speech"
	SOUND = "sound"
	SOUND_AND_SPEECH = "soundAndSpeech"


class LocationKind(Enum):
	SELECTED = "selected"
	CUSTOM = "custom"


class DayPeriod(Enum):
	AM = "AM"
	PM = "PM"


class MorningReference(Enum):
	AFTER_FAJR = "afterFajr"
	BEFORE_SUNRISE = "beforeSunrise"
	AFTER_SUNRISE = "afterSunrise"


class EveningReference(Enum):
	AFTER_ASR = "afterAsr"
	BEFORE_MAGHRIB = "beforeMaghrib"
	AFTER_MAGHRIB = "afterMaghrib"


class FridayReference(Enum):
	AFTER_ASR = "afterAsr"
	BEFORE_MAGHRIB = "beforeMaghrib"


class RecurringDhikrId(Enum):
	SUBHAN_ALLAH = "subhanAllah"
	ALHAMDU_LILLAH = "alhamduLillah"
	LA_ILAHA_ILLA_ALLAH = "laIlahaIllaAllah"
	ALLAHU_AKBAR = "allahuAkbar"
	LA_HAWLA_WA_LA_QUWWATA = "laHawlaWaLaQuwwata"
	ASTAGHFIRU_ALLAH = "astaghfiruAllah"
	SALAT_ALA_AL_NABI = "salatAlaAlNabi"
	UDHKUR_ALLAH = "udhkurAllah"
	LA_TANSA_DHIKR_ALLAH = "laTansaDhikrAllah"


@dataclass(slots=True)
class ClockTime:
	hour: int
	minute: int


@dataclass(slots=True)
class SoundReference:
	"""Canonical path relative to the future Awqati user-data root."""

	value: str


@dataclass(slots=True)
class StoredLocation:
	kind: LocationKind
	location: Location
	country_code: str | None = None


@dataclass(slots=True)
class QuietHoursSettings:
	enabled: bool = False
	start: ClockTime = field(default_factory=lambda: ClockTime(22, 0))
	end: ClockTime = field(default_factory=lambda: ClockTime(6, 0))
	apply_to_prayer_alerts: bool = False


@dataclass(slots=True)
class GeneralSettings:
	all_automatic_alerts_enabled: bool = True
	quiet_hours: QuietHoursSettings = field(default_factory=QuietHoursSettings)


@dataclass(slots=True)
class AlertOutputSettings:
	action: AlertAction = AlertAction.SPEECH
	sound: SoundReference | None = None


@dataclass(slots=True)
class IqamaAlertSettings:
	delay_minutes: int
	alert_before_minutes: int = DEFAULT_IQAMA_ALERT_BEFORE_MINUTES
	alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)


@dataclass(slots=True)
class PrayerEventAlertSettings:
	pre_alert_minutes: int = DEFAULT_EVENT_PRE_ALERT_MINUTES
	pre_alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)
	at_time_alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)
	iqama: IqamaAlertSettings | None = None
	post_alert_minutes: int | None = None
	post_alert: AlertOutputSettings | None = None


def _default_prayer_events() -> dict[PrayerEventName, PrayerEventAlertSettings]:
	result: dict[PrayerEventName, PrayerEventAlertSettings] = {}
	for name in PrayerEventName:
		if name in PRAYER_EVENT_NAMES:
			result[name] = PrayerEventAlertSettings(iqama=IqamaAlertSettings(DEFAULT_IQAMA_DELAYS_MINUTES[name]))
		else:
			post_minutes = 20 if name is PrayerEventName.SUNRISE else 0
			result[name] = PrayerEventAlertSettings(
				post_alert_minutes=post_minutes,
				post_alert=AlertOutputSettings(),
			)
	return result


def _default_corrections() -> dict[PrayerEventName, int]:
	return {name: 0 for name in PrayerEventName}


@dataclass(slots=True)
class PrayerSettings:
	alerts_enabled: bool = True
	calculation_method: CalculationMethod = CalculationMethod.AUTO
	asr_method: AsrMethod = AsrMethod.STANDARD
	high_latitude_rule: HighLatitudeRule = HighLatitudeRule.AUTO
	corrections_minutes: dict[PrayerEventName, int] = field(default_factory=_default_corrections)
	events: dict[PrayerEventName, PrayerEventAlertSettings] = field(default_factory=_default_prayer_events)
	current_prayer_after_iqama_minutes: int = DEFAULT_CURRENT_PRAYER_DURATION_MINUTES


@dataclass(slots=True)
class ClockPresentationSettings:
	style: AnnouncementStyle = AnnouncementStyle.DOUBLE
	hour_system: HourSystem = HourSystem.TWELVE
	representation: TimeRepresentation = TimeRepresentation.NUMERIC
	speak_seconds: bool = False
	speak_zero_minute: bool = False


def _default_clock_presentations() -> dict[ClockType, ClockPresentationSettings]:
	return {clock_type: ClockPresentationSettings() for clock_type in ClockType}


@dataclass(slots=True)
class ClockChimeIntervals:
	on_hour: bool = True
	on_quarter: bool = False
	on_half: bool = False
	on_three_quarters: bool = False


@dataclass(slots=True)
class ClockSettings:
	automatic_alert_enabled: bool = False
	presentations: dict[ClockType, ClockPresentationSettings] = field(default_factory=_default_clock_presentations)
	intervals: ClockChimeIntervals = field(default_factory=ClockChimeIntervals)
	alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)


def _default_calendar_formats() -> dict[CalendarId, DateFormat]:
	return {calendar_id: DateFormat.DOUBLE for calendar_id in CalendarId}


@dataclass(slots=True)
class CalendarSettings:
	primary_calendar: CalendarId = CalendarId.HIJRI_UMM_AL_QURA
	formats: dict[CalendarId, DateFormat] = field(default_factory=_default_calendar_formats)
	hijri_adjustment_days: int = 0
	include_arabian_calendar_in_daily_info: bool = False


@dataclass(slots=True)
class TimedDhikrSettings:
	enabled: bool
	reference: MorningReference | EveningReference | FridayReference
	minutes: int
	alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)


@dataclass(slots=True)
class DailyWirdSettings:
	enabled: bool = False
	text: str = DEFAULT_DAILY_WIRD_TEXT
	hour: int = 10
	minute: int = 0
	period: DayPeriod = DayPeriod.PM
	alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)


@dataclass(slots=True)
class RecurringDhikrItemSettings:
	enabled: bool = True
	alert: AlertOutputSettings = field(default_factory=AlertOutputSettings)


def _default_recurring_items() -> dict[RecurringDhikrId, RecurringDhikrItemSettings]:
	return {identity: RecurringDhikrItemSettings() for identity in RecurringDhikrId}


@dataclass(slots=True)
class RecurringDhikrSettings:
	enabled: bool = False
	interval_minutes: int = 60
	items: dict[RecurringDhikrId, RecurringDhikrItemSettings] = field(default_factory=_default_recurring_items)


@dataclass(slots=True)
class AdhkarSettings:
	alerts_enabled: bool = True
	morning: TimedDhikrSettings = field(default_factory=lambda: TimedDhikrSettings(
		False, MorningReference.BEFORE_SUNRISE, 15))
	evening: TimedDhikrSettings = field(default_factory=lambda: TimedDhikrSettings(
		False, EveningReference.BEFORE_MAGHRIB, 15))
	friday_hour: TimedDhikrSettings = field(default_factory=lambda: TimedDhikrSettings(
		False, FridayReference.BEFORE_MAGHRIB, 60))
	daily_wird: DailyWirdSettings = field(default_factory=DailyWirdSettings)
	recurring: RecurringDhikrSettings = field(default_factory=RecurringDhikrSettings)


@dataclass(slots=True)
class AwqatiSettings:
	schema_version: int = SETTINGS_SCHEMA_VERSION
	location: StoredLocation | None = None
	general: GeneralSettings = field(default_factory=GeneralSettings)
	prayer: PrayerSettings = field(default_factory=PrayerSettings)
	clock: ClockSettings = field(default_factory=ClockSettings)
	calendar: CalendarSettings = field(default_factory=CalendarSettings)
	adhkar: AdhkarSettings = field(default_factory=AdhkarSettings)


def default_settings() -> AwqatiSettings:
	settings = AwqatiSettings()
	validate_settings(settings)
	return settings


def _fail(message: str, path: str = "settings", code: str = "invalidValue") -> None:
	raise SettingsValidationError(message, path=path, code=code)


def _require_type(value: object, expected: type, path: str) -> None:
	if not isinstance(value, expected):
		_fail(f"{path} must be {expected.__name__}", path, "invalidType")


def _require_bool(value: object, path: str) -> None:
	if not isinstance(value, bool):
		_fail(f"{path} must be boolean", path, "invalidType")


def _require_int(value: object, minimum: int, maximum: int, path: str) -> None:
	if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
		_fail(f"{path} must be a whole number from {minimum} through {maximum}", path, "outOfRange")


def _validate_sound(value: SoundReference | None, path: str) -> None:
	if value is None:
		return
	_require_type(value, SoundReference, path)
	reference = value.value
	if not isinstance(reference, str) or not reference or "\\" in reference:
		_fail(f"{path} must be a non-empty canonical relative path", path, "invalidSound")
	if reference.startswith("/") or re.match(r"^[A-Za-z]:", reference):
		_fail(f"{path} must not be absolute", path, "invalidSound")
	parts = reference.split("/")
	if any(part in ("", ".", "..") or ":" in part for part in parts):
		_fail(f"{path} must remain inside the Awqati sound root", path, "invalidSound")
	if len(parts) < 3 or parts[0] != "sounds" or parts[1] not in {"adhan", "alerts", "adhkar"}:
		_fail(f"{path} must be under a supported Awqati sound category", path, "invalidSound")


def _validate_output(value: AlertOutputSettings, allowed: set[AlertAction], path: str) -> None:
	_require_type(value, AlertOutputSettings, path)
	if not isinstance(value.action, AlertAction):
		_fail(f"{path}.action is not a known alert action", f"{path}.action", "invalidChoice")
	if value.action not in allowed:
		_fail(f"{path}.action is not allowed for this feature", f"{path}.action", "invalidChoice")
	_validate_sound(value.sound, f"{path}.sound")


def _validate_exact_keys(mapping: object, expected: set[Enum], path: str) -> None:
	if not isinstance(mapping, dict) or set(mapping) != expected:
		_fail(f"{path} must define every supported identity exactly once", path, "invalidKeys")


def _validate_location(location: Location, path: str) -> None:
	_require_type(location, Location, path)
	for name in ("location_id", "name", "timezone_id"):
		value = getattr(location, name, None)
		field_path = f"{path}." + {"location_id": "locationId", "timezone_id": "timezoneId"}.get(name, name)
		if not isinstance(value, str) or not value.strip():
			_fail(f"{field_path} must not be empty", field_path, "invalidLocation")
	for name, minimum, maximum in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
		value = getattr(location, name, None)
		field_path = f"{path}.{name}"
		if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
			_fail(f"{field_path} is outside its valid range", field_path, "outOfRange")
	timezone_parts = location.timezone_id.split("/")
	if any(part in {"", ".", ".."} or re.fullmatch(r"[A-Za-z0-9._+-]+", part) is None
			for part in timezone_parts):
		_fail(f"{path}.timezoneId is not an IANA identifier", f"{path}.timezoneId", "invalidTimezone")


def validate_settings(settings: AwqatiSettings) -> None:
	"""Validate the whole graph before repository writes or runtime publication."""
	_require_type(settings, AwqatiSettings, "settings")
	if settings.schema_version != SETTINGS_SCHEMA_VERSION:
		_fail(f"schemaVersion must equal {SETTINGS_SCHEMA_VERSION}", "schemaVersion", "unsupportedSchema")
	if settings.location is not None:
		_require_type(settings.location, StoredLocation, "location")
		if not isinstance(settings.location.kind, LocationKind):
			_fail("location.kind is invalid", "location.kind", "invalidChoice")
		_validate_location(settings.location.location, "location.location")
		if settings.location.kind is LocationKind.SELECTED:
			code = settings.location.country_code
			if not isinstance(code, str) or re.fullmatch(r"[A-Z]{2}", code) is None:
				_fail("a selected location requires a two-letter uppercase country code", "location.countryCode", "invalidLocation")
		elif settings.location.country_code is not None:
			_fail("a custom location must not carry a bundled country code", "location.countryCode", "invalidLocation")
	general = settings.general
	_require_type(general, GeneralSettings, "general")
	_require_bool(general.all_automatic_alerts_enabled, "general.allAutomaticAlertsEnabled")
	quiet = general.quiet_hours
	_require_type(quiet, QuietHoursSettings, "general.quietHours")
	_require_bool(quiet.enabled, "general.quietHours.enabled")
	_require_bool(quiet.apply_to_prayer_alerts, "general.quietHours.applyToPrayerAlerts")
	for name, value in (("start", quiet.start), ("end", quiet.end)):
		_require_type(value, ClockTime, f"general.quietHours.{name}")
		_require_int(value.hour, 0, 23, f"general.quietHours.{name}.hour")
		_require_int(value.minute, 0, 59, f"general.quietHours.{name}.minute")

	prayer = settings.prayer
	_require_type(prayer, PrayerSettings, "prayer")
	_require_bool(prayer.alerts_enabled, "prayer.alertsEnabled")
	for path, value, kind in (
		("prayer.calculationMethod", prayer.calculation_method, CalculationMethod),
		("prayer.asrMethod", prayer.asr_method, AsrMethod),
		("prayer.highLatitudeRule", prayer.high_latitude_rule, HighLatitudeRule),
	):
		if not isinstance(value, kind):
			_fail(f"{path} is invalid", path, "invalidChoice")
	_validate_exact_keys(prayer.corrections_minutes, set(PrayerEventName), "prayer.correctionsMinutes")
	for name in PrayerEventName:
		value = prayer.corrections_minutes[name]
		_require_int(value, MIN_USER_CORRECTION_MINUTES, MAX_USER_CORRECTION_MINUTES,
			f"prayer.correctionsMinutes.{name.value}")
	_validate_exact_keys(prayer.events, set(PrayerEventName), "prayer.events")
	prayer_actions = set(AlertAction)
	for name in PrayerEventName:
		event = prayer.events[name]
		_require_type(event, PrayerEventAlertSettings, f"prayer.events.{name.value}")
		_require_int(event.pre_alert_minutes, 0, MAX_DURATION_MINUTES,
			f"prayer.events.{name.value}.preAlertMinutes")
		_validate_output(event.pre_alert, prayer_actions, f"prayer.events.{name.value}.preAlert")
		_validate_output(event.at_time_alert, prayer_actions, f"prayer.events.{name.value}.atTimeAlert")
		if name in PRAYER_EVENT_NAMES:
			if event.iqama is None or event.post_alert_minutes is not None or event.post_alert is not None:
				_fail(f"prayer.events.{name.value} must use Iqama and no post alert", f"prayer.events.{name.value}", "invalidShape")
			_require_int(event.iqama.delay_minutes, 0, MAX_DURATION_MINUTES,
				f"prayer.events.{name.value}.iqama.delayMinutes")
			_require_int(event.iqama.alert_before_minutes, 0, MAX_DURATION_MINUTES,
				f"prayer.events.{name.value}.iqama.alertBeforeMinutes")
			if event.iqama.delay_minutes > 0 and event.iqama.alert_before_minutes >= event.iqama.delay_minutes:
				_fail(f"prayer.events.{name.value}.iqama.alertBeforeMinutes must be below the Iqama delay", f"prayer.events.{name.value}.iqama.alertBeforeMinutes", "iqamaBeforeDelay")
			_validate_output(event.iqama.alert, prayer_actions, f"prayer.events.{name.value}.iqama.alert")
		else:
			if event.iqama is not None or event.post_alert_minutes is None or event.post_alert is None:
				_fail(f"prayer.events.{name.value} must use a post alert and no Iqama", f"prayer.events.{name.value}", "invalidShape")
			_require_int(event.post_alert_minutes, 0, MAX_DURATION_MINUTES,
				f"prayer.events.{name.value}.postAlertMinutes")
			_validate_output(event.post_alert, prayer_actions, f"prayer.events.{name.value}.postAlert")
	_require_int(prayer.current_prayer_after_iqama_minutes, 0, MAX_DURATION_MINUTES,
		"prayer.currentPrayerAfterIqamaMinutes")

	clock = settings.clock
	_require_type(clock, ClockSettings, "clock")
	_require_bool(clock.automatic_alert_enabled, "clock.automaticAlertEnabled")
	_validate_exact_keys(clock.presentations, set(ClockType), "clock.presentations")
	for identity in ClockType:
		presentation = clock.presentations[identity]
		_require_type(presentation, ClockPresentationSettings, f"clock.presentations.{identity.value}")
		for path, value, kind in (
			("style", presentation.style, AnnouncementStyle),
			("hourSystem", presentation.hour_system, HourSystem),
			("representation", presentation.representation, TimeRepresentation),
		):
			if not isinstance(value, kind):
				_fail(f"clock.presentations.{identity.value}.{path} is invalid", f"clock.presentations.{identity.value}.{path}", "invalidChoice")
		_require_bool(presentation.speak_seconds, f"clock.presentations.{identity.value}.speakSeconds")
		_require_bool(presentation.speak_zero_minute, f"clock.presentations.{identity.value}.speakZeroMinute")
	_require_type(clock.intervals, ClockChimeIntervals, "clock.intervals")
	for name in ("on_hour", "on_quarter", "on_half", "on_three_quarters"):
		_require_bool(getattr(clock.intervals, name), f"clock.intervals.{name}")
	_validate_output(clock.alert, {AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH}, "clock.alert")

	calendar = settings.calendar
	_require_type(calendar, CalendarSettings, "calendar")
	if not isinstance(calendar.primary_calendar, CalendarId) or calendar.primary_calendar not in {
			CalendarId.GREGORIAN, CalendarId.HIJRI_UMM_AL_QURA,
	}:
		_fail("calendar.primaryCalendar must be Gregorian or lunar Hijri", "calendar.primaryCalendar", "invalidChoice")
	_validate_exact_keys(calendar.formats, set(CalendarId), "calendar.formats")
	if any(not isinstance(value, DateFormat) for value in calendar.formats.values()):
		bad = next(identity for identity in CalendarId if not isinstance(calendar.formats[identity], DateFormat))
		_fail("calendar formats must use known neutral values", f"calendar.formats.{bad.value}", "invalidChoice")
	_require_int(calendar.hijri_adjustment_days, -2, 2, "calendar.hijriAdjustmentDays")
	_require_bool(calendar.include_arabian_calendar_in_daily_info,
		"calendar.includeArabianCalendarInDailyInfo")

	adhkar = settings.adhkar
	_require_type(adhkar, AdhkarSettings, "adhkar")
	_require_bool(adhkar.alerts_enabled, "adhkar.alertsEnabled")
	timed_allowed = {AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH}
	for name, value, reference_type in (
		("morning", adhkar.morning, MorningReference),
		("evening", adhkar.evening, EveningReference),
		("fridayHour", adhkar.friday_hour, FridayReference),
	):
		_require_type(value, TimedDhikrSettings, f"adhkar.{name}")
		_require_bool(value.enabled, f"adhkar.{name}.enabled")
		if not isinstance(value.reference, reference_type):
			_fail(f"adhkar.{name}.reference is invalid", f"adhkar.{name}.reference", "invalidChoice")
		_require_int(value.minutes, 0, MAX_DURATION_MINUTES, f"adhkar.{name}.minutes")
		_validate_output(value.alert, timed_allowed, f"adhkar.{name}.alert")
	wird = adhkar.daily_wird
	_require_type(wird, DailyWirdSettings, "adhkar.dailyWird")
	_require_bool(wird.enabled, "adhkar.dailyWird.enabled")
	if not isinstance(wird.text, str):
		_fail("adhkar.dailyWird.text must be text", "adhkar.dailyWird.text", "invalidType")
	_require_int(wird.hour, 1, 12, "adhkar.dailyWird.hour")
	_require_int(wird.minute, 0, 59, "adhkar.dailyWird.minute")
	if not isinstance(wird.period, DayPeriod):
		_fail("adhkar.dailyWird.period is invalid", "adhkar.dailyWird.period", "invalidChoice")
	_validate_output(wird.alert, timed_allowed, "adhkar.dailyWird.alert")
	recurring = adhkar.recurring
	_require_type(recurring, RecurringDhikrSettings, "adhkar.recurring")
	_require_bool(recurring.enabled, "adhkar.recurring.enabled")
	_require_int(recurring.interval_minutes, 5, 1440, "adhkar.recurring.intervalMinutes")
	_validate_exact_keys(recurring.items, set(RecurringDhikrId), "adhkar.recurring.items")
	for identity in RecurringDhikrId:
		item = recurring.items[identity]
		_require_type(item, RecurringDhikrItemSettings, f"adhkar.recurring.items.{identity.value}")
		_require_bool(item.enabled, f"adhkar.recurring.items.{identity.value}.enabled")
		_validate_output(item.alert, {AlertAction.SPEECH, AlertAction.SOUND},
			f"adhkar.recurring.items.{identity.value}.alert")
