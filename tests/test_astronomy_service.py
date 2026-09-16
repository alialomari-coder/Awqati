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
from awqati.domain import (  # noqa: E402
	ASTRONOMY_ALGORITHM_VERSION,
	AstronomyRangeError,
	Instant,
	Location,
	Season,
	SeasonEvent,
	seasonal_event_utc,
	SolarDayState,
)
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
		self.assertEqual(reading.observed_at_local.isoformat(), "2026-09-13T03:30:00+03:00")
		self.assertLess(reading.daylight_change_from_previous_day, timedelta(0))
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

	def test_local_event_date_is_day_one_for_all_four_seasons(self) -> None:
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		zone = self.timezones.get_timezone(location.timezone_id)
		expected = {
			SeasonEvent.MARCH_EQUINOX: Season.SPRING,
			SeasonEvent.JUNE_SOLSTICE: Season.SUMMER,
			SeasonEvent.SEPTEMBER_EQUINOX: Season.AUTUMN,
			SeasonEvent.DECEMBER_SOLSTICE: Season.WINTER,
		}
		for event, season in expected.items():
			local_date = seasonal_event_utc(2026, event).astimezone(zone).date()
			local_early = datetime.combine(local_date, datetime.min.time(), tzinfo=zone) + timedelta(minutes=5)
			reading = AstronomyService(
				EventClock(Instant(local_early.astimezone(timezone.utc))), self.timezones,
			).read(location)
			with self.subTest(event=event):
				self.assertEqual(season, reading.current_season)
				self.assertEqual(1, reading.season_day)

	def test_last_local_day_of_each_season_precedes_next_boundary(self) -> None:
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		zone = self.timezones.get_timezone(location.timezone_id)
		events = list(SeasonEvent)
		for index, event in enumerate(events):
			start = seasonal_event_utc(2026, event).astimezone(zone).date()
			next_year = 2027 if event is SeasonEvent.DECEMBER_SOLSTICE else 2026
			next_event = events[(index + 1) % len(events)]
			last = seasonal_event_utc(next_year, next_event).astimezone(zone).date() - timedelta(days=1)
			reading = self._read_local_noon(location, last)
			with self.subTest(event=event):
				self.assertEqual((last - start).days + 1, reading.season_day)
				next_reading = self._read_local_noon(location, last + timedelta(days=1))
				self.assertEqual(1, next_reading.season_day)

	def test_season_day_uses_each_locations_local_boundary_date(self) -> None:
		for location in (
			Location("london", "London", 51.5074, -0.1278, "Europe/London"),
			Location("kiritimati", "Kiritimati", 1.8721, -157.4278, "Pacific/Kiritimati"),
		):
			zone = self.timezones.get_timezone(location.timezone_id)
			for event in SeasonEvent:
				local_date = seasonal_event_utc(2026, event).astimezone(zone).date()
				with self.subTest(location=location.location_id, event=event):
					self.assertEqual(1, self._read_local_noon(location, local_date).season_day)
	def test_runtime_path_uses_no_network_provider(self) -> None:
		class NoNetworkClock:
			def now(self):
				return Instant(datetime(2026, 1, 15, tzinfo=timezone.utc))

		location = Location("sydney", "Sydney", -33.8688, 151.2093, "Australia/Sydney")
		reading = AstronomyService(NoNetworkClock(), self.timezones).read(location)
		self.assertEqual(reading.local_date.isoformat(), "2026-01-15")
		self.assertIsNotNone(reading.sunrise_local)
		self.assertIsNotNone(reading.sunset_local)

	def test_date_line_solar_cycle_belongs_to_kiritimati_local_day(self) -> None:
		location = Location(
			"kiritimati", "Kiritimati", 1.8721, -157.4278, "Pacific/Kiritimati",
		)
		reading = self._read_local_noon(location, datetime(2026, 1, 15).date())
		self.assertEqual(reading.local_date.isoformat(), "2026-01-15")
		assert reading.sunrise_local and reading.sunset_local
		self.assertEqual(reading.sunrise_local.date(), reading.local_date)
		self.assertEqual(reading.sunset_local.date(), reading.local_date)
		self.assertEqual(reading.sunrise_local.utcoffset(), timedelta(hours=14))
		self.assertEqual(reading.sunset_local.utcoffset(), timedelta(hours=14))
		self.assertGreater(reading.solar_day.daylight, timedelta(hours=11))
		self.assertLess(reading.solar_day.daylight, timedelta(hours=13))
		self.assertGreater(reading.solar_day.night, timedelta(hours=11))
		self.assertLess(reading.solar_day.night, timedelta(hours=13))
		next_sunrise_local = reading.solar_day.next_sunrise_utc.astimezone(
			self.timezones.get_timezone(location.timezone_id),
		)
		self.assertEqual(next_sunrise_local.date().isoformat(), "2026-01-16")

	def test_ordinary_riyadh_solar_cycle_still_belongs_to_local_day(self) -> None:
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		reading = self._read_local_noon(location, datetime(2026, 1, 15).date())
		assert reading.sunrise_local and reading.sunset_local
		self.assertEqual(reading.local_date.isoformat(), "2026-01-15")
		self.assertEqual(reading.sunrise_local.date(), reading.local_date)
		self.assertEqual(reading.sunset_local.date(), reading.local_date)

	def test_complete_reading_at_first_supported_local_day(self) -> None:
		# 1900-12-31 21:00 UTC is 1901-01-01 in Riyadh.  This also proves
		# that the previous new moon and season boundary may come from 1900.
		reading = self._read_riyadh(datetime(1900, 12, 31, 21, tzinfo=timezone.utc))
		self._assert_complete(reading)
		self.assertEqual(reading.local_date.isoformat(), "1901-01-01")
		self.assertEqual(reading.current_season_started.at_utc.year, 1900)
		self.assertEqual(reading.lunar.previous_new_moon_utc.year, 1900)
		self.assertIsNone(reading.daylight_change_from_previous_day)

	def test_february_1901_before_march_equinox_is_complete(self) -> None:
		reading = self._read_riyadh(datetime(1901, 2, 15, tzinfo=timezone.utc))
		self._assert_complete(reading)
		self.assertEqual(reading.current_season_started.event, SeasonEvent.DECEMBER_SOLSTICE)
		self.assertEqual(reading.current_season_started.at_utc.year, 1900)

	def test_complete_reading_after_december_solstice_2099(self) -> None:
		reading = self._read_riyadh(datetime(2099, 12, 31, 20, tzinfo=timezone.utc))
		self._assert_complete(reading)
		self.assertEqual(reading.local_date.isoformat(), "2099-12-31")
		self.assertEqual(reading.next_seasonal_event.at_utc.year, 2100)
		self.assertEqual(reading.lunar.next_new_moon_utc.year, 2100)
		self.assertEqual(reading.lunar.next_full_moon_utc.year, 2100)

	def test_local_requests_outside_the_public_range_still_fail(self) -> None:
		for moment in (
			datetime(1900, 6, 1, 12, tzinfo=timezone.utc),
			datetime(2100, 6, 1, 12, tzinfo=timezone.utc),
		):
			with self.subTest(moment=moment):
				with self.assertRaises(AstronomyRangeError):
					self._read_riyadh(moment)

	def test_date_line_timezone_preserves_both_supported_local_endpoints(self) -> None:
		location = Location(
			"kiritimati", "Kiritimati", 1.8721, -157.4278, "Pacific/Kiritimati",
		)
		for local_date in (datetime(1901, 1, 1).date(), datetime(2099, 12, 31).date()):
			with self.subTest(local_date=local_date):
				reading = self._read_local_noon(location, local_date)
				self._assert_complete(reading)
				self.assertEqual(reading.local_date, local_date)
				assert reading.sunrise_local and reading.sunset_local
				self.assertEqual(reading.sunrise_local.date(), local_date)
				self.assertEqual(reading.sunset_local.date(), local_date)

	def _read_riyadh(self, moment: datetime):
		clock = EventClock(Instant(moment))
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		return AstronomyService(clock, self.timezones).read(location)

	def test_daylight_change_matches_the_same_service_policy_for_previous_local_day(self) -> None:
		current = self._read_local_noon(
			Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh"),
			datetime(2026, 3, 1).date(),
		)
		previous = self._read_local_noon(
			Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh"),
			datetime(2026, 2, 28).date(),
		)
		self.assertEqual(
			current.daylight_change_from_previous_day,
			current.solar_day.daylight - previous.solar_day.daylight,
		)

	def _read_local_noon(self, location: Location, local_date):
		zone = self.timezones.get_timezone(location.timezone_id)
		local_noon = datetime(
			local_date.year, local_date.month, local_date.day, 12, tzinfo=zone,
		)
		clock = EventClock(Instant(local_noon.astimezone(timezone.utc)))
		return AstronomyService(clock, self.timezones).read(location)

	def _assert_complete(self, reading) -> None:
		self.assertIsNotNone(reading.current_season)
		self.assertIsNotNone(reading.current_season_started.at_utc)
		self.assertIsNotNone(reading.next_seasonal_event.at_utc)
		self.assertIsNotNone(reading.next_seasonal_event_local)
		self.assertIsNotNone(reading.observed_at_local.utcoffset())
		self.assertEqual(reading.solar_day.state, SolarDayState.NORMAL)
		self.assertIsNotNone(reading.sunrise_local)
		self.assertIsNotNone(reading.sunset_local)
		self.assertGreater(reading.solar_day.daylight, timedelta(0))
		self.assertGreater(reading.solar_day.night, timedelta(0))
		self.assertIsNotNone(reading.lunar.phase)
		self.assertGreaterEqual(reading.lunar.age_days, 0)
		self.assertGreaterEqual(reading.lunar.illumination_fraction, 0)
		self.assertLessEqual(reading.lunar.illumination_fraction, 1)
		self.assertGreater(
			reading.lunar.next_new_moon_utc,
			reading.lunar.previous_new_moon_utc,
		)
		self.assertIsNotNone(reading.next_new_moon_local.utcoffset())
		self.assertIsNotNone(reading.next_full_moon_local.utcoffset())
		self.assertEqual(reading.algorithm_version, ASTRONOMY_ALGORITHM_VERSION)


if __name__ == "__main__":
	unittest.main()
