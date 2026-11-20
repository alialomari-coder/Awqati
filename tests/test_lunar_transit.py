"""Task 2.2 contracts and exceptional civil dates; no legacy reference replay."""
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
import hashlib
import json
import math
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'addon/globalPlugins'),str(ROOT/'tools')]
from awqati.domain import (
    lunar_transit_day, lunar_horizon_events, LunarTransitState, MaximumKind, LunarEventState,
    AstronomyRangeError, Location, Instant,
)
from awqati.domain.lunar_transit import _civil_intervals
from awqati.domain.lunar_horizon import _topocentric
from awqati.application import AstronomyService
from awqati.infrastructure import BundledTimezoneProvider


class LunarTransitTests(unittest.TestCase):
    def setUp(self):
        self.zones=BundledTimezoneProvider()

    def calculate(self,text='2026-11-19',lat=26.4207,lon=50.0888,tz='Asia/Riyadh'):
        return lunar_transit_day(date.fromisoformat(text),lat,lon,self.zones.get_timezone(tz))

    def test_independent_horizons_full_day_and_maximum_replay(self):
        from verify_lunar_transit import compare
        r=compare()
        self.assertTrue(r['passed'])
        self.assertEqual(r['cases'],14)
        self.assertEqual(r['transits'],11)
        self.assertEqual(r['maxima'],14)

    def test_legacy_prayer_settings_synopsis_and_astronomy_preserved(self):
        values=json.loads((ROOT/'docs/lunar_transit_task22/preservation.json').read_text())
        from daily_synopsis_baseline import APPROVED_SYNOPSIS_SHA256
        values.update({path:sha for path,sha in APPROVED_SYNOPSIS_SHA256.items() if path in values})
        for path,sha in values.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),sha)

    def test_transit_root_upper_and_airless_center_altitude(self):
        r=self.calculate()
        self.assertEqual(r.transit_state,LunarTransitState.AVAILABLE)
        for p in r.transits:
            altitude,_,ha=_topocentric(p.at_utc,26.4207,50.0888)
            self.assertLess(abs(ha),1e-6)
            self.assertAlmostEqual(p.altitude_degrees,altitude,places=12)
            self.assertGreater(math.cos(ha),0)

    def test_affected_rise_set_calculation_matches_saved_pre22_values(self):
        # Regression snapshot only; do not rerun the approved USNO reference suite.
        r=lunar_horizon_events(date(2026,11,19),26.4207,50.0888,self.zones.get_timezone('Asia/Riyadh'))
        self.assertEqual([t.isoformat() for t in r.rises_local],['2026-11-19T13:08:20.143432+03:00'])
        self.assertEqual([t.isoformat() for t in r.sets_local],['2026-11-19T00:29:52.062378+03:00'])

    def test_maximum_can_precede_transit_and_near_zenith_stays_distinct(self):
        for text,lat,lon,tz in [('2026-06-01',78.2232,15.6469,'Arctic/Longyearbyen'),
                              ('2026-11-19',0,0,'UTC')]:
            r=self.calculate(text,lat,lon,tz)
            self.assertLess(r.maxima[0].at_utc,r.transits[0].at_utc)
            self.assertGreater(r.maxima[0].altitude_degrees,r.transits[0].altitude_degrees)

    def test_actual_maximum_is_distinct_from_transit(self):
        r=self.calculate()
        peak=r.maxima[0]
        self.assertEqual(peak.kind,MaximumKind.INTERIOR)
        self.assertTrue(peak.above_horizon)
        self.assertTrue(peak.attained)
        self.assertGreater((peak.at_utc-r.transits[0].at_utc).total_seconds(),120)
        self.assertGreater(peak.altitude_degrees,r.transits[0].altitude_degrees)
        for seconds in (-60,-1,1,60):
            self.assertLess(_topocentric(peak.at_utc+timedelta(seconds=seconds),26.4207,50.0888)[0],peak.altitude_degrees)

    def test_global_peak_dominates_independent_dense_local_samples(self):
        for text,lat,lon,tz in [('2026-11-19',26.4207,50.0888,'Asia/Riyadh'),
                ('2026-06-21',-33.8688,151.2093,'Australia/Sydney'),
                ('2026-06-01',90,0,'UTC'),('2026-06-01',-90,0,'UTC')]:
            r=self.calculate(text,lat,lon,tz)
            for start,end in r.civil_intervals_utc:
                t=start
                while t<end:
                    self.assertLessEqual(_topocentric(t,lat,lon)[0],r.maxima[0].altitude_degrees+1e-9)
                    t+=timedelta(minutes=7)

    def test_no_transit_and_start_boundary_are_not_substituted(self):
        r=self.calculate('2026-11-25')
        self.assertEqual(r.transit_state,LunarTransitState.NO_EVENT)
        self.assertFalse(r.transits)
        self.assertEqual(r.maxima[0].kind,MaximumKind.DAY_START)
        self.assertEqual(r.maxima[0].at_utc,r.civil_intervals_utc[0][0])

    def test_end_limit_is_not_an_attained_event_on_the_day(self):
        r=self.calculate('2026-06-01',-78,15.6469,'UTC')
        self.assertEqual(r.transit_state,LunarTransitState.NO_EVENT)
        self.assertEqual(r.maxima[0].kind,MaximumKind.DAY_END_LIMIT)
        self.assertFalse(r.maxima[0].attained)
        self.assertEqual(r.maxima_local[0].date(),date(2026,6,2))

    def test_below_horizon_all_day_never_implies_visibility(self):
        r=self.calculate('2026-06-01',78.2232,15.6469,'Arctic/Longyearbyen')
        self.assertTrue(r.center_below_horizon_all_day)
        self.assertFalse(r.maxima[0].above_horizon)
        self.assertLess(r.maxima[0].altitude_degrees,-16)
        self.assertTrue(all(not p.above_horizon for p in r.transits))

    def test_exact_poles_have_no_defined_local_meridian(self):
        for lat in (90,-90):
            r=self.calculate('2026-06-01',lat,0,'UTC')
            self.assertEqual(r.transit_state,LunarTransitState.UNDEFINED_MERIDIAN)
            self.assertFalse(r.transits)
            self.assertEqual(r.maximum_state,LunarEventState.AVAILABLE)
            s=self.calculate('2026-06-01',lat,179,'UTC')
            self.assertAlmostEqual(r.maxima[0].altitude_degrees,s.maxima[0].altitude_degrees,places=9)

    def test_repeated_47_hour_day_retains_both_transits(self):
        r=self.calculate('1969-09-30',8.7167,167.7333,'Pacific/Kwajalein')
        self.assertEqual(r.transit_state,LunarTransitState.MULTIPLE)
        self.assertEqual(len(r.transits),2)
        self.assertEqual((r.civil_intervals_utc[0][1]-r.civil_intervals_utc[0][0]).total_seconds(),47*3600)
        self.assertTrue(all(t.date()==r.local_date for t in r.transits_local))
        self.assertNotEqual(r.transits_local[0].utcoffset(),r.transits_local[1].utcoffset())
        self.assertEqual(len(r.maxima),1)
        self.assertGreater(r.maxima[0].altitude_degrees,max(p.altitude_degrees for p in r.transits))

    def test_skipped_date_has_no_peak_or_transit(self):
        r=self.calculate('2011-12-30',-13.8333,-171.75,'Pacific/Apia')
        self.assertFalse(r.civil_intervals_utc or r.transits or r.maxima)
        self.assertEqual(r.maximum_state,LunarEventState.NO_EVENT)
        self.assertEqual(r.transit_state,LunarTransitState.NO_EVENT)
        self.assertIsNone(r.center_below_horizon_all_day)

    def test_dst_day_length_and_per_instant_local_conversion(self):
        for text,tz,hours in [('2026-03-29','Europe/London',23),
                ('2026-10-25','Europe/London',25),('2026-04-05','Australia/Lord_Howe',24.5),
                ('2026-10-04','Australia/Sydney',23)]:
            r=self.calculate(text,tz=tz)
            self.assertEqual(sum((b-a).total_seconds() for a,b in r.civil_intervals_utc),hours*3600)
            for p,t in zip(r.transits,r.transits_local):
                self.assertEqual(t.date(),r.local_date)
                self.assertEqual(t.astimezone(timezone.utc),p.at_utc)

    def test_historical_midnight_gap_round_trips(self):
        zone=self.zones.get_timezone('America/Sao_Paulo')
        intervals=_civil_intervals(date(2018,11,4),zone)
        self.assertEqual(intervals[0][0].astimezone(zone).hour,1)
        self.assertEqual((intervals[0][1]-intervals[0][0]).total_seconds(),23*3600)

    def test_one_clock_read_location_zone_and_offline_service(self):
        clock=Mock()
        clock.now.return_value=Instant(datetime(2026,11,18,22,tzinfo=timezone.utc))
        location=Location('dammam','Dammam',26.4207,50.0888,'Asia/Riyadh')
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            r=AstronomyService(clock,self.zones).read_lunar_transit(location)
        clock.now.assert_called_once()
        self.assertEqual(r,self.calculate())

    def test_invalid_input_and_civil_year_endpoints(self):
        for text in ('1901-01-01','2099-12-31'):
            for zone in (timezone(timedelta(hours=14)),timezone(timedelta(hours=-12))):
                r=lunar_transit_day(date.fromisoformat(text),0,0,zone)
                self.assertNotEqual(r.maximum_state,LunarEventState.CALCULATION_ERROR)
                self.assertTrue(all(p.at_utc.astimezone(zone).date()==r.local_date for p in r.transits))
        for text in ('1900-01-01','2100-01-01'):
            with self.assertRaises(AstronomyRangeError): self.calculate(text)
        for lat,lon in ((91,0),(0,181),(math.nan,0),(0,math.inf)):
            with self.assertRaises(ValueError): self.calculate(lat=lat,lon=lon)
        class NaiveZone(tzinfo):
            def utcoffset(self,dt): return None
        for zone in (None,NaiveZone()):
            with self.assertRaises(ValueError): lunar_transit_day(date(2026,1,1),0,0,zone)

    def test_numerical_failure_is_distinct_from_no_event(self):
        with patch('awqati.domain.lunar_transit._topocentric',side_effect=ArithmeticError):
            r=self.calculate()
        self.assertEqual(r.transit_state,LunarTransitState.CALCULATION_ERROR)
        self.assertEqual(r.maximum_state,LunarEventState.CALCULATION_ERROR)
        self.assertIsNone(r.center_below_horizon_all_day)

    def test_half_open_boundary_transit(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        def coords(t,*_):
            seconds=(t-start).total_seconds()
            return 20+math.cos(seconds/86400),380000,seconds*2*math.pi/86400
        with patch('awqati.domain.lunar_transit._topocentric',side_effect=coords):
            r=self.calculate('2026-01-01',tz='UTC')
        self.assertEqual(tuple(p.at_utc for p in r.transits),(start,))

    def test_peak_close_to_day_start_is_not_lost_between_samples(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        def coords(t,*_):
            seconds=(t-start).total_seconds()
            return 30-((seconds-2)/86400)**2,380000,seconds*2*math.pi/86400
        with patch('awqati.domain.lunar_transit._topocentric',side_effect=coords):
            r=self.calculate('2026-01-01',tz='UTC')
        self.assertEqual(r.maxima[0].kind,MaximumKind.INTERIOR)
        self.assertAlmostEqual((r.maxima[0].at_utc-start).total_seconds(),2,delta=.03)

    def test_equal_global_maxima_are_preserved(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        def coords(t,*_):
            seconds=(t-start).total_seconds()
            return 30+math.sin(seconds*2*math.pi/(12*3600)),380000,seconds*2*math.pi/86400
        with patch('awqati.domain.lunar_transit._topocentric',side_effect=coords):
            r=self.calculate('2026-01-01',tz='UTC')
        self.assertEqual(r.maximum_state,LunarEventState.MULTIPLE)
        self.assertEqual(len(r.maxima),2)

    def test_stationary_maximum_exactly_at_end_stays_a_limit(self):
        end=datetime(2026,1,2,tzinfo=timezone.utc)
        def coords(t,*_):
            seconds=(t-end).total_seconds()
            return 30-(seconds/3600)**2,380000,seconds*2*math.pi/86400
        with patch('awqati.domain.lunar_transit._topocentric',side_effect=coords):
            r=self.calculate('2026-01-01',tz='UTC')
        self.assertEqual(len(r.maxima),1)
        self.assertEqual(r.maxima[0].kind,MaximumKind.DAY_END_LIMIT)


if __name__=='__main__': unittest.main()
