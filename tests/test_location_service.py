from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import socket
from types import SimpleNamespace
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
for path in (PLUGIN_PACKAGES, ROOT / "tests"):
	if str(path) not in sys.path:
		sys.path.insert(0, str(path))

from awqati.application import (  # noqa: E402
	EventDispatcher,
	LocationDetectionError,
	LocationMatch,
	LocationNotFoundError,
	LocationService,
)
from awqati.domain import (  # noqa: E402
	Coordinates,
	Instant,
	Location,
	LocationChanged,
	LocationDetectionFailure,
	LocationStatus,
)
from support.event_clock import EventClock  # noqa: E402


RIYADH = Location("108410", "Riyadh", 24.6877, 46.7219, "Asia/Riyadh")
LONDON = Location("2643743", "London", 51.5085, -0.1257, "Europe/London")


def match(location: Location, country: str) -> LocationMatch:
	return LocationMatch(location, country, country, "", "", 1_000_000, "PPLC")


class FakeRepository:
	def __init__(self) -> None:
		self.items = {("SA", RIYADH.location_id): match(RIYADH, "SA"), ("GB", LONDON.location_id): match(LONDON, "GB")}
		self.nearest_result = self.items[("SA", RIYADH.location_id)]
		self.nearest_calls: list[tuple[float, float]] = []

	def get(self, country_code: str, location_id: str) -> LocationMatch | None:
		return self.items.get((country_code, location_id))

	def nearest(self, latitude: float, longitude: float) -> LocationMatch:
		self.nearest_calls.append((latitude, longitude))
		return self.nearest_result


class FakeTimezones:
	def __init__(self) -> None:
		self.calls: list[str] = []

	def get_timezone(self, timezone_id: str):
		self.calls.append(timezone_id)
		if timezone_id not in {"Asia/Riyadh", "Europe/London", "Etc/UTC"}:
			raise ValueError("unknown timezone")
		return timezone.utc


class FakeWindowsLocation:
	def __init__(self, result: object = Coordinates(24.7, 46.7)) -> None:
		self.result = result
		self.calls = 0

	def get_coordinates(self) -> Coordinates:
		self.calls += 1
		if isinstance(self.result, BaseException):
			raise self.result
		return self.result  # type: ignore[return-value]


