from __future__ import annotations

from datetime import timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import CountryInfo, LocationDetectionError, LocationMatch, LocationSetupService  # noqa: E402
from awqati.domain import Coordinates, Location, LocationDetectionFailure, LocationKind  # noqa: E402

RIYADH = Location("108410", "Riyadh", 24.6877, 46.7219, "Asia/Riyadh")
LONDON = Location("2643743", "London", 51.5085, -0.1257, "Europe/London")


class Repository:
	def __init__(self) -> None:
		self.loaded: list[str] = []
		self.nearest_calls = 0

	def countries(self):
		return (CountryInfo("SA", "Saudi Arabia", 2), CountryInfo("GB", "United Kingdom", 1))

	def search(self, country_code, query, limit=20):
		self.loaded.append(country_code)
		if country_code == "SA" and query.casefold() in "riyadh":
			return (LocationMatch(RIYADH, "SA", "Saudi Arabia", "Riyadh Region", "", 1, "PPLC"),)
		return ()

	def get(self, country_code, location_id):
		if (country_code, location_id) == ("SA", RIYADH.location_id):
			return LocationMatch(RIYADH, "SA", "Saudi Arabia", "Riyadh Region", "", 1, "PPLC")
		return None

	def nearest(self, latitude, longitude):
		self.nearest_calls += 1
		return LocationMatch(RIYADH, "SA", "Saudi Arabia", "Riyadh Region", "", 1, "PPLC")


class Timezones:
	def get_timezone(self, timezone_id):
		if timezone_id not in {"Asia/Riyadh", "Europe/London", "Etc/UTC"}:
			raise ValueError("unknown timezone")
		return timezone.utc

	def timezone_ids(self):
		return ("Asia/Riyadh", "Etc/UTC", "Europe/London")


class CoordinatesProvider:
	def __init__(self, value=Coordinates(24.7, 46.7)) -> None:
		self.value = value
		self.calls = 0

	def get_coordinates(self):
		self.calls += 1
		if isinstance(self.value, Exception):
			raise self.value
		return self.value


class LocationSetupTests(unittest.TestCase):
	def setUp(self) -> None:
		self.repository = Repository()
		self.provider = CoordinatesProvider()
		self.service = LocationSetupService(self.repository, Timezones(), self.provider)

	def test_construction_and_manual_search_do_not_detect_or_load_the_world(self) -> None:
		self.assertEqual(self.provider.calls, 0)
		self.assertEqual(len(self.service.countries()), 2)
		self.assertEqual(self.repository.loaded, [])
		matches = self.service.search("SA", "riy", 20)
		self.assertEqual(matches[0].location, RIYADH)
		self.assertEqual(self.repository.loaded, ["SA"])
		self.assertEqual(self.provider.calls, 0)

	def test_selected_location_preserves_stable_identity_coordinates_and_timezone(self) -> None:
		stored = self.service.selected("SA", RIYADH.location_id)
		self.assertEqual(stored.kind, LocationKind.SELECTED)
		self.assertEqual(stored.country_code, "SA")
		self.assertEqual(stored.location, RIYADH)

	def test_custom_location_validates_coordinates_timezone_and_cancel_has_no_side_effect(self) -> None:
		stored = self.service.custom(" Home ", 12.5, 44.5, "Etc/UTC")
		self.assertEqual(stored.kind, LocationKind.CUSTOM)
		self.assertEqual(stored.location.name, "Home")
		self.assertEqual(stored.location.timezone_id, "Etc/UTC")
		for args in (("X", 91, 0, "Etc/UTC"), ("X", 0, 181, "Etc/UTC"), ("X", 0, 0, "Bad/Zone")):
			with self.subTest(args=args), self.assertRaises(ValueError):
				self.service.custom(*args)
		self.assertEqual(self.provider.calls, 0)

	def test_detection_is_only_explicit_and_matches_locally_once(self) -> None:
		self.assertEqual(self.provider.calls, 0)
		result = self.service.detect()
		self.assertEqual(self.provider.calls, 1)
		self.assertEqual(self.repository.nearest_calls, 1)
		self.assertEqual(result.location.location, RIYADH)
		self.assertEqual(result.location.country_code, "SA")

	def test_typed_detection_failures_are_contained(self) -> None:
		for failure in LocationDetectionFailure:
			provider = CoordinatesProvider(LocationDetectionError(failure))
			result = LocationSetupService(self.repository, Timezones(), provider).detect()
			self.assertIsNone(result.location)
			self.assertEqual(result.failure, failure)

	def test_invalid_detection_coordinates_are_contained(self) -> None:
		class InvalidProvider:
			def get_coordinates(self):
				return type("Raw", (), {"latitude": 91, "longitude": 0})()
		result = LocationSetupService(self.repository, Timezones(), InvalidProvider()).detect()
		self.assertIsNone(result.location)
		self.assertEqual(result.failure, LocationDetectionFailure.INVALID_COORDINATES)


if __name__ == "__main__":
	unittest.main()
