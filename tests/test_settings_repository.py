from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from unittest import mock
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))

from awqati.application import SettingsRepository  # noqa: E402
from awqati.domain import (  # noqa: E402
	AlertAction,
	PrayerEventName,
	RecurringDhikrId,
	SETTINGS_SCHEMA_VERSION,
	SoundReference,
	default_settings,
)
from awqati.infrastructure import (  # noqa: E402
	InvalidSettingsDataError,
	FIRST_PUBLISHED_SETTINGS_SCHEMA_VERSION,
	JsonSettingsRepository,
	SettingsMigrationRegistry,
	SettingsWriteError,
	UnsupportedSettingsSchemaError,
)
import awqati.infrastructure.settings_repository as repository_module  # noqa: E402


def migration_to(version: int):
	def migrate(data):
		result = deepcopy(data)
		result["schemaVersion"] = version
		return result
	return migrate


class JsonSettingsRepositoryTests(unittest.TestCase):
	def setUp(self) -> None:
		self.temporary = tempfile.TemporaryDirectory()
		self.path = Path(self.temporary.name) / "nested" / "settings.json"
		self.repository = JsonSettingsRepository(self.path)

	def tearDown(self) -> None:
		self.temporary.cleanup()

	def test_missing_file_returns_complete_defaults_without_legacy_lookup(self) -> None:
		self.assertIsInstance(self.repository, SettingsRepository)
		settings = self.repository.load()
		self.assertEqual(settings.schema_version, 1)
		self.assertFalse(self.path.exists())

	def test_complete_round_trip_preserves_enums_nested_values_and_each_sound(self) -> None:
		settings = default_settings()
		settings.prayer.events[PrayerEventName.FAJR].pre_alert.action = AlertAction.SILENT
		for index, identity in enumerate(RecurringDhikrId):
			item = settings.adhkar.recurring.items[identity]
			item.alert.action = AlertAction.SOUND
			item.alert.sound = SoundReference(f"sounds/adhkar/item-{index}.wav")
		self.repository.save(settings)
		loaded = self.repository.load()
		self.assertEqual(loaded, settings)
		self.assertTrue(all(
			loaded.adhkar.recurring.items[identity].alert.sound.value == f"sounds/adhkar/item-{index}.wav"
			for index, identity in enumerate(RecurringDhikrId)))

	def test_saved_json_uses_neutral_codes_and_no_absolute_user_paths(self) -> None:
		settings = default_settings()
		settings.clock.alert.action = AlertAction.SOUND_AND_SPEECH
		settings.adhkar.daily_wird.alert.action = AlertAction.SOUND
		settings.adhkar.daily_wird.alert.sound = SoundReference("sounds/adhkar/wird.wav")
		self.repository.save(settings)
		text = self.path.read_text(encoding="utf-8")
		self.assertIn('"schemaVersion": 1', text)
		self.assertIn('"HIJRI_UMM_AL_QURA"', text)
		self.assertIn('"soundAndSpeech"', text)
		self.assertNotIn(str(Path.home()), text)

	def test_newer_schema_is_rejected_explicitly(self) -> None:
		self.path.parent.mkdir(parents=True)
		self.path.write_text('{"schemaVersion": 2}', encoding="utf-8")
		with self.assertRaises(UnsupportedSettingsSchemaError):
			self.repository.load()

	def test_missing_schema_unknown_fields_and_invalid_values_are_rejected(self) -> None:
		for payload in (
			{},
			{"schemaVersion": 1},
		{"schemaVersion": 0},
		{"schemaVersion": "1"},
		None,
	):
			with self.subTest(payload=payload):
				self.path.parent.mkdir(parents=True, exist_ok=True)
				self.path.write_text(json.dumps(payload), encoding="utf-8")
				with self.assertRaises(InvalidSettingsDataError):
					self.repository.load()

	def test_corrupt_file_does_not_fall_back_or_overwrite_it(self) -> None:
		self.path.parent.mkdir(parents=True)
		original = "{bad json"
		self.path.write_text(original, encoding="utf-8")
		with self.assertRaises(InvalidSettingsDataError):
			self.repository.load()
		self.assertEqual(self.path.read_text(encoding="utf-8"), original)

	def test_invalid_settings_are_rejected_before_any_write(self) -> None:
		settings = default_settings()
		settings.calendar.primary_calendar = "UNKNOWN"
		with self.assertRaises(InvalidSettingsDataError):
			self.repository.save(settings)
		self.assertFalse(self.path.exists())

	def test_replace_failure_preserves_previous_file_and_removes_temporary(self) -> None:
		self.repository.save(default_settings())
		original = self.path.read_bytes()
		changed = default_settings()
		changed.adhkar.daily_wird.text = "private reminder"
		with mock.patch.object(repository_module.os, "replace", side_effect=OSError("blocked")):
			with self.assertRaises(SettingsWriteError):
				self.repository.save(changed)
		self.assertEqual(self.path.read_bytes(), original)
		self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

	def test_registry_has_no_schema_zero_or_legacy_migration(self) -> None:
		registry = SettingsMigrationRegistry()
		with self.assertRaises(ValueError):
			registry.register(0, lambda data: data)
		with self.assertRaises(InvalidSettingsDataError):
			registry.migrate({"schemaVersion": 0})


