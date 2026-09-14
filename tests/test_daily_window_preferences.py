from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))
sys.path.insert(0, str(ROOT / "tests"))

from awqati.application import SettingsService  # noqa: E402
from awqati.domain import (  # noqa: E402
	Instant,
	SETTINGS_SCHEMA_VERSION,
	SettingsValidationError,
	default_settings,
	validate_settings,
)
from awqati.infrastructure import InvalidSettingsDataError, JsonSettingsRepository  # noqa: E402
from awqati.nvda_adapter.settings_sections import (  # noqa: E402
	SettingsSection,
	focus_target_for_path,
)
from support.event_clock import EventClock  # noqa: E402


class MemoryRepository:
	def __init__(self) -> None:
		self.value = default_settings()
		self.saved = []

	def load(self):
		return deepcopy(self.value)

	def save(self, settings) -> None:
		self.value = deepcopy(settings)
		self.saved.append(deepcopy(settings))


class DailyWindowSchemaTests(unittest.TestCase):
	def test_defaults_are_false_and_schema_version_remains_one(self) -> None:
		settings = default_settings()
		self.assertEqual(SETTINGS_SCHEMA_VERSION, 1)
		self.assertFalse(settings.prayer.open_daily_prayer_times_window)
		self.assertFalse(settings.calendar.open_daily_info_window)

	def test_both_boolean_values_validate_for_each_preference(self) -> None:
		for prayer_value in (False, True):
			for info_value in (False, True):
				with self.subTest(prayer=prayer_value, info=info_value):
					settings = default_settings()
					settings.prayer.open_daily_prayer_times_window = prayer_value
					settings.calendar.open_daily_info_window = info_value
					validate_settings(settings)

	def test_non_boolean_values_are_rejected_with_neutral_paths(self) -> None:
		cases = (
			("prayer.openDailyPrayerTimesWindow", lambda value: setattr(
				value.prayer, "open_daily_prayer_times_window", 1)),
			("calendar.openDailyInfoWindow", lambda value: setattr(
				value.calendar, "open_daily_info_window", "false")),
		)
		for path, mutate in cases:
			with self.subTest(path=path):
				settings = default_settings()
				mutate(settings)
				with self.assertRaises(SettingsValidationError) as caught:
					validate_settings(settings)
				self.assertEqual(caught.exception.path, path)
				self.assertEqual(caught.exception.code, "invalidType")


class DailyWindowRepositoryTests(unittest.TestCase):
	def setUp(self) -> None:
		self.temporary = tempfile.TemporaryDirectory()
		self.path = Path(self.temporary.name) / "settings.json"
		self.repository = JsonSettingsRepository(self.path)

	def tearDown(self) -> None:
		self.temporary.cleanup()

	def test_true_values_round_trip_under_neutral_json_keys(self) -> None:
		settings = default_settings()
		settings.prayer.open_daily_prayer_times_window = True
		settings.calendar.open_daily_info_window = True
		self.repository.save(settings)
		self.assertEqual(self.repository.load(), settings)
		payload = json.loads(self.path.read_text(encoding="utf-8"))
		self.assertIs(payload["prayer"]["openDailyPrayerTimesWindow"], True)
		self.assertIs(payload["calendar"]["openDailyInfoWindow"], True)

	def test_missing_new_fields_follow_existing_incomplete_file_policy(self) -> None:
		self.repository.save(default_settings())
		payload = json.loads(self.path.read_text(encoding="utf-8"))
		del payload["prayer"]["openDailyPrayerTimesWindow"]
		self.path.write_text(json.dumps(payload), encoding="utf-8")
		with self.assertRaises(InvalidSettingsDataError):
			self.repository.load()


