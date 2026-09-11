from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PLUGIN_PACKAGES) not in sys.path:
	sys.path.insert(0, str(PLUGIN_PACKAGES))
if str(ROOT / "tests") not in sys.path:
	sys.path.insert(0, str(ROOT / "tests"))

from awqati.application import NowProvider  # noqa: E402
from awqati.domain import DomainEvent, Instant, Location  # noqa: E402
from awqati.infrastructure import SystemNowProvider  # noqa: E402
from support.event_clock import EventClock  # noqa: E402


class CoreModelTests(unittest.TestCase):
	def test_instant_accepts_an_aware_datetime(self) -> None:
		value = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
		self.assertEqual(Instant(value).value, value)

	def test_instant_rejects_an_ambiguous_datetime(self) -> None:
		with self.assertRaisesRegex(ValueError, "timezone-aware"):
			Instant(datetime(2026, 1, 2, 3, 4))

	def test_location_keeps_only_neutral_core_identity(self) -> None:
		location = Location("sa-riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		self.assertEqual(location.location_id, "sa-riyadh")
		self.assertEqual(location.timezone_id, "Asia/Riyadh")

	def test_location_rejects_empty_identity_and_invalid_coordinates(self) -> None:
		valid = {"location_id": "id", "name": "Name", "latitude": 0.0, "longitude": 0.0, "timezone_id": "Etc/UTC"}
		for field_name in ("location_id", "name", "timezone_id"):
			values = valid | {field_name: "  "}
			with self.subTest(field=field_name), self.assertRaises(ValueError):
				Location(**values)
		for field_name, value in (("latitude", 90.1), ("latitude", math.inf), ("longitude", -180.1), ("longitude", math.nan)):
			values = valid | {field_name: value}
			with self.subTest(field=field_name, value=value), self.assertRaises(ValueError):
				Location(**values)

	def test_domain_event_records_only_its_instant(self) -> None:
		instant = Instant(datetime(2026, 1, 2, tzinfo=timezone.utc))
		self.assertEqual(DomainEvent(instant).occurred_at, instant)


class ClockBoundaryTests(unittest.TestCase):
	def test_event_clock_is_deterministic_and_controllable(self) -> None:
		first = Instant(datetime(2026, 1, 2, tzinfo=timezone.utc))
		second = Instant(datetime(2026, 6, 7, tzinfo=timezone.utc))
		clock = EventClock(first)
		self.assertIsInstance(clock, NowProvider)
		self.assertEqual(clock.now(), first)
		clock.set(second)
		self.assertEqual(clock.now(), second)

	def test_system_clock_implements_the_same_small_contract(self) -> None:
		clock = SystemNowProvider()
		self.assertIsInstance(clock, NowProvider)
		self.assertIsNotNone(clock.now().value.utcoffset())


if __name__ == "__main__":
	unittest.main()
