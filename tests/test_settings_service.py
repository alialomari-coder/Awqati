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
	ClosedSettingsDraftError,
	EventDispatcher,
	SettingsDraft,
	SettingsRepository,
	SettingsService,
)
from awqati.domain import (  # noqa: E402
	AlertAction,
	Instant,
	Location,
	LocationChanged,
	LocationKind,
	RecurringDhikrId,
	SettingsApplied,
	SoundReference,
	StoredLocation,
	default_settings,
)
from awqati.infrastructure import SettingsWriteError  # noqa: E402
from support.event_clock import EventClock  # noqa: E402


class MemoryRepository:
	def __init__(self, settings=None) -> None:
		self.value = deepcopy(settings or default_settings())
		self.saved: list = []
		self.failure: Exception | None = None

	def load(self):
		return deepcopy(self.value)

	def save(self, settings) -> None:
		if self.failure is not None:
			raise self.failure
		self.value = deepcopy(settings)
		self.saved.append(deepcopy(settings))


class SettingsDraftTests(unittest.TestCase):
	def test_nested_edit_and_sound_path_do_not_leak_to_runtime_or_repository(self) -> None:
		repository = MemoryRepository()
		service = SettingsService(repository, EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc))))
		draft = service.open_draft()
		identity = RecurringDhikrId.ASTAGHFIRU_ALLAH
		draft.settings.adhkar.recurring.items[identity].alert.action = AlertAction.SOUND
		draft.settings.adhkar.recurring.items[identity].alert.sound = SoundReference("sounds/adhkar/private.wav")
		self.assertIsNone(service.runtime_settings.adhkar.recurring.items[identity].alert.sound)
		self.assertIsNone(repository.value.adhkar.recurring.items[identity].alert.sound)
		self.assertIsNot(draft.settings.adhkar.recurring, service.runtime_settings.adhkar.recurring)

	def test_discard_is_cancel_and_leaves_no_effect(self) -> None:
		repository = MemoryRepository()
		service = SettingsService(repository, EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc))))
		events = []
		service.events.subscribe(SettingsApplied, events.append)
		draft = service.open_draft()
		draft.settings.general.all_automatic_alerts_enabled = False
		draft.discard()
		self.assertTrue(service.runtime_settings.general.all_automatic_alerts_enabled)
		self.assertEqual(repository.saved, [])
		self.assertEqual(events, [])
		with self.assertRaises(ClosedSettingsDraftError):
			_ = draft.settings

	def test_apply_refreshes_open_draft_base_after_one_validated_write(self) -> None:
		repository = MemoryRepository()
		clock = EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)))
		service = SettingsService(repository, clock)
		events = []
		service.events.subscribe(SettingsApplied, events.append)
		draft = service.open_draft()
		draft.settings.adhkar.recurring.enabled = True
		applied = service.apply(draft)
		self.assertTrue(applied.adhkar.recurring.enabled)
		self.assertTrue(draft.base.adhkar.recurring.enabled)
		self.assertEqual(len(repository.saved), 1)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].schema_version, 1)

	def test_validation_failure_writes_and_publishes_nothing(self) -> None:
		repository = MemoryRepository()
		service = SettingsService(repository, EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc))))
		events = []
		service.events.subscribe(SettingsApplied, events.append)
		draft = service.open_draft()
		draft.settings.adhkar.recurring.interval_minutes = 4
		with self.assertRaises(ValueError):
			service.apply(draft)
		self.assertEqual(repository.saved, [])
		self.assertEqual(events, [])
		self.assertEqual(service.runtime_settings.adhkar.recurring.interval_minutes, 60)

	def test_write_failure_preserves_runtime_draft_base_and_events(self) -> None:
		repository = MemoryRepository()
		service = SettingsService(repository, EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc))))
		events = []
		service.events.subscribe(SettingsApplied, events.append)
		draft = service.open_draft()
		draft.settings.adhkar.daily_wird.text = "changed"
		repository.failure = SettingsWriteError("disk")
		with self.assertRaises(SettingsWriteError):
			service.apply(draft)
		self.assertEqual(service.runtime_settings.adhkar.daily_wird.text, "Do not forget your daily Wird.")
		self.assertEqual(draft.base.adhkar.daily_wird.text, "Do not forget your daily Wird.")
		self.assertEqual(events, [])

	def test_location_change_reuses_one_existing_event_and_unchanged_location_does_not_repeat(self) -> None:
		repository = MemoryRepository()
		clock = EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)))
		service = SettingsService(repository, clock)
		location_events = []
		service.events.subscribe(LocationChanged, location_events.append)
		draft = service.open_draft()
		location = Location("108410", "Riyadh", 24.6877, 46.7219, "Asia/Riyadh")
		draft.settings.location = StoredLocation(LocationKind.SELECTED, location, "SA")
		service.apply(draft)
		service.apply(draft)
		self.assertEqual(len(location_events), 1)
		self.assertIsNone(location_events[0].previous_location)
		self.assertEqual(location_events[0].current_location, location)


class EventDispatcherTests(unittest.TestCase):
	def test_subscribe_order_unsubscribe_and_exception_policy(self) -> None:
		dispatcher = EventDispatcher()
		event = SettingsApplied(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)), 1)
		calls = []
		remove_first = dispatcher.subscribe(SettingsApplied, lambda value: calls.append(("first", value.schema_version)))
		dispatcher.subscribe(SettingsApplied, lambda value: calls.append(("second", value.schema_version)))
		dispatcher.publish(event)
		remove_first()
		remove_first()
		dispatcher.publish(event)
		self.assertEqual(calls, [("first", 1), ("second", 1), ("second", 1)])

		def fail(_event) -> None:
			raise RuntimeError("listener")

		dispatcher.subscribe(SettingsApplied, fail)
		with self.assertRaises(RuntimeError):
			dispatcher.publish(event)

	def test_memory_repository_satisfies_small_contract(self) -> None:
		self.assertIsInstance(MemoryRepository(), SettingsRepository)


if __name__ == "__main__":
	unittest.main()
