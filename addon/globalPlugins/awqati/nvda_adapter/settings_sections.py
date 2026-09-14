"""Language-neutral identities and visibility rules for the task 3.3 settings UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain import AlertAction, CalendarId, ClockType, DateFormat, PrayerEventName, RecurringDhikrId


class SettingsSection(Enum):
	PRAYER = "prayer"
	CLOCK = "clock"
	DATE = "date"
	ADHKAR = "adhkar"


SECTION_ORDER = (
	SettingsSection.PRAYER,
	SettingsSection.CLOCK,
	SettingsSection.DATE,
	SettingsSection.ADHKAR,
)

PRAYER_EVENT_ORDER = (
	PrayerEventName.FAJR,
	PrayerEventName.SUNRISE,
	PrayerEventName.DHUHR,
	PrayerEventName.ASR,
	PrayerEventName.MAGHRIB,
	PrayerEventName.ISHA,
	PrayerEventName.MIDNIGHT,
	PrayerEventName.LAST_THIRD,
)

CALENDAR_EDIT_ORDER = (
	CalendarId.HIJRI_UMM_AL_QURA,
	CalendarId.GREGORIAN,
	CalendarId.SAUDI_SOLAR_HIJRI,
	CalendarId.AFGHAN_SOLAR_HIJRI,
	CalendarId.PERSIAN_SOLAR_HIJRI,
)

PRIMARY_CALENDAR_ORDER = (CalendarId.HIJRI_UMM_AL_QURA, CalendarId.GREGORIAN)

RECURRING_DHIKR_ORDER = tuple(RecurringDhikrId)

PRAYER_ACTIONS = tuple(AlertAction)
STANDARD_ALERT_ACTIONS = (AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH)
RECURRING_ACTIONS = (AlertAction.SPEECH, AlertAction.SOUND)


def action_uses_sound(action: AlertAction) -> bool:
	return action in {AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH}


def hijri_adjustment_visible(calendar_id: CalendarId, date_format: DateFormat) -> bool:
	return calendar_id is CalendarId.HIJRI_UMM_AL_QURA or date_format is DateFormat.DOUBLE


def is_rtl_language(language: str) -> bool:
	"""Return the explicit page direction for the supported UI language."""
	return language.split("_", 1)[0].split("-", 1)[0].casefold() == "ar"


@dataclass(frozen=True, slots=True)
class SettingsFocusTarget:
	control_key: str
	section: SettingsSection | None = None
	prayer_event: PrayerEventName | None = None
	clock_type: ClockType | None = None
	calendar_id: CalendarId | None = None
	adhkar_function: str | None = None
	recurring_item: RecurringDhikrId | None = None


def focus_target_for_path(path: str) -> SettingsFocusTarget:
	"""Map one neutral validation path to the UI state needed to expose it."""
	if path.startswith("location."):
		return SettingsFocusTarget("location")
	if path == "general.allAutomaticAlertsEnabled":
		return SettingsFocusTarget("allAlerts")
	if path == "general.quietHours.enabled":
		return SettingsFocusTarget("quietEnabled")
	if path.startswith("general.quietHours.start"):
		return SettingsFocusTarget("quietStart")
	if path.startswith("general.quietHours.end"):
		return SettingsFocusTarget("quietEnd")
	if path == "general.quietHours.applyToPrayerAlerts":
		return SettingsFocusTarget("quietPrayer")
	parts = path.split(".")
	if parts[0] == "prayer":
		if len(parts) >= 3 and parts[1] == "correctionsMinutes":
			return SettingsFocusTarget("prayer.correction", SettingsSection.PRAYER,
				prayer_event=_enum_or_none(PrayerEventName, parts[2]))
		if len(parts) >= 4 and parts[1] == "events":
			event = _enum_or_none(PrayerEventName, parts[2])
			suffix = ".".join(parts[3:])
			key = {
				"preAlertMinutes": "prayer.preMinutes",
				"preAlert.action": "prayer.pre.action",
				"preAlert.sound": "prayer.pre.sound",
				"atTimeAlert.action": "prayer.atTime.action",
				"atTimeAlert.sound": "prayer.atTime.sound",
				"iqama.delayMinutes": "prayer.iqamaDelay",
				"iqama.alertBeforeMinutes": "prayer.iqamaBefore",
				"iqama.alert.action": "prayer.iqama.action",
				"iqama.alert.sound": "prayer.iqama.sound",
				"postAlertMinutes": "prayer.postMinutes",
				"postAlert.action": "prayer.post.action",
				"postAlert.sound": "prayer.post.sound",
			}.get(suffix, "prayer.event")
			return SettingsFocusTarget(key, SettingsSection.PRAYER, prayer_event=event)
		return SettingsFocusTarget({
			"calculationMethod": "prayer.calculationMethod",
			"asrMethod": "prayer.asrMethod",
			"highLatitudeRule": "prayer.highLatitudeRule",
			"currentPrayerAfterIqamaMinutes": "prayer.currentDuration",
			"openDailyPrayerTimesWindow": "prayer.openDailyPrayerTimesWindow",
			"alertsEnabled": "prayer.enabled",
		}.get(parts[1] if len(parts) > 1 else "", "section"),
			SettingsSection.PRAYER)
	if parts[0] == "clock":
		if len(parts) >= 4 and parts[1] == "presentations":
			return SettingsFocusTarget(
				"clock." + parts[3],
				SettingsSection.CLOCK,
				clock_type=_enum_or_none(ClockType, parts[2]),
			)
		if len(parts) >= 3 and parts[1] == "alert":
			return SettingsFocusTarget("clock.alert." + parts[2], SettingsSection.CLOCK)
		if len(parts) >= 3 and parts[1] == "intervals":
			return SettingsFocusTarget("clock.interval." + parts[2], SettingsSection.CLOCK)
		return SettingsFocusTarget("clock.enabled", SettingsSection.CLOCK)
	if parts[0] == "calendar":
		if len(parts) >= 3 and parts[1] == "formats":
			return SettingsFocusTarget("calendar.format", SettingsSection.DATE,
				calendar_id=_enum_or_none(CalendarId, parts[2]))
		return SettingsFocusTarget({
			"primaryCalendar": "calendar.primary",
			"hijriAdjustmentDays": "calendar.adjustment",
			"includeArabianCalendarInDailyInfo": "calendar.includeArabian",
			"openDailyInfoWindow": "calendar.openDailyInfoWindow",
		}.get(parts[1] if len(parts) > 1 else "", "section"), SettingsSection.DATE,
			calendar_id=(CalendarId.HIJRI_UMM_AL_QURA
				if len(parts) > 1 and parts[1] == "hijriAdjustmentDays" else None))
	if parts[0] == "adhkar":
		name = parts[1] if len(parts) > 1 else ""
		if name == "alertsEnabled":
			return SettingsFocusTarget("adhkar.enabled", SettingsSection.ADHKAR)
		function = {"fridayHour": "friday", "dailyWird": "wird"}.get(name, name)
		if name == "recurring" and len(parts) >= 5 and parts[2] == "items":
			key = "recurring.item." + parts[-1]
			return SettingsFocusTarget(key, SettingsSection.ADHKAR, adhkar_function="recurring",
				recurring_item=_enum_or_none(RecurringDhikrId, parts[3]))
		key = {
			"enabled": "enabled",
			"reference": "reference",
			"minutes": "minutes",
			"text": "text",
			"hour": "hour",
			"minute": "minute",
			"period": "period",
			"intervalMinutes": "interval",
			"action": "action",
			"sound": "sound",
		}.get(parts[-1], "enabled")
		return SettingsFocusTarget(f"{function}.{key}", SettingsSection.ADHKAR,
			adhkar_function=function)
	return SettingsFocusTarget("section")


def _enum_or_none(enum_type, value: str):
	try:
		return enum_type(value)
	except ValueError:
		return None
