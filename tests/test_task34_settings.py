from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))
sys.path.insert(0, str(ROOT / "tests"))

from awqati.application import (  # noqa: E402
	CustomLocationValidationError,
	EventDispatcher,
	LocationSetupService,
	SettingsService,
)
from awqati.domain import (  # noqa: E402
	AlertAction,
	CalendarId,
	ClockType,
	DayPeriod,
	Instant,
	Location,
	LocationKind,
	PrayerEventName,
	RecurringDhikrId,
	SettingsApplied,
	SettingsValidationError,
	StoredLocation,
	default_settings,
	validate_settings,
)
from awqati.nvda_adapter.settings_sections import (  # noqa: E402
	SettingsSection,
	focus_target_for_path,
	is_rtl_language,
)
from support.event_clock import EventClock  # noqa: E402


class MemoryRepository:
	def __init__(self, settings=None) -> None:
		self.value = deepcopy(settings or default_settings())
		self.saved = []
		self.failure = None

	def load(self):
		return deepcopy(self.value)

	def save(self, settings) -> None:
		if self.failure is not None:
			raise self.failure
		self.value = deepcopy(settings)
		self.saved.append(deepcopy(settings))


class Timezones:
	def get_timezone(self, timezone_id):
		if timezone_id not in {"Asia/Riyadh", "Etc/UTC"}:
			raise ValueError("unknown timezone")
		return timezone.utc

	def timezone_ids(self):
		return ("Asia/Riyadh", "Etc/UTC")


class EmptyLocations:
	def countries(self):
		return ()

	def search(self, country_code, query, limit=20):
		return ()

	def get(self, country_code, location_id):
		return None

	def nearest(self, latitude, longitude):
		raise AssertionError("not used")


class NoCoordinates:
	def get_coordinates(self):
		raise AssertionError("not used")


