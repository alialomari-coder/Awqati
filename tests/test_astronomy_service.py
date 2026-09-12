from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
for path in (PACKAGES, ROOT / "tests"):
	if str(path) not in sys.path:
		sys.path.insert(0, str(path))

from awqati.application import AstronomyService  # noqa: E402
from awqati.domain import ASTRONOMY_ALGORITHM_VERSION, Instant, Location, SeasonEvent  # noqa: E402
from awqati.infrastructure import BundledTimezoneProvider  # noqa: E402
from support.event_clock import EventClock  # noqa: E402


class AstronomyServiceTests(unittest.TestCase):
	def setUp(self) -> None:
		self.timezones = BundledTimezoneProvider()

	def test_read_uses_now_location_iana_zone_and_complete_metadata(self) -> None:
		clock = EventClock(Instant(datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc)))
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		reading = AstronomyService(clock, self.timezones).read(location)
		self.assertEqual(reading.local_date.isoformat(), "2026-09-13")
		self.assertEqual(reading.next_seasonal_event.event, SeasonEvent.SEPTEMBER_EQUINOX)
		self.assertEqual(reading.next_seasonal_event_local.utcoffset(), timedelta(hours=3))
		self.assertEqual(reading.next_new_moon_local.utcoffset(), timedelta(hours=3))
		self.assertEqual(reading.algorithm_version, ASTRONOMY_ALGORITHM_VERSION)

	def test_dst_is_applied_at_the_absolute_event_instant(self) -> None:
		clock = EventClock(Instant(datetime(2026, 4, 1, tzinfo=timezone.utc)))
		location = Location("london", "London", 51.5074, -0.1278, "Europe/London")
		reading = AstronomyService(clock, self.timezones).read(location)
		self.assertEqual(reading.next_seasonal_event.event, SeasonEvent.JUNE_SOLSTICE)
		self.assertEqual(reading.next_seasonal_event_local.utcoffset(), timedelta(hours=1))
		self.assertEqual(reading.next_seasonal_event_local.hour, 9)

	def test_runtime_path_uses_no_network_provider(self) -> None:
		class NoNetworkClock:
			def now(self):
				return Instant(datetime(2026, 1, 15, tzinfo=timezone.utc))

		location = Location("sydney", "Sydney", -33.8688, 151.2093, "Australia/Sydney")
		reading = AstronomyService(NoNetworkClock(), self.timezones).read(location)
		self.assertEqual(reading.local_date.isoformat(), "2026-01-15")
		self.assertIsNotNone(reading.sunrise_local)
		self.assertIsNotNone(reading.sunset_local)


if __name__ == "__main__":
	unittest.main()
