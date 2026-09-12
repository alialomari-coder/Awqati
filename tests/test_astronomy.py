from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.domain import (  # noqa: E402
	ASTRONOMY_ALGORITHM_VERSION,
	ASTRONOMY_MAX_YEAR,
	ASTRONOMY_MIN_YEAR,
	AstronomyRangeError,
	classify_moon_phase,
	MoonPhase,
	Season,
	SeasonEvent,
	SolarDayState,
	delta_t_seconds,
	lunar_facts,
	lunar_phase_event_utc,
	next_seasonal_event,
	season_at,
	seasonal_event_utc,
	solar_day,
)


UTC = timezone.utc


class SeasonalAstronomyTests(unittest.TestCase):
	def assertWithin(self, actual: datetime, expected: datetime, tolerance: timedelta) -> None:
		self.assertLessEqual(abs(actual - expected), tolerance, (actual, expected))

	def test_2026_four_events_match_usno_to_two_minutes(self) -> None:
		# USNO Earth Seasons service, UTC values (retrieved 2026-09-13).
		references = {
			SeasonEvent.MARCH_EQUINOX: datetime(2026, 3, 20, 14, 46, tzinfo=UTC),
			SeasonEvent.JUNE_SOLSTICE: datetime(2026, 6, 21, 8, 24, tzinfo=UTC),
			SeasonEvent.SEPTEMBER_EQUINOX: datetime(2026, 9, 23, 0, 5, tzinfo=UTC),
			SeasonEvent.DECEMBER_SOLSTICE: datetime(2026, 12, 21, 20, 50, tzinfo=UTC),
		}
		for event, expected in references.items():
			with self.subTest(event=event):
				self.assertWithin(seasonal_event_utc(2026, event), expected, timedelta(minutes=2))

	def test_before_at_after_boundary_and_strictly_next(self) -> None:
		event = seasonal_event_utc(2026, SeasonEvent.MARCH_EQUINOX)
		self.assertEqual(season_at(event - timedelta(microseconds=1), 24)[0], Season.WINTER)
		self.assertEqual(season_at(event, 24)[0], Season.SPRING)
		self.assertEqual(season_at(event + timedelta(microseconds=1), 24)[0], Season.SPRING)
		self.assertEqual(next_seasonal_event(event).event, SeasonEvent.JUNE_SOLSTICE)

	def test_southern_hemisphere_and_equator_policy(self) -> None:
		july = datetime(2026, 7, 1, tzinfo=UTC)
		self.assertEqual(season_at(july, -33.9)[0], Season.WINTER)
		self.assertEqual(season_at(july, 0.0)[0], Season.SUMMER)

	def test_supported_range_and_delta_t_are_explicit(self) -> None:
		self.assertEqual((ASTRONOMY_MIN_YEAR, ASTRONOMY_MAX_YEAR), (1901, 2099))
		self.assertTrue(60 < delta_t_seconds(2026) < 90)
		for year in (1900, 2100):
			with self.assertRaises(AstronomyRangeError):
				seasonal_event_utc(year, SeasonEvent.MARCH_EQUINOX)


class SolarAstronomyTests(unittest.TestCase):
	def test_noaa_riyadh_reference_and_complementary_day_night(self) -> None:
		result = solar_day(date(2026, 9, 13), 24.7136, 46.6753)
		self.assertEqual(result.state, SolarDayState.NORMAL)
		self.assertIsNotNone(result.sunrise_utc)
		self.assertIsNotNone(result.sunset_utc)
		assert result.sunrise_utc and result.sunset_utc
		self.assertLessEqual(
			abs(result.sunrise_utc - datetime(2026, 9, 13, 2, 39, tzinfo=UTC)),
			timedelta(minutes=2),
		)
		self.assertLessEqual(
			abs(result.sunset_utc - datetime(2026, 9, 13, 15, 0, tzinfo=UTC)),
			timedelta(minutes=2),
		)
		self.assertEqual(result.daylight + result.night, timedelta(days=1))

	def test_southern_summer_has_a_long_day(self) -> None:
		result = solar_day(date(2026, 1, 15), -33.8688, 151.2093)
		self.assertEqual(result.state, SolarDayState.NORMAL)
		self.assertGreater(result.daylight, timedelta(hours=14))
		self.assertLess(result.night, timedelta(hours=10))

	def test_polar_day_and_night_are_explicit_without_prayer_fallback(self) -> None:
		summer = solar_day(date(2026, 6, 21), 78.2232, 15.6469)
		winter = solar_day(date(2026, 12, 21), 78.2232, 15.6469)
		self.assertEqual(summer.state, SolarDayState.POLAR_DAY)
		self.assertEqual((summer.sunrise_utc, summer.sunset_utc), (None, None))
		self.assertEqual((summer.daylight, summer.night), (timedelta(days=1), timedelta(0)))
		self.assertEqual(winter.state, SolarDayState.POLAR_NIGHT)
		self.assertEqual((winter.daylight, winter.night), (timedelta(0), timedelta(days=1)))


