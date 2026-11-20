"""Task 2.1 contracts, adversarial civil days and independent USNO replay."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import math
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'addon/globalPlugins'), str(ROOT/'tools')]
from awqati.domain import lunar_horizon_events, LunarEventState, AstronomyRangeError, Location, Instant
from awqati.domain.lunar_horizon import _crossings, _horizon_residual, _position
from awqati.application import AstronomyService
from awqati.application.lunar_horizon_presentation import format_lunar_horizon
from awqati.infrastructure import BundledTimezoneProvider


class LunarHorizonTests(unittest.TestCase):
    def setUp(self):
        self.zones = BundledTimezoneProvider()
        self.zone = self.zones.get_timezone('Asia/Riyadh')

    def calculate(self, day=date(2026,11,19), lat=26.4207, lon=50.0888, zone=None):
        return lunar_horizon_events(day, lat, lon, zone or self.zone)

    def test_independent_usno_replay_all_cases_and_event_counts(self):
        from verify_lunar_horizon import compare
        result = compare()
        self.assertTrue(result['passed'])
        self.assertGreaterEqual(result['cases'],28)
        self.assertGreaterEqual(result['compared_events'],44)

    def test_legacy_astronomy_prayer_settings_and_synopsis_sources_unchanged(self):
        values = json.loads((ROOT/'docs/lunar_horizon_task21/preservation.json').read_text())
        from daily_synopsis_baseline import APPROVED_SYNOPSIS_SHA256
        values.update({path:sha for path,sha in APPROVED_SYNOPSIS_SHA256.items() if path in values})
        for path, expected in values.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(), expected)

    def test_offline_service_uses_one_clock_read_and_location_zone(self):
        clock = Mock()
        clock.now.return_value = Instant(datetime(2026,11,18,22,tzinfo=timezone.utc))
        location = Location('dammam','Dammam',26.4207,50.0888,'Asia/Riyadh')
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            result = AstronomyService(clock,self.zones).read_lunar_horizon(location)
        self.assertEqual(result.local_date,date(2026,11,19))
        self.assertEqual(result,self.calculate())
        clock.now.assert_called_once()

    def test_rise_and_set_residuals_cross_in_correct_direction(self):
        result = self.calculate()
        for values, direction in [(result.rises_utc,1),(result.sets_utc,-1)]:
            for t in values:
                self.assertLess(abs(_horizon_residual(t,26.4207,50.0888)),.0001)
                self.assertLess(direction*_horizon_residual(t-timedelta(seconds=1),26.4207,50.0888),0)
                self.assertGreater(direction*_horizon_residual(t+timedelta(seconds=1),26.4207,50.0888),0)

    def test_adjacent_day_events_never_substituted(self):
        result = self.calculate(date(2026,12,31))
        self.assertEqual(result.rises_utc,())
        self.assertEqual(result.rise_state,LunarEventState.NO_EVENT)
        self.assertEqual(result.set_state,LunarEventState.AVAILABLE)

    def test_polar_days_and_both_exact_poles(self):
        for lat in (69.6492,78.2232,90,-90):
            result = self.calculate(date(2026,6,1),lat,18.9553)
            self.assertNotEqual(result.rise_state,LunarEventState.CALCULATION_ERROR)
            self.assertNotEqual(result.set_state,LunarEventState.CALCULATION_ERROR)
        polar=self.calculate(date(2026,6,1),69.6492,18.9553)
        self.assertFalse(polar.rises_utc or polar.sets_utc)

    def test_repeated_47_hour_date_preserves_multiple_events(self):
        zone=self.zones.get_timezone('Pacific/Kwajalein')
        result=self.calculate(date(1969,9,30),8.7167,167.7333,zone)
        self.assertEqual(result.rise_state,LunarEventState.MULTIPLE)
        self.assertEqual(result.set_state,LunarEventState.MULTIPLE)
        self.assertEqual(len(result.rises_utc),2)
        self.assertEqual(len(result.sets_utc),2)
        self.assertNotEqual(result.rises_local[0].utcoffset(),result.rises_local[1].utcoffset())

    def test_skipped_date_has_no_events(self):
        result=self.calculate(date(2011,12,30),-13.8333,-171.75,self.zones.get_timezone('Pacific/Apia'))
        self.assertFalse(result.rises_utc or result.sets_utc)
        self.assertEqual(result.rise_state,LunarEventState.NO_EVENT)

    def test_dst_offsets_at_each_instant(self):
        result=self.calculate(date(2026,10,4),-33.8688,151.2093,self.zones.get_timezone('Australia/Sydney'))
        self.assertEqual(result.rises_local[0].utcoffset(),timedelta(hours=10))
        self.assertEqual(result.sets_local[0].utcoffset(),timedelta(hours=11))

    def test_endpoint_civil_years_and_invalid_inputs(self):
        for year in (1901,2099):
            for zone in (timezone(timedelta(hours=14)),timezone(timedelta(hours=-12))):
                r=self.calculate(date(year,1,1),zone=zone)
                self.assertTrue(all(t.astimezone(zone).date()==r.local_date for t in r.rises_utc+r.sets_utc))
        for year in (1900,2100):
            with self.assertRaises(AstronomyRangeError): self.calculate(date(year,1,1))
        for lat,lon in ((91,0),(0,181),(math.nan,0),(0,math.inf)):
            with self.assertRaises(ValueError): self.calculate(lat=lat,lon=lon)
        with self.assertRaises(ValueError): lunar_horizon_events(date(2026,1,1),0,0,None)

    def test_numerical_failure_is_not_reported_as_absence(self):
        with patch('awqati.domain.lunar_horizon._position',side_effect=ArithmeticError):
            r=self.calculate()
        self.assertEqual(r.rise_state,LunarEventState.CALCULATION_ERROR)
        self.assertEqual(r.set_state,LunarEventState.CALCULATION_ERROR)

    def test_meeus_chapter47_worked_example(self):
        # Meeus 1992 April 12 0h TT: true longitude 133.162655,
        # latitude -3.229126, radius 368409.7 km. Undo apparent conversion.
        from awqati.domain.astronomy import _delta_t_seconds, _obliquity_correction
        from awqati.domain.lunar_horizon import _nutation
        tt=datetime(1992,4,12,tzinfo=timezone.utc)
        ra,dec,radius=_position(tt-timedelta(seconds=_delta_t_seconds(1992,4)))
        t=(2448724.5-2451545)/36525
        eps=math.radians(_obliquity_correction(t))
        x,y,z=math.cos(dec)*math.cos(ra),math.cos(dec)*math.sin(ra),math.sin(dec)
        lon=math.degrees(math.atan2(y*math.cos(eps)+z*math.sin(eps),x))%360-_nutation(t)
        lat=math.degrees(math.asin(z*math.cos(eps)-y*math.sin(eps)))
        self.assertAlmostEqual(lon,133.162655,places=5)
        self.assertAlmostEqual(lat,-3.229126,places=5)
        self.assertAlmostEqual(radius,368409.7,delta=.1)

    def test_close_pair_of_crossings_hidden_between_grid_points(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        f=lambda t: ((t-start).total_seconds()-710)**2-4
        values=_crossings(f,start,start+timedelta(hours=1))
        self.assertEqual([up for _,up in values],[False,True])
        self.assertAlmostEqual((values[0][0]-start).total_seconds(),708,delta=.03)
        self.assertAlmostEqual((values[1][0]-start).total_seconds(),712,delta=.03)

    def test_real_shallow_pair_hidden_within_one_ten_minute_step(self):
        r=self.calculate(date(2026,6,1),61.937,179.2,timezone.utc)
        self.assertEqual(len(r.rises_utc),1)
        self.assertEqual(len(r.sets_utc),1)
        self.assertEqual(r.rises_utc[0].hour,12)
        self.assertEqual(r.sets_utc[0].hour,12)
        self.assertGreater(r.rises_utc[0].minute,50)
        self.assertLess(r.sets_utc[0].minute,60)
        for minute in (50,60):
            t=datetime(2026,6,1,12,tzinfo=timezone.utc)+timedelta(minutes=minute)
            self.assertLess(_horizon_residual(t,61.937,179.2),0)
        absent=self.calculate(date(2026,6,1),61.95,179.2,timezone.utc)
        self.assertFalse(absent.rises_utc or absent.sets_utc)

    def test_exact_grid_root_and_tangent(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        f=lambda t: (t-start).total_seconds()-600
        values=_crossings(f,start,start+timedelta(hours=1))
        self.assertEqual(values,[(start+timedelta(seconds=600),True)])
        self.assertEqual(_crossings(lambda t:f(t)**2,start,start+timedelta(hours=1)),[])

    def test_half_open_local_date_boundary(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        # Crossings at midnight belong to the new day only.
        with patch('awqati.domain.lunar_horizon._horizon_residual',side_effect=lambda t,*_: (t-start).total_seconds()):
            previous=self.calculate(date(2025,12,31),zone=timezone.utc)
            current=self.calculate(date(2026,1,1),zone=timezone.utc)
        self.assertEqual(previous.rises_utc,())
        self.assertEqual(current.rises_utc,(start,))

    def test_future_prose_both_single_absent_and_error(self):
        r=self.calculate()
        clock=lambda t:t.strftime('%H:%M')
        self.assertEqual(format_lunar_horizon(r,'ar',clock),'يغرب القمر اليوم عند الساعة 00:29، ويشرق عند الساعة 13:08.')
        self.assertEqual(format_lunar_horizon(r,'en',clock),'The Moon sets today at 00:29, and rises at 13:08.')
        for rises,sets in [(r.rises_utc,()),((),r.sets_utc),((),())]:
            other=replace(r,rises_utc=rises,sets_utc=sets,
                rise_state=LunarEventState.AVAILABLE if rises else LunarEventState.NO_EVENT,
                set_state=LunarEventState.AVAILABLE if sets else LunarEventState.NO_EVENT)
            for lang in ('ar','en'):
                text=format_lunar_horizon(other,lang,clock)
                self.assertTrue(text)
                self.assertNotIn('None',text)
                if not rises: self.assertIn('لا يشرق' if lang=='ar' else 'does not rise',text)
                if not sets: self.assertIn('لا يغرب' if lang=='ar' else 'does not set',text)
        other=replace(r,rises_utc=(),rise_state=LunarEventState.CALCULATION_ERROR)
        self.assertIn('تعذر',format_lunar_horizon(other,'ar',clock))
        self.assertIn('could not',format_lunar_horizon(other,'en',clock))
        with self.assertRaises(ValueError): format_lunar_horizon(r,'fr',clock)

    def test_multiple_prose_preserves_offset_disambiguation(self):
        r=self.calculate(date(1969,9,30),8.7167,167.7333,self.zones.get_timezone('Pacific/Kwajalein'))
        for language in ('ar','en'):
            text=format_lunar_horizon(r,language,lambda t:t.strftime('%H:%M'))
            self.assertEqual(text.count('UTC+1100'),2)
            self.assertEqual(text.count('UTC-1200'),2)


if __name__=='__main__': unittest.main()