class StructuredValidationTests(unittest.TestCase):
	def assert_error(self, settings, path: str, code: str | None = None) -> SettingsValidationError:
		with self.assertRaises(SettingsValidationError) as caught:
			validate_settings(settings)
		self.assertEqual(caught.exception.path, path)
		if code is not None:
			self.assertEqual(caught.exception.code, code)
		return caught.exception

	def test_iqama_boundary_matrix_and_structured_relationship_error(self) -> None:
		for delay, before in ((20, 0), (20, 1), (20, 19), (0, 0), (0, 180)):
			settings = default_settings()
			iqama = settings.prayer.events[PrayerEventName.DHUHR].iqama
			iqama.delay_minutes, iqama.alert_before_minutes = delay, before
			validate_settings(settings)
		for before in (20, 21):
			settings = default_settings()
			settings.prayer.events[PrayerEventName.DHUHR].iqama.alert_before_minutes = before
			self.assert_error(
				settings,
				"prayer.events.dhuhr.iqama.alertBeforeMinutes",
				"iqamaBeforeDelay",
			)

	def test_all_timed_dhikr_boundaries_are_model_enforced(self) -> None:
		for name in ("morning", "evening", "friday_hour"):
			for valid in (0, 180):
				settings = default_settings()
				setattr(getattr(settings.adhkar, name), "minutes", valid)
				validate_settings(settings)
			for invalid in (-1, 181):
				settings = default_settings()
				setattr(getattr(settings.adhkar, name), "minutes", invalid)
				logical = "fridayHour" if name == "friday_hour" else name
				self.assert_error(settings, f"adhkar.{logical}.minutes", "outOfRange")

	def test_remaining_numeric_boundaries_and_daily_wird_period(self) -> None:
		settings = default_settings()
		settings.prayer.events[PrayerEventName.SUNRISE].post_alert_minutes = 180
		settings.prayer.events[PrayerEventName.FAJR].pre_alert_minutes = 0
		settings.prayer.current_prayer_after_iqama_minutes = 180
		settings.prayer.corrections_minutes[PrayerEventName.LAST_THIRD] = -30
		settings.calendar.hijri_adjustment_days = 2
		settings.adhkar.recurring.interval_minutes = 1440
		settings.adhkar.daily_wird.hour = 12
		settings.adhkar.daily_wird.minute = 59
		settings.adhkar.daily_wird.period = DayPeriod.AM
		validate_settings(settings)
		cases = (
			("prayer.events.sunrise.postAlertMinutes", lambda s: setattr(s.prayer.events[PrayerEventName.SUNRISE], "post_alert_minutes", 181)),
			("prayer.events.fajr.preAlertMinutes", lambda s: setattr(s.prayer.events[PrayerEventName.FAJR], "pre_alert_minutes", -1)),
			("prayer.currentPrayerAfterIqamaMinutes", lambda s: setattr(s.prayer, "current_prayer_after_iqama_minutes", 181)),
			("prayer.correctionsMinutes.fajr", lambda s: s.prayer.corrections_minutes.__setitem__(PrayerEventName.FAJR, 31)),
			("calendar.hijriAdjustmentDays", lambda s: setattr(s.calendar, "hijri_adjustment_days", -3)),
			("adhkar.recurring.intervalMinutes", lambda s: setattr(s.adhkar.recurring, "interval_minutes", 4)),
			("adhkar.dailyWird.hour", lambda s: setattr(s.adhkar.daily_wird, "hour", 0)),
			("adhkar.dailyWird.minute", lambda s: setattr(s.adhkar.daily_wird, "minute", 60)),
			("adhkar.dailyWird.period", lambda s: setattr(s.adhkar.daily_wird, "period", "AM")),
		)
		for path, mutate in cases:
			with self.subTest(path=path):
				invalid = default_settings()
				mutate(invalid)
				self.assert_error(invalid, path)

	def test_contextual_actions_reject_programmatic_incompatibility(self) -> None:
		cases = (
			("clock.alert.action", lambda s: setattr(s.clock.alert, "action", AlertAction.SILENT)),
			("adhkar.morning.alert.action", lambda s: setattr(s.adhkar.morning.alert, "action", AlertAction.SILENT)),
			("adhkar.evening.alert.action", lambda s: setattr(s.adhkar.evening.alert, "action", AlertAction.SILENT)),
			("adhkar.fridayHour.alert.action", lambda s: setattr(s.adhkar.friday_hour.alert, "action", AlertAction.SILENT)),
			("adhkar.dailyWird.alert.action", lambda s: setattr(s.adhkar.daily_wird.alert, "action", AlertAction.SILENT)),
			("adhkar.recurring.items.subhanAllah.alert.action", lambda s: setattr(
				s.adhkar.recurring.items[RecurringDhikrId.SUBHAN_ALLAH].alert,
				"action",
				AlertAction.SOUND_AND_SPEECH,
			)),
		)
		for path, mutate in cases:
			with self.subTest(path=path):
				settings = default_settings()
				mutate(settings)
				self.assert_error(settings, path, "invalidChoice")

	def test_first_error_order_is_deterministic_even_for_reordered_dicts(self) -> None:
		settings = default_settings()
		settings.prayer.events[PrayerEventName.FAJR].pre_alert_minutes = 181
		settings.prayer.events[PrayerEventName.DHUHR].pre_alert_minutes = 181
		settings.prayer.events = dict(reversed(tuple(settings.prayer.events.items())))
		error = self.assert_error(settings, "prayer.events.fajr.preAlertMinutes")
		self.assertEqual(error.code, "outOfRange")

	def test_mutated_location_fields_and_syntax_are_rejected_by_domain(self) -> None:
		base = Location("custom:1", "Home", 24.0, 46.0, "Asia/Riyadh")
		for field, value, path in (
			("name", " ", "location.location.name"),
			("latitude", 91.0, "location.location.latitude"),
			("longitude", 181.0, "location.location.longitude"),
			("timezone_id", "../bad", "location.location.timezoneId"),
		):
			location = deepcopy(base)
			object.__setattr__(location, field, value)
			settings = default_settings()
			settings.location = StoredLocation(LocationKind.CUSTOM, location)
			self.assert_error(settings, path)


class ApplyCancelTests(unittest.TestCase):
	def setUp(self) -> None:
		self.repository = MemoryRepository()
		self.clock = EventClock(Instant(datetime(2026, 9, 14, tzinfo=timezone.utc)))
		self.events = EventDispatcher()
		self.service = SettingsService(
			self.repository,
			self.clock,
			self.events,
			valid_timezone_ids={"Asia/Riyadh", "Etc/UTC"},
		)

	def test_invalid_bundled_timezone_writes_publishes_and_changes_nothing(self) -> None:
		applied_events = []
		self.events.subscribe(SettingsApplied, applied_events.append)
		draft = self.service.open_draft()
		draft.settings.location = StoredLocation(
			LocationKind.CUSTOM,
			Location("custom:1", "Home", 24.0, 46.0, "Bad/Zone"),
		)
		with self.assertRaises(SettingsValidationError) as caught:
			self.service.apply(draft)
		self.assertEqual(caught.exception.path, "location.location.timezoneId")
		self.assertEqual(self.repository.saved, [])
		self.assertEqual(applied_events, [])
		self.assertIsNone(self.service.runtime_settings.location)
		self.assertIsNone(draft.base.location)

	def test_apply_preserves_live_draft_objects_and_cancel_keeps_last_apply(self) -> None:
		draft = self.service.open_draft()
		morning = draft.settings.adhkar.morning
		morning.enabled = True
		morning.minutes = 17
		self.service.apply(draft)
		self.assertIs(draft.settings.adhkar.morning, morning)
		self.assertEqual(draft.base.adhkar.morning.minutes, 17)
		morning.minutes = 23
		draft.discard()
		self.assertEqual(self.service.runtime_settings.adhkar.morning.minutes, 17)
		self.assertEqual(self.repository.value.adhkar.morning.minutes, 17)
		self.assertEqual(len(self.repository.saved), 1)


