from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PLUGIN_PACKAGES) not in sys.path:
	sys.path.insert(0, str(PLUGIN_PACKAGES))
if str(ROOT / "tests") not in sys.path:
	sys.path.insert(0, str(ROOT / "tests"))

from support.time_fixtures import (  # noqa: E402
	LEAP_DAY,
	REFERENCE_DATE,
	REFERENCE_DATETIME,
	UTC,
	UTC_PLUS_THREE,
	event_clock_at,
	fixed_offset_hours,
	instant_at,
)


class TimeFixtureTests(unittest.TestCase):
	def test_shared_datetime_is_aware_with_the_expected_fixed_offset(self) -> None:
		self.assertIsNotNone(REFERENCE_DATETIME.tzinfo)
		self.assertEqual(REFERENCE_DATETIME.utcoffset(), timedelta(hours=3))
		self.assertEqual(UTC.utcoffset(REFERENCE_DATETIME), timedelta(0))
		self.assertEqual(UTC_PLUS_THREE.utcoffset(REFERENCE_DATETIME), timedelta(hours=3))

	def test_shared_calendar_dates_are_fixed(self) -> None:
		self.assertEqual(REFERENCE_DATE.isoformat(), "2026-01-15")
		self.assertEqual(LEAP_DAY.isoformat(), "2024-02-29")

	def test_factories_return_the_exact_requested_values(self) -> None:
		value = datetime(2026, 8, 9, 10, 11, tzinfo=fixed_offset_hours(-4))
		self.assertEqual(instant_at().value, REFERENCE_DATETIME)
		self.assertEqual(instant_at(value).value, value)
		self.assertEqual(fixed_offset_hours(-4).utcoffset(value), timedelta(hours=-4))

	def test_event_clock_moves_without_waiting_for_the_system_clock(self) -> None:
		clock = event_clock_at()
		later = instant_at(datetime(2027, 2, 3, 4, 5, tzinfo=UTC))
		self.assertEqual(clock.now(), instant_at())
		clock.set(later)
		self.assertEqual(clock.now(), later)


if __name__ == "__main__":
	unittest.main()
