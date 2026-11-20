"""Offline transit contracts and independent saved JPL DE441 comparisons."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'addon/globalPlugins'), str(ROOT / 'tests')]
from awqati.domain import SolarTransitState, SolarDayState, solar_day, AstronomyRangeError, Location, Instant
from awqati.application import AstronomyService
from awqati.application.daily_info_formatters import ArabicDailyInfoFormatter, EnglishDailyInfoFormatter
from awqati.infrastructure import BundledTimezoneProvider
from support.event_clock import EventClock


class SolarTransitTests(unittest.TestCase):
    def setUp(self):
        self.zones = BundledTimezoneProvider()

    def calculate(self, day, lat=24.7136, lon=46.6753, tz='Asia/Riyadh'):
        return solar_day(day, lat, lon, transit_zone=self.zones.get_timezone(tz))

    def test_independent_jpl_36_cases(self):
        rows = json.loads((ROOT / 'docs/solar_transit_task11/comparisons.json').read_text())
        self.assertEqual(36, len(rows))
        for row in rows:
            with self.subTest(site=row['site'], day=row['date']):
                result = self.calculate(date.fromisoformat(row['date']), row['latitude'], row['longitude'], row['timezone'])
                reference = datetime.fromisoformat(row['reference_local'])
                self.assertLessEqual(abs((result.transit_utc - reference).total_seconds()), 15)
                self.assertAlmostEqual(result.transit_altitude_degrees, row['reference_altitude'], delta=0.02)
                self.assertEqual(result.transit_state, SolarTransitState.AVAILABLE)

    def test_sites_have_distinct_times(self):
        day = date(2026, 3, 20)
        self.assertNotEqual(self.calculate(day).transit_utc, self.calculate(day, 26.4207, 50.0888).transit_utc)

    def test_northern_and_southern_seasons(self):
        for lat, lon, tz, summer, winter in (
            (24.7136, 46.6753, 'Asia/Riyadh', date(2026, 6, 21), date(2026, 12, 21)),
            (-33.8688, 151.2093, 'Australia/Sydney', date(2026, 12, 21), date(2026, 6, 21)),
        ):
            self.assertGreater(self.calculate(summer, lat, lon, tz).transit_altitude_degrees,
                self.calculate(winter, lat, lon, tz).transit_altitude_degrees)

    def test_polar_day_and_night_still_have_transit(self):
        for day, state, sign in ((date(2026, 6, 21), SolarDayState.POLAR_DAY, 1),
                (date(2026, 12, 21), SolarDayState.POLAR_NIGHT, -1)):
            result = self.calculate(day, 78.2232, 15.6469, 'Arctic/Longyearbyen')
            self.assertEqual(result.state, state)
            self.assertIsNone(result.sunrise_utc)
            self.assertEqual(result.transit_state, SolarTransitState.AVAILABLE)
            self.assertGreater(result.transit_altitude_degrees * sign, 0)

    def test_exact_poles_have_no_unique_upper_culmination(self):
        for lat in (-90, 90):
            result = self.calculate(date(2026, 6, 21), lat, 0, 'UTC')
            self.assertEqual(result.transit_state, SolarTransitState.UNDEFINED_AT_POLE)
            self.assertIsNone(result.transit_utc)
            self.assertIsNone(result.transit_altitude_degrees)

    def test_local_date_line_and_supported_endpoints(self):
        for day in (date(1901, 1, 1), date(2099, 12, 31), date(2026, 1, 1), date(2026, 12, 31)):
            for lat, lon, tz in ((1.8721, -157.4278, 'Pacific/Kiritimati'),
                    (-14.2756, -170.702, 'Pacific/Pago_Pago'), (0, 180, 'Pacific/Tarawa')):
                with self.subTest(day=day, tz=tz):
                    result = self.calculate(day, lat, lon, tz)
                    self.assertEqual(result.transit_utc.astimezone(self.zones.get_timezone(tz)).date(), day)
                    self.assertEqual(result.transit_utc.utcoffset(), timedelta(0))

    def test_dst_offset_at_transit(self):
        for tz, lat, lon, before, after, first, second in (
            ('Europe/London', 51.5074, -0.1278, '2026-03-28', '2026-03-29', 0, 1),
            ('Africa/Cairo', 30.0444, 31.2357, '2026-04-23', '2026-04-24', 2, 3),
            ('Australia/Sydney', -33.8688, 151.2093, '2026-04-04', '2026-04-05', 11, 10),
        ):
            zone = self.zones.get_timezone(tz)
            a = self.calculate(date.fromisoformat(before), lat, lon, tz).transit_utc
            b = self.calculate(date.fromisoformat(after), lat, lon, tz).transit_utc
            self.assertEqual(a.astimezone(zone).utcoffset(), timedelta(hours=first))
            self.assertEqual(b.astimezone(zone).utcoffset(), timedelta(hours=second))
            self.assertAlmostEqual((b - a).total_seconds(), 86400, delta=40)

    def test_skipped_civil_date_no_fabricated_result(self):
        result = self.calculate(date(2011, 12, 30), -13.833, -171.75, 'Pacific/Apia')
        self.assertEqual(result.transit_state, SolarTransitState.NO_TRANSIT)
        self.assertIsNone(result.transit_utc)
        self.assertIsNone(result.transit_altitude_degrees)

    def test_repeated_civil_date_reports_ambiguity(self):
        # A mismatched but valid longitude/zone can put two upper transits into
        # the 25-hour civil day when clocks turn back. Do not choose arbitrarily.
        result = self.calculate(date(2026, 10, 25), 51.5, -176, 'Europe/London')
        self.assertEqual(result.transit_state, SolarTransitState.MULTIPLE_TRANSITS)
        self.assertIsNone(result.transit_utc)

    def test_invalid_inputs_and_public_range(self):
        for lat, lon in ((float('nan'), 0), (0, float('inf')), (91, 0), (0, -181)):
            with self.assertRaises(ValueError):
                self.calculate(date(2026, 1, 1), lat, lon)
        for year in (1900, 2100):
            with self.assertRaises(AstronomyRangeError):
                self.calculate(date(year, 1, 1))

    def test_repeat_is_deterministic(self):
        self.assertEqual(self.calculate(date(2026, 1, 1)), self.calculate(date(2026, 1, 1)))

    def test_sunrise_sunset_intervals_unaffected_by_transit(self):
        day = date(2026, 6, 21)
        actual = self.calculate(day)
        with patch('awqati.domain.astronomy._solar_transit', return_value=(None, None, SolarTransitState.NO_TRANSIT)):
            baseline = self.calculate(day)
        for field in ('state', 'sunrise_utc', 'sunset_utc', 'next_sunrise_utc', 'daylight', 'night'):
            self.assertEqual(getattr(actual, field), getattr(baseline, field))

    def test_service_local_now_and_formatters_do_not_display_transit(self):
        location = Location('k', 'Kiritimati', 1.8721, -157.4278, 'Pacific/Kiritimati')
        clock = EventClock(Instant(datetime(2025, 12, 31, 23, tzinfo=timezone.utc)))
        reading = AstronomyService(clock, self.zones).read(location)
        self.assertEqual(reading.local_date, date(2026, 1, 1))
        self.assertEqual(reading.solar_transit_local.date(), reading.local_date)
        self.assertEqual(reading.solar_transit_local.utcoffset(), timedelta(hours=14))
        absent = replace(reading, solar_day=replace(reading.solar_day, transit_utc=None,
            transit_altitude_degrees=None, transit_state=SolarTransitState.NO_TRANSIT))
        self.assertIsNone(absent.solar_transit_local)
        for formatter in (ArabicDailyInfoFormatter(), EnglishDailyInfoFormatter()):
            self.assertEqual(formatter.format_scientific(reading), formatter.format_scientific(absent))


if __name__ == '__main__':
    unittest.main()
