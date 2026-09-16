from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import sys

PACKAGES = Path(__file__).resolve().parents[1] / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))

from awqati.domain import (  # noqa: E402
	AlertAction,
	AnnouncementStyle,
	CalendarId,
	DateFormat,
	DayPeriod,
	EveningReference,
	MorningReference,
	PrayerEventName,
	RecurringDhikrId,
	SETTINGS_SCHEMA_VERSION,
	SettingsValidationError,
	SoundReference,
	default_settings,
	validate_settings,
)


class SettingsDefaultsTests(unittest.TestCase):
	def setUp(self) -> None:
		self.settings = default_settings()

	def test_schema_general_hierarchy_and_quiet_hours_defaults(self) -> None:
		self.assertEqual(self.settings.schema_version, SETTINGS_SCHEMA_VERSION, 1)
		self.assertIsNone(self.settings.location)
		self.assertTrue(self.settings.general.all_automatic_alerts_enabled)
		self.assertFalse(self.settings.general.quiet_hours.enabled)
		self.assertFalse(self.settings.general.quiet_hours.apply_to_prayer_alerts)
		self.assertTrue(self.settings.prayer.alerts_enabled)
		self.assertFalse(self.settings.clock.automatic_alert_enabled)
		self.assertTrue(self.settings.adhkar.alerts_enabled)

	def test_all_eight_events_have_ten_minute_pre_alerts(self) -> None:
		self.assertEqual(set(self.settings.prayer.events), set(PrayerEventName))
		self.assertEqual({event.pre_alert_minutes for event in self.settings.prayer.events.values()}, {10})

	def test_iqama_and_current_prayer_defaults(self) -> None:
		expected = {
			PrayerEventName.FAJR: 25,
			PrayerEventName.DHUHR: 20,
			PrayerEventName.ASR: 20,
			PrayerEventName.MAGHRIB: 10,
			PrayerEventName.ISHA: 20,
		}
		self.assertEqual({
			name: event.iqama.delay_minutes for name, event in self.settings.prayer.events.items()
			if event.iqama is not None
		}, expected)
		self.assertTrue(all(event.iqama.alert_before_minutes == 5
			for event in self.settings.prayer.events.values() if event.iqama is not None))
		self.assertEqual(self.settings.prayer.current_prayer_after_iqama_minutes, 20)

	def test_point_event_post_alert_defaults(self) -> None:
		self.assertEqual(self.settings.prayer.events[PrayerEventName.SUNRISE].post_alert_minutes, 20)
		self.assertEqual(self.settings.prayer.events[PrayerEventName.MIDNIGHT].post_alert_minutes, 0)
		self.assertEqual(self.settings.prayer.events[PrayerEventName.LAST_THIRD].post_alert_minutes, 0)

	def test_clock_and_calendar_defaults(self) -> None:
		for presentation in self.settings.clock.presentations.values():
			self.assertIs(presentation.style, AnnouncementStyle.DOUBLE)
			self.assertEqual(presentation.hour_system.value, 12)
			self.assertEqual(presentation.representation.value, "numeric")
			self.assertFalse(presentation.speak_seconds)
			self.assertFalse(presentation.speak_zero_minute)
		self.assertIs(self.settings.calendar.primary_calendar, CalendarId.HIJRI_UMM_AL_QURA)
		self.assertEqual(set(self.settings.calendar.formats), set(CalendarId))
		self.assertEqual(set(self.settings.calendar.formats.values()), {DateFormat.DOUBLE})
		self.assertEqual(self.settings.calendar.hijri_adjustment_days, 0)
		self.assertFalse(self.settings.calendar.include_arabian_calendar_in_daily_info)

	def test_adhkar_function_defaults(self) -> None:
		adhkar = self.settings.adhkar
		self.assertFalse(adhkar.morning.enabled)
		self.assertIs(adhkar.morning.reference, MorningReference.BEFORE_SUNRISE)
		self.assertEqual(adhkar.morning.minutes, 15)
		self.assertFalse(adhkar.evening.enabled)
		self.assertIs(adhkar.evening.reference, EveningReference.BEFORE_MAGHRIB)
		self.assertEqual(adhkar.evening.minutes, 15)
		self.assertFalse(adhkar.friday_hour.enabled)
		self.assertEqual(adhkar.friday_hour.minutes, 60)
		self.assertFalse(adhkar.daily_wird.enabled)
		self.assertEqual(adhkar.daily_wird.text, "Do not forget your daily Wird.")
		self.assertEqual((adhkar.daily_wird.hour, adhkar.daily_wird.minute, adhkar.daily_wird.period),
			(10, 0, DayPeriod.PM))

	def test_recurring_dhikr_defaults_are_complete_and_independent(self) -> None:
		recurring = self.settings.adhkar.recurring
		self.assertFalse(recurring.enabled)
		self.assertEqual(recurring.interval_minutes, 60)
		self.assertEqual(set(recurring.items), set(RecurringDhikrId))
		self.assertTrue(all(item.enabled for item in recurring.items.values()))
		self.assertEqual({item.alert.action for item in recurring.items.values()}, {AlertAction.SPEECH})
		self.assertEqual({item.alert.sound for item in recurring.items.values()}, {None})
		self.assertEqual(len({id(item) for item in recurring.items.values()}), len(RecurringDhikrId))


