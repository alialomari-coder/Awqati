"""Language-neutral identities and visibility rules for the task 3.3 settings UI."""

from __future__ import annotations

from enum import Enum

from ..domain import AlertAction, CalendarId, DateFormat, PrayerEventName, RecurringDhikrId


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
