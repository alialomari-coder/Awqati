"""Focused task 2.4 acceptance, boundaries and legacy-preservation checks."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'addon/globalPlugins'), str(ROOT/'tests')]
from awqati.domain import (
    PrincipalPhase as Phase, lunar_phase_events, upcoming_lunar_phases,
    AstronomyRangeError, Instant, Location,
)
from awqati.domain.lunar_phases import _event, _LEAPS
from awqati.domain.astronomy import lunar_phase_event_utc, _lunar_phase_jde_tt
from awqati.application import AstronomyService
from awqati.infrastructure import BundledTimezoneProvider
from awqati.application.lunar_phases_presentation import format_next_lunar_phase

UTC = timezone.utc
START = datetime(2026,1,1,tzinfo=UTC)
END = datetime(2027,1,1,tzinfo=UTC)
OUT = ROOT/'docs/lunar_phases_task24'


class LunarPhasesTests(unittest.TestCase):
    def setUp(self):
        self.events = lunar_phase_events(START, END)
        self.zones = BundledTimezoneProvider()

    def test_events_order_cycle_and_unique(self):
        self.assertEqual(len(self.events), 50)
        self.assertEqual(len({e.at_utc for e in self.events}), len(self.events))
        for a,b in zip(self.events,self.events[1:]):
            self.assertLess(a.at_utc,b.at_utc)
            self.assertEqual((tuple(Phase).index(a.phase)+1)%4, tuple(Phase).index(b.phase))

    def test_all_years_order_and_supported_endpoints(self):
        for y in range(1901,2100):
            events = lunar_phase_events(datetime(y,1,1,tzinfo=UTC),datetime(y+1,1,1,tzinfo=UTC))
            self.assertTrue(48<=len(events)<=51)
            for a,b in zip(events,events[1:]):
                self.assertLess(a.at_utc,b.at_utc)
            self.assertTrue(all(e.at_utc.year==y for e in events))

    def test_next_each_and_exact_instant_strict_contract(self):
        for event in self.events:
            before = upcoming_lunar_phases(event.at_utc-timedelta(microseconds=1))
            self.assertEqual(before.next_event,event)
            self.assertEqual(before.next_for(event.phase),event)
            at = upcoming_lunar_phases(event.at_utc)
            after = upcoming_lunar_phases(event.at_utc+timedelta(microseconds=1))
            self.assertNotIn(event,at.events)
            self.assertEqual(at.events,after.events)
            self.assertEqual({e.phase for e in at.events},set(Phase))
            self.assertTrue(all(e.at_utc>event.at_utc for e in at.events))

    def test_half_open_intervals_event_boundary(self):
        for event in self.events:
            low,high = event.at_utc-timedelta(seconds=1),event.at_utc+timedelta(seconds=1)
            self.assertEqual(lunar_phase_events(low,event.at_utc),())
            self.assertEqual(lunar_phase_events(event.at_utc,high),(event,))
            self.assertEqual(lunar_phase_events(low,high),(event,))
            self.assertEqual(lunar_phase_events(event.at_utc,event.at_utc),())

    def test_midnight_day_partition_in_real_zones(self):
        # Check both sides of local date boundaries around every phase,
        # including fractional offsets and DST, without comparing wall times.
        for zid in ('Asia/Riyadh','America/New_York','Australia/Lord_Howe','Pacific/Kiritimati'):
            zone = self.zones.get_timezone(zid)
            for event in self.events:
                local = event.local_time(zone)
                midnight = local.replace(hour=0,minute=0,second=0,microsecond=0)
                end = midnight+timedelta(days=1)
                self.assertIn(event,lunar_phase_events(midnight,end))
                self.assertNotIn(event,lunar_phase_events(midnight-timedelta(days=1),midnight))
                self.assertEqual(local.astimezone(UTC),event.at_utc)

    def test_near_local_midnight_reference_cases(self):
        near = []
        for event in self.events:
            for zid in ('Asia/Riyadh','America/New_York','Pacific/Kiritimati'):
                local = event.local_time(self.zones.get_timezone(zid))
                if local.hour in (0,23):
                    near.append((event,local))
        self.assertGreaterEqual(len(near),5)
        for event,local in near:
            self.assertEqual(upcoming_lunar_phases(event.at_utc-timedelta(seconds=1)).next_event,event)
            self.assertEqual(local.astimezone(UTC),event.at_utc)

    def test_dst_offset_is_at_future_event_not_request(self):
        zone = self.zones.get_timezone('America/New_York')
        request = datetime(2026,3,7,tzinfo=UTC)
        reading = upcoming_lunar_phases(request,zone)
        self.assertEqual(request.astimezone(zone).utcoffset(),timedelta(hours=-5))
        self.assertEqual(reading.next_local.utcoffset(),timedelta(hours=-4))
        self.assertEqual(reading.next_local.astimezone(UTC),reading.next_event.at_utc)

    def test_year_rollover_and_exclusive_upper_range(self):
        reading = upcoming_lunar_phases(datetime(2026,12,31,tzinfo=UTC))
        self.assertTrue(all(e.at_utc.year==2027 for e in reading.events))
        final = lunar_phase_events(datetime(2099,12,1,tzinfo=UTC),datetime(2100,1,1,tzinfo=UTC))[-1]
        before = upcoming_lunar_phases(final.at_utc-timedelta(microseconds=1))
        self.assertEqual(before.events,(final,))
        self.assertEqual(upcoming_lunar_phases(final.at_utc).events,())
        self.assertIsNone(upcoming_lunar_phases(final.at_utc).next_event)
        self.assertIsNone(upcoming_lunar_phases(final.at_utc).next_for(Phase.FULL_MOON))
        self.assertIsNone(upcoming_lunar_phases(final.at_utc).next_local)
        first = upcoming_lunar_phases(datetime(1901,1,1,tzinfo=UTC))
        self.assertTrue(all(e.at_utc.year==1901 for e in first.events))

    def test_input_range_is_absolute_utc(self):
        for t in (datetime(1900,12,31,23,59,tzinfo=UTC),datetime(2100,1,1,tzinfo=UTC)):
            with self.assertRaises(AstronomyRangeError):
                upcoming_lunar_phases(t)
        # Local year 2100 does not admit a UTC year 2100 event.
        t=datetime(2100,1,1,1,tzinfo=timezone(timedelta(hours=14)))
        self.assertEqual(upcoming_lunar_phases(t).events,())
        for a,b in ((START,datetime(2100,1,1,0,0,1,tzinfo=UTC)),):
            with self.assertRaises(AstronomyRangeError):
                lunar_phase_events(a,b)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            upcoming_lunar_phases(datetime(2026,1,1))
        with self.assertRaises(ValueError):
            lunar_phase_events(END,START)
        with self.assertRaises(ValueError):
            lunar_phase_events(START,datetime(2026,2,1))
        with self.assertRaises(ValueError):
            upcoming_lunar_phases(START).next_for('fullMoon')
        for k in (.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                _lunar_phase_jde_tt(k)
        with self.assertRaises(ValueError):
            lunar_phase_event_utc(.25)

    def test_leap_seconds_time_basis_and_tt_offset(self):
        for y in (1972,1980,2000,2015,2017,2026):
            event=upcoming_lunar_phases(datetime(y,8,1,tzinfo=UTC)).next_event
            tai = [n for yy,mm,n in _LEAPS if (yy,mm)<=(event.at_utc.year,event.at_utc.month)][-1]
            civil_tt=datetime(1970,1,1,tzinfo=UTC)+timedelta(days=event.jde_tt-2440587.5)
            self.assertAlmostEqual((civil_tt-event.at_utc).total_seconds(),32.184+tai,places=5)
            self.assertEqual(event.time_basis,'utcLeapSeconds')
        for y in (1901,1950,1965,2027,2050,2099):
            self.assertEqual(upcoming_lunar_phases(datetime(y,1,1,tzinfo=UTC)).next_event.time_basis,'modeledUT')

    def test_legacy_new_and_full_are_bit_identical(self):
        before=json.loads((OUT/'legacy_before.json').read_text(encoding='utf-8'))
        self.assertGreater(len(before),4000)
        for k,expected in before.items():
            self.assertEqual(lunar_phase_event_utc(float(k)).isoformat(),expected)

    def test_service_clock_once_and_bundled_location_zone(self):
        clock=Mock(); clock.now.return_value=Instant(START)
        zones=Mock(wraps=self.zones)
        location=Location('ny','New York',40.7,-74,'America/New_York')
        result=AstronomyService(clock,zones).read_lunar_phases(location)
        clock.now.assert_called_once_with()
        zones.get_timezone.assert_called_once_with('America/New_York')
        self.assertEqual(result.requested_at_utc,START)
        self.assertEqual(result.next_local.utcoffset(),timedelta(hours=-5))
        clock.reset_mock(); zones.reset_mock()
        AstronomyService(clock,zones).read_lunar_phases()
        clock.now.assert_called_once_with(); zones.get_timezone.assert_not_called()

    def test_current_synopsis_does_not_call_new_api(self):
        from support.event_clock import EventClock
        location=Location('r','Riyadh',24.7,46.7,'Asia/Riyadh')
        with patch('awqati.application.astronomy_service.upcoming_lunar_phases',side_effect=AssertionError):
            result=AstronomyService(EventClock(Instant(START)),self.zones).read(location)
        self.assertIsNotNone(result.lunar.next_new_moon_utc)

    def test_arabic_english_all_phase_names_and_local_callbacks(self):
        for event in self.events[:4]:
            zone=self.zones.get_timezone('Asia/Riyadh')
            date=Mock(return_value='DATE'); time=Mock(return_value='TIME')
            ar=format_next_lunar_phase(event,zone,'ar',date,time)
            en=format_next_lunar_phase(event,zone,'en',date,time)
            self.assertIn('DATE',ar); self.assertIn('TIME',ar)
            self.assertIn('DATE',en); self.assertIn('TIME',en)
            names=('المحاق','التربيع الأول','البدر','التربيع الأخير')
            self.assertIn(names[tuple(Phase).index(event.phase)],ar)
            self.assertTrue('Moon' in en or 'moon' in en)
            self.assertEqual(date.call_args.args[0],event.local_time(zone))
            self.assertEqual(time.call_args.args[0].utcoffset(),timedelta(hours=3))
        for lang in ('ar','en'):
            self.assertTrue(format_next_lunar_phase(None,UTC,lang,str,str))
        with self.assertRaises(ValueError):
            format_next_lunar_phase(self.events[0],UTC,'fr',str,str)

    def test_exact_local_midnight_and_end_of_day(self):
        event=self.events[0]
        # A fixed test zone places the computed instant exactly at midnight.
        tod=event.at_utc-event.at_utc.replace(hour=0,minute=0,second=0,microsecond=0)
        zone=timezone(-tod)
        local=event.local_time(zone)
        self.assertEqual((local.hour,local.minute,local.second,local.microsecond),(0,0,0,0))
        self.assertEqual(lunar_phase_events(local-timedelta(days=1),local),())
        self.assertEqual(lunar_phase_events(local,local+timedelta(days=1)),(event,))
        self.assertEqual(upcoming_lunar_phases(local-timedelta(microseconds=1)).next_event,event)
        self.assertNotEqual(upcoming_lunar_phases(local).next_event,event)

    def test_iers_saved_table_matches_runtime_constants(self):
        import hashlib
        meta=json.loads((OUT/'iers_request.json').read_text(encoding='utf-8-sig'))
        raw=(OUT/'iers_leap_seconds.dat').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['sha256'])
        table=[]
        for line in raw.decode().splitlines():
            if line.strip() and not line.startswith('#'):
                mjd,day,month,year,tai=line.split()
                table.append((int(year),int(month),int(tai)))
        self.assertEqual(tuple(table),_LEAPS)

    def test_saved_primary_jpl_acceptance(self):
        report=json.loads((OUT/'jpl_comparison.json').read_text(encoding='utf-8'))
        self.assertEqual(report['count'],96)
        self.assertLessEqual(report['max_absolute_seconds'],90)
        self.assertEqual(set(report['by_phase']),{p.value for p in Phase})


if __name__ == '__main__':
    unittest.main()