class DailyWindowDraftTests(unittest.TestCase):
	def setUp(self) -> None:
		self.repository = MemoryRepository()
		self.service = SettingsService(
			self.repository,
			EventClock(Instant(datetime(2026, 9, 14, tzinfo=timezone.utc))),
		)

	def test_draft_changes_do_not_reach_runtime_and_cancel_discards_them(self) -> None:
		draft = self.service.open_draft()
		draft.settings.prayer.open_daily_prayer_times_window = True
		draft.settings.calendar.open_daily_info_window = True
		self.assertFalse(self.service.runtime_settings.prayer.open_daily_prayer_times_window)
		self.assertFalse(self.service.runtime_settings.calendar.open_daily_info_window)
		self.assertEqual(self.repository.saved, [])
		draft.discard()
		self.assertFalse(self.repository.value.prayer.open_daily_prayer_times_window)
		self.assertFalse(self.repository.value.calendar.open_daily_info_window)

	def test_apply_updates_base_and_later_cancel_keeps_last_apply(self) -> None:
		draft = self.service.open_draft()
		draft.settings.prayer.open_daily_prayer_times_window = True
		draft.settings.calendar.open_daily_info_window = True
		self.service.apply(draft)
		self.assertTrue(draft.base.prayer.open_daily_prayer_times_window)
		self.assertTrue(draft.base.calendar.open_daily_info_window)
		draft.settings.prayer.open_daily_prayer_times_window = False
		draft.settings.calendar.open_daily_info_window = False
		draft.discard()
		self.assertTrue(self.service.runtime_settings.prayer.open_daily_prayer_times_window)
		self.assertTrue(self.service.runtime_settings.calendar.open_daily_info_window)
		self.assertEqual(len(self.repository.saved), 1)


class DailyWindowUiContractTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.path = PACKAGES / "awqati" / "nvda_adapter" / "settings_panel.py"
		cls.source = cls.path.read_text(encoding="utf-8")
		cls.tree = ast.parse(cls.source)

	@classmethod
	def method_source(cls, name: str) -> str:
		node = next(item for item in ast.walk(cls.tree)
			if isinstance(item, ast.FunctionDef) and item.name == name)
		return ast.get_source_segment(cls.source, node) or ""

	def test_prayer_checkbox_is_translated_bound_and_before_event_configuration(self) -> None:
		method = self.method_source("_build_prayer")
		self.assertIn('_("Open daily prayer times window")', method)
		self.assertIn('"open_daily_prayer_times_window"', method)
		self.assertIn('"prayer.openDailyPrayerTimesWindow"', method)
		self.assertLess(method.index('_("Open daily prayer times window")'),
			method.index('_("Time to configure:")'))

	def test_daily_info_checkbox_is_translated_bound_and_follows_content_option(self) -> None:
		method = self.method_source("_build_date")
		include = '_("Include Arabian calendar information in astronomical daily information")'
		open_window = '_("Open daily information window")'
		self.assertIn(include, method)
		self.assertIn(open_window, method)
		self.assertIn('"open_daily_info_window"', method)
		self.assertIn('"calendar.openDailyInfoWindow"', method)
		self.assertLess(method.index(include), method.index(open_window))

	def test_validation_focus_paths_resolve_to_the_two_accessible_controls(self) -> None:
		prayer = focus_target_for_path("prayer.openDailyPrayerTimesWindow")
		info = focus_target_for_path("calendar.openDailyInfoWindow")
		self.assertEqual((prayer.control_key, prayer.section),
			("prayer.openDailyPrayerTimesWindow", SettingsSection.PRAYER))
		self.assertEqual((info.control_key, info.section),
			("calendar.openDailyInfoWindow", SettingsSection.DATE))

	def test_scope_contains_no_commands_windows_scheduler_or_multipress(self) -> None:
		changed_sources = "\n".join((
			(PACKAGES / "awqati" / "domain" / "settings.py").read_text(encoding="utf-8"),
			(PACKAGES / "awqati" / "infrastructure" / "settings_repository.py").read_text(encoding="utf-8"),
			self.source,
		))
		for forbidden in ("MultiPressDispatcher", "browseableMessage", "AlertPresenter", "Scheduler"):
			self.assertNotIn(forbidden, changed_sources)


if __name__ == "__main__":
	unittest.main()