class SettingsMigrationRegistryTests(unittest.TestCase):
	def test_runtime_schema_and_first_published_schema_remain_one(self) -> None:
		self.assertEqual(SETTINGS_SCHEMA_VERSION, 1)
		self.assertEqual(FIRST_PUBLISHED_SETTINGS_SCHEMA_VERSION, 1)

	def test_future_registry_can_upgrade_schema_one_to_two(self) -> None:
		registry = SettingsMigrationRegistry(target_version=2, oldest_supported_version=1)
		registry.register(1, migration_to(2))
		self.assertEqual(registry.target_version, 2)
		self.assertEqual(registry.oldest_supported_version, 1)
		self.assertEqual(registry.migrate({"schemaVersion": 1, "kept": "value"}),
			{"schemaVersion": 2, "kept": "value"})

	def test_future_registry_runs_complete_one_to_two_to_three_chain(self) -> None:
		registry = SettingsMigrationRegistry(target_version=3, oldest_supported_version=1)
		registry.register(1, migration_to(2))
		registry.register(2, migration_to(3))
		self.assertEqual(registry.migrate({"schemaVersion": 1})["schemaVersion"], 3)

	def test_incomplete_future_chain_is_rejected(self) -> None:
		registry = SettingsMigrationRegistry(target_version=3, oldest_supported_version=1)
		registry.register(1, migration_to(2))
		with self.assertRaises(InvalidSettingsDataError):
			registry.migrate({"schemaVersion": 1})

	def test_migration_must_return_a_mapping_advanced_by_exactly_one(self) -> None:
		invalid_migrations = (
			lambda data: data,
			lambda data: {**data, "schemaVersion": 1},
			lambda data: {**data, "schemaVersion": 3},
			lambda data: {**data, "schemaVersion": "2"},
			lambda data: None,
		)
		for migration in invalid_migrations:
			with self.subTest(migration=migration):
				registry = SettingsMigrationRegistry(target_version=2, oldest_supported_version=1)
				registry.register(1, migration)
				with self.assertRaises(InvalidSettingsDataError):
					registry.migrate({"schemaVersion": 1})

	def test_duplicate_and_out_of_range_registration_are_rejected(self) -> None:
		registry = SettingsMigrationRegistry(target_version=3, oldest_supported_version=1)
		registry.register(1, migration_to(2))
		with self.assertRaises(ValueError):
			registry.register(1, migration_to(2))
		for from_version in (0, 3, 4):
			with self.subTest(from_version=from_version):
				with self.assertRaises(ValueError):
					registry.register(from_version, migration_to(from_version + 1))

	def test_versions_outside_supported_window_are_rejected(self) -> None:
		registry = SettingsMigrationRegistry(target_version=3, oldest_supported_version=2)
		with self.assertRaises(InvalidSettingsDataError):
			registry.migrate({"schemaVersion": 1})
		with self.assertRaises(UnsupportedSettingsSchemaError):
			registry.migrate({"schemaVersion": 4})

	def test_invalid_registry_version_window_is_rejected(self) -> None:
		for target, oldest in ((2, 0), (1, 2), (True, 1), (2, False)):
			with self.subTest(target=target, oldest=oldest):
				with self.assertRaises(ValueError):
					SettingsMigrationRegistry(target_version=target, oldest_supported_version=oldest)


if __name__ == "__main__":
	unittest.main()
