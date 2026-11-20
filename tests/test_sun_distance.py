"""Focused task 1.3 behavior and recorded, independent JPL acceptance."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'addon/globalPlugins'), str(ROOT / 'tests')]
from awqati.domain import sun_distance, SunDistance, AstronomyRangeError, Instant
from awqati.application import AstronomyService
from awqati.application.sun_distance_presentation import format_sun_distance_millions


class SunDistanceTests(unittest.TestCase):
    def test_known_ranges_and_seasonal_change(self):
        def distance(month, day):
            return sun_distance(datetime(2026, month, day, 12, tzinfo=timezone.utc)).distance_km
        near, far = distance(1, 3), distance(7, 6)
        self.assertTrue(147_000_000 < near < 147_200_000)
        self.assertTrue(152_000_000 < far < 152_200_000)
        self.assertLess(near, distance(1, 1))
        self.assertLess(near, distance(1, 8))
        self.assertGreater(far, distance(7, 1))
        self.assertGreater(far, distance(7, 11))

    def test_instant_changes_within_day_without_early_rounding(self):
        start = datetime(2026, 3, 20, tzinfo=timezone.utc)
        a = sun_distance(start)
        b = sun_distance(start + timedelta(hours=12))
        c = sun_distance(start + timedelta(seconds=1))
        self.assertGreater(b.distance_km - a.distance_km, 10_000)
        self.assertNotEqual(a.distance_km, c.distance_km)
        self.assertNotEqual(a.distance_km, round(a.distance_km))
        self.assertIsInstance(a, SunDistance)

    def test_same_absolute_instant_has_same_distance_in_any_zone(self):
        moment = datetime(2026, 3, 20, 12, 30, 15, 123456, tzinfo=timezone.utc)
        for hours in (-12, 3, 14):
            other = sun_distance(moment.astimezone(timezone(timedelta(hours=hours))))
            self.assertEqual(other, sun_distance(moment))
            self.assertEqual(other.observed_at_utc, moment)
            self.assertIs(other.observed_at_utc.tzinfo, timezone.utc)

    def test_aware_input_and_absolute_utc_range(self):
        with self.assertRaises(ValueError):
            sun_distance(datetime(2026, 1, 1))
        for text in ('1901-01-01T00:00:00+00:00', '2099-12-31T23:59:59+00:00',
                     '2100-01-01T12:00:00+14:00'):
            self.assertTrue(math.isfinite(sun_distance(datetime.fromisoformat(text)).distance_km))
        for text in ('1900-12-31T23:59:59+00:00', '2100-01-01T00:00:00+00:00',
                     '1901-01-01T00:00:00+14:00'):
            with self.assertRaises(AstronomyRangeError):
                sun_distance(datetime.fromisoformat(text))

    def test_service_reads_clock_once_each_request_without_location_or_network(self):
        first = datetime(2026, 3, 20, tzinfo=timezone.utc)
        clock, zones = Mock(), Mock()
        clock.now.side_effect = [Instant(first), Instant(first + timedelta(hours=12))]
        service = AstronomyService(clock, zones)
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            a, b = service.read_sun_distance(), service.read_sun_distance()
        self.assertEqual(clock.now.call_count, 2)
        self.assertEqual(zones.mock_calls, [])
        self.assertEqual(a, sun_distance(first))
        self.assertEqual(b, sun_distance(first + timedelta(hours=12)))
        self.assertNotEqual(a.distance_km, b.distance_km)

    def test_numeric_presentation_keeps_domain_precision(self):
        reading = sun_distance(datetime(2026, 1, 3, 12, tzinfo=timezone.utc))
        original = reading.distance_km
        self.assertEqual(format_sun_distance_millions(original), '147.1')
        self.assertEqual(format_sun_distance_millions(152_098_123.456), '152.1')
        self.assertEqual(format_sun_distance_millions(149_600_000), '149.6')
        self.assertEqual(reading.distance_km, original)
        for bad in (0, -1, math.inf, -math.inf, math.nan):
            with self.assertRaises(ValueError):
                format_sun_distance_millions(bad)

    def test_all_50_recorded_jpl_geometric_ranges(self):
        comparison = json.loads((ROOT / 'docs/sun_distance_task13/comparison.json').read_text())
        self.assertEqual(comparison['count'], 50)
        for row in comparison['results']:
            with self.subTest(utc=row['utc']):
                value = sun_distance(datetime.fromisoformat(row['utc'])).distance_km
                self.assertEqual(value, row['calculated_km'])
                self.assertLessEqual(abs(value - row['jpl_km']), comparison['tolerance_km'])
        references = {r['utc'][:10]: r['jpl_km'] for r in comparison['results']}
        self.assertLess(references['2026-01-03'], references['2026-01-01'])
        self.assertLess(references['2026-01-03'], references['2026-01-08'])
        self.assertGreater(references['2026-07-06'], references['2026-07-01'])
        self.assertGreater(references['2026-07-06'], references['2026-07-11'])


if __name__ == '__main__':
    unittest.main()