class LunarAstronomyTests(unittest.TestCase):
	def assertWithin(self, actual: datetime, expected: datetime, tolerance: timedelta) -> None:
		self.assertLessEqual(abs(actual - expected), tolerance, (actual, expected))

	def test_new_and_full_moon_match_usno_2026_table(self) -> None:
		# k=330 and 330.5 correspond to USNO 2026 Sep 11/26 entries.
		self.assertWithin(
			lunar_phase_event_utc(330),
			datetime(2026, 9, 11, 3, 27, tzinfo=UTC),
			timedelta(minutes=2),
		)
		self.assertWithin(
			lunar_phase_event_utc(330.5),
			datetime(2026, 9, 26, 16, 49, tzinfo=UTC),
			timedelta(minutes=2),
		)

	def test_intermediate_phase_age_illumination_and_next_events(self) -> None:
		moment = datetime(2026, 9, 13, tzinfo=UTC)
		facts = lunar_facts(moment)
		self.assertEqual(facts.phase, MoonPhase.WAXING_CRESCENT)
		self.assertAlmostEqual(facts.age_days, 1.856, delta=0.01)
		self.assertAlmostEqual(facts.illumination_fraction, 0.041, delta=0.01)
		self.assertWithin(facts.next_new_moon_utc, datetime(2026, 10, 10, 15, 50, tzinfo=UTC), timedelta(minutes=2))
		self.assertWithin(facts.next_full_moon_utc, datetime(2026, 9, 26, 16, 49, tzinfo=UTC), timedelta(minutes=2))

	def test_usno_daily_illumination_reference(self) -> None:
		# USNO Fraction of Moon Illuminated table: 2026-09-01 12:00 UT = 0.80.
		facts = lunar_facts(datetime(2026, 9, 1, 12, tzinfo=UTC))
		self.assertEqual(facts.phase, MoonPhase.WANING_GIBBOUS)
		self.assertAlmostEqual(facts.illumination_fraction, 0.80, delta=0.01)

	def test_event_equality_is_not_returned_as_next(self) -> None:
		event = lunar_phase_event_utc(330)
		facts = lunar_facts(event)
		self.assertEqual(facts.previous_new_moon_utc, event)
		self.assertGreater(facts.next_new_moon_utc, event)
		self.assertWithin(facts.next_new_moon_utc, datetime(2026, 10, 10, 15, 50, tzinfo=UTC), timedelta(minutes=2))

	def test_all_eight_phase_sector_boundaries_are_deterministic(self) -> None:
		phases = (
			MoonPhase.NEW_MOON, MoonPhase.WAXING_CRESCENT,
			MoonPhase.FIRST_QUARTER, MoonPhase.WAXING_GIBBOUS,
			MoonPhase.FULL_MOON, MoonPhase.WANING_GIBBOUS,
			MoonPhase.LAST_QUARTER, MoonPhase.WANING_CRESCENT,
		)
		for index, expected in enumerate(phases):
			center = index * 45
			with self.subTest(center=center):
				self.assertEqual(classify_moon_phase(center), expected)
				self.assertEqual(classify_moon_phase(center + 22.499999), expected)
				self.assertEqual(classify_moon_phase(center - 22.5), expected)
		self.assertEqual(classify_moon_phase(337.5), MoonPhase.NEW_MOON)


if __name__ == "__main__":
	unittest.main()