class LocationServiceTests(unittest.TestCase):
	def setUp(self) -> None:
		self.repository = FakeRepository()
		self.timezones = FakeTimezones()
		self.windows = FakeWindowsLocation()
		self.instant = Instant(datetime(2026, 9, 12, 12, tzinfo=timezone.utc))
		self.events = EventDispatcher()
		self.received: list[LocationChanged] = []
		self.events.subscribe(LocationChanged, self.received.append)
		self.service = LocationService(
			self.repository, self.timezones, self.windows, EventClock(self.instant), self.events
		)

	def test_construction_and_reading_are_unset_and_do_not_detect(self) -> None:
		self.assertEqual(self.service.current_state.status, LocationStatus.UNSET)
		self.assertIsNone(self.service.current_state.location)
		self.assertEqual(self.windows.calls, 0)
		self.assertEqual(self.received, [])

	def test_valid_initial_location_is_available_without_a_change_event(self) -> None:
		service = LocationService(
			self.repository,
			self.timezones,
			self.windows,
			EventClock(self.instant),
			self.events,
			initial_location=LONDON,
		)
		self.assertEqual(service.current_state.location, LONDON)
		self.assertEqual(self.windows.calls, 0)
		self.assertEqual(self.received, [])

	def test_selected_location_uses_stable_identity_and_timezone(self) -> None:
		state = self.service.assign_selected("SA", "108410")
		self.assertEqual(state.status, LocationStatus.ASSIGNED)
		self.assertEqual(state.location, RIYADH)
		self.assertEqual(self.timezones.calls, ["Asia/Riyadh"])
		self.assertEqual(len(self.received), 1)

	def test_unknown_selected_identity_preserves_previous_location(self) -> None:
		self.service.assign_selected("SA", "108410")
		with self.assertRaises(LocationNotFoundError):
			self.service.assign_selected("SA", "missing")
		self.assertEqual(self.service.current_state.location, RIYADH)
		self.assertEqual(len(self.received), 1)

	def test_custom_location_is_validated_and_has_deterministic_identity(self) -> None:
		first = self.service.assign_custom("  My place  ", 10, 20, "Etc/UTC").location
		self.assertIsNotNone(first)
		assert first is not None
		self.assertEqual((first.name, first.latitude, first.longitude, first.timezone_id), ("My place", 10.0, 20.0, "Etc/UTC"))
		self.assertTrue(first.location_id.startswith("custom:"))
		self.assertEqual(self.service.assign_custom("My place", 10.0, 20.0, "Etc/UTC").location, first)
		self.assertEqual(len(self.received), 1)

	def test_invalid_custom_values_preserve_previous_location_and_emit_nothing(self) -> None:
		self.service.assign_selected("SA", "108410")
		for arguments in (
			("", 1, 2, "Etc/UTC"),
			("x", float("nan"), 2, "Etc/UTC"),
			("x", 91, 2, "Etc/UTC"),
			("x", 1, -181, "Etc/UTC"),
			("x", 1, 2, "Bad/Zone"),
		):
			with self.subTest(arguments=arguments), self.assertRaises(ValueError):
				self.service.assign_custom(*arguments)
			self.assertEqual(self.service.current_state.location, RIYADH)
		self.assertEqual(len(self.received), 1)

	def test_successful_detection_matches_locally_and_assigns_once(self) -> None:
		result = self.service.detect_and_assign()
		self.assertEqual((result.status, result.location, result.failure), (LocationStatus.ASSIGNED, RIYADH, None))
		self.assertEqual(self.repository.nearest_calls, [(24.7, 46.7)])
		self.assertEqual(len(self.received), 1)
		self.service.detect_and_assign()
		self.assertEqual(len(self.received), 1)

	def test_each_typed_detection_failure_preserves_an_existing_location(self) -> None:
		self.service.assign_selected("GB", LONDON.location_id)
		for failure in LocationDetectionFailure:
			self.windows.result = LocationDetectionError(failure)
			result = self.service.detect_and_assign()
			with self.subTest(failure=failure):
				self.assertEqual(result.status, LocationStatus.DETECTION_FAILED)
				self.assertEqual(result.failure, failure)
				self.assertEqual(result.location, LONDON)
				self.assertEqual(self.service.current_state.location, LONDON)
		self.assertEqual(len(self.received), 1)

	def test_failed_first_detection_keeps_current_state_unset(self) -> None:
		self.windows.result = LocationDetectionError(LocationDetectionFailure.DENIED)
		result = self.service.detect_and_assign()
		self.assertEqual(result.status, LocationStatus.DETECTION_FAILED)
		self.assertIsNone(result.location)
		self.assertEqual(self.service.current_state.status, LocationStatus.UNSET)
		self.assertEqual(self.received, [])

	def test_invalid_provider_coordinates_and_unexpected_failure_are_contained(self) -> None:
		for value in (SimpleNamespace(latitude=float("inf"), longitude=1), RuntimeError("boom")):
			self.windows.result = value
			result = self.service.detect_and_assign()
			self.assertEqual(result.status, LocationStatus.DETECTION_FAILED)
			self.assertEqual(result.failure, LocationDetectionFailure.API_ERROR)
		self.assertEqual(self.received, [])

	def test_every_actual_transition_emits_exactly_one_complete_event(self) -> None:
		self.service.assign_selected("SA", RIYADH.location_id)
		self.service.assign_selected("GB", LONDON.location_id)
		custom = self.service.assign_custom("Custom", 1, 2, "Etc/UTC").location
		self.repository.nearest_result = match(RIYADH, "SA")
		self.service.detect_and_assign()
		self.service.clear()
		self.assertEqual(len(self.received), 5)
		self.assertEqual(
			[(event.previous_location, event.current_location) for event in self.received],
			[(None, RIYADH), (RIYADH, LONDON), (LONDON, custom), (custom, RIYADH), (RIYADH, None)],
		)
		self.assertTrue(all(event.occurred_at == self.instant for event in self.received))

	def test_repeated_clear_read_and_unsubscribe_do_not_duplicate_events(self) -> None:
		unsubscribed: list[LocationChanged] = []
		unsubscribe = self.events.subscribe(LocationChanged, unsubscribed.append)
		self.service.assign_selected("SA", RIYADH.location_id)
		unsubscribe()
		self.service.assign_selected("GB", LONDON.location_id)
		self.service.clear()
		self.service.clear()
		_ = self.service.current_state
		self.assertEqual(len(self.received), 3)
		self.assertEqual(len(unsubscribed), 1)

	def test_selected_and_custom_paths_ignore_network_locale_and_system_timezone(self) -> None:
		with (
			mock.patch.object(socket, "socket", side_effect=AssertionError("network attempted")),
			mock.patch("locale.getlocale", side_effect=AssertionError("locale consulted")),
			mock.patch("time.localtime", side_effect=AssertionError("system timezone consulted")),
		):
			self.service.assign_selected("SA", RIYADH.location_id)
			self.service.assign_custom("Offline", 5, 6, "Etc/UTC")


if __name__ == "__main__":
	unittest.main()
