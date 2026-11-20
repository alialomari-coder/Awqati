"""Task 2.3 behavior and independent saved geometric-vector acceptance."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'addon/globalPlugins'), str(ROOT/'tests')]
from awqati.domain import lunar_distance, LunarDistance, AstronomyRangeError, Instant
from awqati.domain.lunar_horizon import _position, _topocentric
from awqati.application import AstronomyService
from awqati.application.lunar_distance_presentation import (
    format_lunar_distance, format_lunar_distance_thousands,
)


class LunarDistanceTests(unittest.TestCase):
    def test_shared_radius_is_unrounded_and_not_observer_range(self):
        t = datetime(2026,11,19,12,tzinfo=timezone.utc)
        result = lunar_distance(t)
        self.assertIsInstance(result, LunarDistance)
        self.assertEqual(result.distance_km, _position(t)[2])
        self.assertNotEqual(result.distance_km, round(result.distance_km))
        self.assertNotEqual(result.distance_km, _topocentric(t,24.7,46.7)[1])

    def test_subsecond_and_intraday_changes(self):
        t = datetime(2026,11,19,tzinfo=timezone.utc)
        a = lunar_distance(t).distance_km
        self.assertNotEqual(a, lunar_distance(t+timedelta(milliseconds=1)).distance_km)
        self.assertGreater(a-lunar_distance(t+timedelta(hours=12)).distance_km, 2000)

    def test_same_instant_in_any_zone(self):
        t = datetime(2026,11,19,12,30,15,123456,tzinfo=timezone.utc)
        for hours in (-12,3,14):
            self.assertEqual(lunar_distance(t), lunar_distance(t.astimezone(timezone(timedelta(hours=hours)))))
        self.assertIs(lunar_distance(t).observed_at_utc.tzinfo, timezone.utc)

    def test_aware_input_and_utc_year_boundaries(self):
        with self.assertRaises(ValueError):
            lunar_distance(datetime(2026,1,1))
        for text in ('1901-01-01T00:00:00+00:00','2099-12-31T23:59:59+00:00','2100-01-01T12:00:00+14:00'):
            self.assertTrue(math.isfinite(lunar_distance(datetime.fromisoformat(text)).distance_km))
        for text in ('1900-12-31T23:59:59+00:00','2100-01-01T00:00:00+00:00','1901-01-01T00:00:00+14:00'):
            with self.assertRaises(AstronomyRangeError):
                lunar_distance(datetime.fromisoformat(text))

    def test_service_clock_once_per_request_no_location_zone_network_or_cache(self):
        t = datetime(2026,11,19,tzinfo=timezone.utc)
        clock, zones = Mock(), Mock()
        clock.now.side_effect = [Instant(t),Instant(t+timedelta(hours=12))]
        service = AstronomyService(clock,zones)
        with patch('socket.socket',side_effect=AssertionError('offline only')):
            a,b = service.read_lunar_distance(),service.read_lunar_distance()
        self.assertEqual(clock.now.call_count,2)
        self.assertEqual(zones.mock_calls,[])
        self.assertEqual(a,lunar_distance(t))
        self.assertEqual(b,lunar_distance(t+timedelta(hours=12)))

    def test_rounding_at_half_thousand_and_speech_templates(self):
        for value, expected in ((384499.999,'384'),(384500,'385'),(385500,'386'),(384000,'384')):
            self.assertEqual(format_lunar_distance_thousands(value),expected)
        self.assertEqual(format_lunar_distance(384500,'ar'), 'ويبعد القمر حاليًا عن الأرض نحو 385 ألف كيلومتر')
        self.assertEqual(format_lunar_distance(384500,'en'), 'And the Moon is currently about 385 thousand kilometers from Earth')
        reading = lunar_distance(datetime(2026,11,19,tzinfo=timezone.utc))
        original = reading.distance_km
        format_lunar_distance(reading.distance_km,'ar')
        self.assertEqual(reading.distance_km,original)
        with self.assertRaises(ValueError):
            format_lunar_distance(384000,'fr')

    def test_invalid_display_and_numerical_failure(self):
        for bad in (0,-1,math.inf,-math.inf,math.nan):
            with self.assertRaises(ValueError):
                format_lunar_distance_thousands(bad)
            with patch('awqati.domain.lunar_distance._position',return_value=(0,0,bad)):
                with self.assertRaises(ArithmeticError):
                    lunar_distance(datetime(2026,11,19,tzinfo=timezone.utc))

    def test_all_jpl_geometric_ranges_and_monthly_extremes(self):
        report = json.loads((ROOT/'docs/lunar_distance_task23/comparison.json').read_text())
        self.assertEqual(report['count'],41)
        self.assertEqual(report['tolerance_km'],20)
        for row in report['results']:
            with self.subTest(utc=row['utc']):
                value = lunar_distance(datetime.fromisoformat(row['utc'])).distance_km
                self.assertEqual(value,row['calculated_km'])
                self.assertLessEqual(abs(value-row['jpl_km']),20)
        month = [r for r in report['results'] if r['utc'].startswith('2026-11')]
        near = min(month,key=lambda r:r['jpl_km'])
        far = max(month,key=lambda r:r['jpl_km'])
        self.assertTrue(near['utc'].startswith('2026-11-26'))
        self.assertTrue(far['utc'].startswith('2026-11-14'))
        self.assertLess(near['calculated_km'],360000)
        self.assertGreater(far['calculated_km'],405000)


if __name__ == '__main__':
    unittest.main()