class CustomLocationValidationTests(unittest.TestCase):
	def setUp(self) -> None:
		self.service = LocationSetupService(EmptyLocations(), Timezones(), NoCoordinates())

	def test_first_invalid_custom_location_field_is_typed_and_ordered(self) -> None:
		cases = (
			(("", "bad", "bad", "Bad/Zone"), "name"),
			(("Home", "bad", "bad", "Bad/Zone"), "latitude"),
			(("Home", "24", "bad", "Bad/Zone"), "longitude"),
			(("Home", "24", "46", "Bad/Zone"), "timezone"),
		)
		for args, field in cases:
			with self.subTest(field=field), self.assertRaises(CustomLocationValidationError) as caught:
				self.service.custom(*args)
			self.assertEqual(caught.exception.field, field)


class FocusAndAccessibilityContractTests(unittest.TestCase):
	def assert_target(self, path, key, section=None, **selectors) -> None:
		target = focus_target_for_path(path)
		self.assertEqual(target.control_key, key)
		self.assertIs(target.section, section)
		for name, value in selectors.items():
			self.assertEqual(getattr(target, name), value)

	def test_validation_paths_select_the_correct_dynamic_control(self) -> None:
		self.assert_target(
			"prayer.events.dhuhr.iqama.alertBeforeMinutes",
			"prayer.iqamaBefore",
			SettingsSection.PRAYER,
			prayer_event=PrayerEventName.DHUHR,
		)
		self.assert_target("adhkar.morning.minutes", "morning.minutes",
			SettingsSection.ADHKAR, adhkar_function="morning")
		self.assert_target("adhkar.dailyWird.hour", "wird.hour",
			SettingsSection.ADHKAR, adhkar_function="wird")
		self.assert_target("adhkar.recurring.intervalMinutes", "recurring.interval",
			SettingsSection.ADHKAR, adhkar_function="recurring")
		self.assert_target(
			"adhkar.recurring.items.astaghfiruAllah.alert.action",
			"recurring.item.action",
			SettingsSection.ADHKAR,
			adhkar_function="recurring",
			recurring_item=RecurringDhikrId.ASTAGHFIRU_ALLAH,
		)
		self.assert_target("clock.presentations.ghurubi.hourSystem", "clock.hourSystem",
			SettingsSection.CLOCK, clock_type=ClockType.GHURUBI)
		self.assert_target("calendar.formats.PERSIAN_SOLAR_HIJRI", "calendar.format",
			SettingsSection.DATE, calendar_id=CalendarId.PERSIAN_SOLAR_HIJRI)
		self.assert_target("general.quietHours.end.minute", "quietEnd")
		self.assert_target("location.location.timezoneId", "location")

	def test_arabic_is_rtl_and_english_is_ltr(self) -> None:
		for language in ("ar", "ar_SA", "ar-SA"):
			self.assertTrue(is_rtl_language(language))
		for language in ("en", "en_US", "en-GB"):
			self.assertFalse(is_rtl_language(language))

	def test_panel_validates_before_sound_commit_and_uses_nvda_standard_hooks(self) -> None:
		source = (PACKAGES / "awqati" / "nvda_adapter" / "settings_panel.py").read_text(encoding="utf-8")
		self.assertLess(source.index("def isValid"), source.index("def onSave"))
		self.assertLess(source.index("self._settings.validate(candidate)"), source.index(
			"self._sound_staging.begin_commit", source.index("def onSave")))
		self.assertIn("def onDiscard", source)
		self.assertIn("self._sound_staging.rollback(commit)", source)
		self.assertIn("wx.Layout_RightToLeft", source)
		self.assertIn("wx.Layout_LeftToRight", source)
		self.assertIn("self._sendLayoutUpdatedEvent()", source)


if __name__ == "__main__":
	unittest.main()