class SettingsValidationTests(unittest.TestCase):
	def assert_invalid(self, mutate) -> None:
		settings = default_settings()
		mutate(settings)
		with self.assertRaises(SettingsValidationError):
			validate_settings(settings)

	def test_duration_bounds_accept_zero_and_180(self) -> None:
		for value in (0, 180):
			settings = default_settings()
			settings.adhkar.morning.minutes = value
			settings.prayer.current_prayer_after_iqama_minutes = value
			validate_settings(settings)
		for value in (-1, 181):
			self.assert_invalid(lambda settings, value=value: setattr(settings.adhkar.morning, "minutes", value))

	def test_recurring_interval_bounds(self) -> None:
		for value in (5, 1440):
			settings = default_settings()
			settings.adhkar.recurring.interval_minutes = value
			validate_settings(settings)
		for value in (4, 1441):
			self.assert_invalid(lambda settings, value=value: setattr(
				settings.adhkar.recurring, "interval_minutes", value))

	def test_daily_wird_clock_bounds(self) -> None:
		for hour, minute in ((1, 0), (12, 59)):
			settings = default_settings()
			settings.adhkar.daily_wird.hour = hour
			settings.adhkar.daily_wird.minute = minute
			validate_settings(settings)
		for field_name, value in (("hour", 0), ("hour", 13), ("minute", -1), ("minute", 60)):
			self.assert_invalid(lambda settings, field_name=field_name, value=value: setattr(
				settings.adhkar.daily_wird, field_name, value))

	def test_hijri_adjustment_bounds_and_primary_calendar(self) -> None:
		for value in (-2, 2):
			settings = default_settings()
			settings.calendar.hijri_adjustment_days = value
			validate_settings(settings)
		for value in (-3, 3):
			self.assert_invalid(lambda settings, value=value: setattr(
				settings.calendar, "hijri_adjustment_days", value))
		self.assert_invalid(lambda settings: setattr(
			settings.calendar, "primary_calendar", CalendarId.SAUDI_SOLAR_HIJRI))
		self.assert_invalid(lambda settings: setattr(settings.calendar, "primary_calendar", "UNKNOWN"))

	def test_contextual_alert_actions(self) -> None:
		self.assert_invalid(lambda settings: setattr(settings.clock.alert, "action", AlertAction.SILENT))
		self.assert_invalid(lambda settings: setattr(settings.adhkar.morning.alert, "action", AlertAction.SILENT))
		item_id = next(iter(RecurringDhikrId))
		self.assert_invalid(lambda settings: setattr(
			settings.adhkar.recurring.items[item_id].alert, "action", AlertAction.SOUND_AND_SPEECH))
		settings = default_settings()
		settings.prayer.events[PrayerEventName.FAJR].pre_alert.action = AlertAction.SILENT
		validate_settings(settings)
		self.assert_invalid(lambda settings: setattr(settings.clock.alert, "action", "speech"))

	def test_iqama_relationship_and_zero_semantics(self) -> None:
		for before in (20, 21):
			self.assert_invalid(lambda settings, before=before: setattr(
				settings.prayer.events[PrayerEventName.DHUHR].iqama, "alert_before_minutes", before))
		settings = default_settings()
		iqama = settings.prayer.events[PrayerEventName.DHUHR].iqama
		iqama.delay_minutes = 0
		iqama.alert_before_minutes = 180
		validate_settings(settings)
		settings = default_settings()
		settings.prayer.events[PrayerEventName.DHUHR].iqama.alert_before_minutes = 0
		validate_settings(settings)
		self.assertEqual(settings.prayer.events[PrayerEventName.DHUHR].iqama.delay_minutes, 20)

	def test_zero_has_distinct_post_alert_and_timed_dhikr_meanings(self) -> None:
		settings = default_settings()
		settings.prayer.events[PrayerEventName.SUNRISE].post_alert_minutes = 0
		settings.adhkar.morning.minutes = 0
		validate_settings(settings)
		self.assertEqual(settings.prayer.events[PrayerEventName.SUNRISE].post_alert_minutes, 0)
		self.assertTrue(settings.prayer.events[PrayerEventName.SUNRISE].post_alert is not None)
		self.assertEqual(settings.adhkar.morning.minutes, 0)

	def test_sound_references_reject_absolute_traversal_and_wrong_roots(self) -> None:
		for value in ("C:/Users/name/file.wav", "/sounds/alerts/file.wav", "sounds/../file.wav",
				"sounds/alerts/C:/file.wav", "sounds\\alerts\\file.wav", "other/file.wav"):
			self.assert_invalid(lambda settings, value=value: setattr(
				settings.adhkar.daily_wird.alert, "sound", SoundReference(value)))
		for value in ("sounds/adhan/fajr.wav", "sounds/alerts/clock.wav", "sounds/adhkar/item.wav"):
			settings = default_settings()
			settings.adhkar.daily_wird.alert.sound = SoundReference(value)
			validate_settings(settings)

	def test_disabling_hierarchy_does_not_erase_children(self) -> None:
		settings = default_settings()
		item = settings.adhkar.recurring.items[RecurringDhikrId.ASTAGHFIRU_ALLAH]
		item.alert.action = AlertAction.SOUND
		item.alert.sound = SoundReference("sounds/adhkar/istighfar.wav")
		before = deepcopy(settings.adhkar)
		settings.general.all_automatic_alerts_enabled = False
		settings.adhkar.alerts_enabled = False
		settings.adhkar.recurring.enabled = False
		validate_settings(settings)
		self.assertEqual(settings.adhkar.recurring.items, before.recurring.items)


if __name__ == "__main__":
	unittest.main()
