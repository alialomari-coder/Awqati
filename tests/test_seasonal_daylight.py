"""Task 1.2 contracts, deliberately excluding task 1.1 reference reruns."""
from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'addon/globalPlugins'), str(ROOT / 'tests')]
from awqati.domain.astronomy import (
    annual_daylight, seasonal_daylight, solar_day_for_local_date, _daylight_extreme,
    DaylightSample, Season, SeasonEvent, seasonal_event_utc, AstronomyRangeError,
)
from awqati.domain import Location, Instant
from awqati.application import AstronomyService
from awqati.infrastructure import BundledTimezoneProvider
from support.event_clock import EventClock

class SeasonalDaylightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zones = BundledTimezoneProvider()

    def facts(self, text, lat=24.7136, lon=46.6753, tz='Asia/Riyadh'):
        zone = self.zones.get_timezone(tz)
        moment = datetime.fromisoformat(text).replace(tzinfo=zone)
        return seasonal_daylight(moment, lat, lon, zone)

    def test_signed_change_and_hemispheres(self):
        for lat, lon, tz in ((24.7136, 46.6753, 'Asia/Riyadh'), (-33.8688, 151.2093, 'Australia/Sydney')):
            for month, event in ((3, SeasonEvent.DECEMBER_SOLSTICE), (9, SeasonEvent.JUNE_SOLSTICE)):
                f = self.facts(f'2026-{month:02}-15T12:00', lat, lon, tz)
                self.assertEqual(f.reference.event, event)
                self.assertEqual(f.change, f.current.daylight - f.reference_day.daylight)
                summer = (month == 9) == (lat >= 0)
                self.assertEqual(f.reference_season, Season.SUMMER if summer else Season.WINTER)
                self.assertEqual(f.change < timedelta(), summer)

    def test_solstice_switches_at_instant_not_midnight(self):
        zone = self.zones.get_timezone('Asia/Riyadh')
        for event in (SeasonEvent.JUNE_SOLSTICE, SeasonEvent.DECEMBER_SOLSTICE):
            moment = seasonal_event_utc(2026, event)
            before = seasonal_daylight(moment - timedelta(microseconds=1), 24.7, 46.7, zone)
            after = seasonal_daylight(moment, 24.7, 46.7, zone)
            self.assertNotEqual(before.reference.event, event)
            self.assertEqual(after.reference.event, event)
            self.assertEqual(after.change, timedelta())

    def test_annual_exhaustive_selection_and_nights(self):
        for lat, lon, tz in ((24.7136, 46.6753, 'Asia/Riyadh'), (-33.8688, 151.2093, 'Australia/Sydney'), (0, 0, 'Etc/UTC')):
            zone = self.zones.get_timezone(tz)
            a = annual_daylight(2026, lat, lon, zone)
            values = [(date(2026, 1, 1) + timedelta(days=i)) for i in range(365)]
            samples = [(d, solar_day_for_local_date(d, lat, lon, zone)) for d in values]
            for extreme, operator in ((a.longest, max), (a.shortest, min)):
                target = operator(s.daylight for d, s in samples)
                self.assertEqual(tuple(s.local_date for s in extreme.days), tuple(d for d, s in samples if s.daylight == target))
                for sample in extreme.days:
                    actual = solar_day_for_local_date(sample.local_date, lat, lon, zone)
                    self.assertEqual(sample.night, actual.next_sunrise_utc - actual.sunset_utc)
            self.assertEqual(a.shortest_night_dates, tuple(d for d, s in samples if s.night == min(v.night for _, v in samples)))

    def test_exact_ties_and_rounding_are_distinct(self):
        samples = tuple(DaylightSample(date(2026, 6, 20) + timedelta(days=i), timedelta(seconds=s), timedelta(hours=10)) for i, s in enumerate((50000, 50000, 49999.5, 49920)))
        e = _daylight_extreme(samples, longest=True)
        self.assertEqual(len(e.days), 2)
        self.assertEqual(len(e.rounded_minute_dates), 3)
        self.assertEqual(e.announcement_date, date(2026, 6, 20))

    def test_announcement_only_exact_first_day(self):
        f = self.facts('2026-06-01T12:00')
        self.assertEqual(f.events_today, ())
        for kind, extreme in (('longestDay', f.annual.longest), ('shortestDay', f.annual.shortest)):
            for day in extreme.rounded_minute_dates:
                moment = datetime.combine(day, datetime.min.time(), tzinfo=self.zones.get_timezone('Asia/Riyadh'))
                value = seasonal_daylight(moment, 24.7136, 46.6753, moment.tzinfo, annual=f.annual)
                self.assertEqual(kind in value.events_today, day == extreme.announcement_date)

    def test_exact_tie_announces_once_and_checks_joint_night_claim(self):
        f = self.facts('2026-06-21T12:00')
        first = f.annual.longest.days[0]
        second = replace(first, local_date=first.local_date + timedelta(days=1))
        tied = replace(f.annual.longest, days=(first, second))
        annual = replace(f.annual, longest=tied, shortest_night_dates=(second.local_date,))
        zone = self.zones.get_timezone('Asia/Riyadh')
        for sample in (first, second):
            value = seasonal_daylight(datetime.combine(sample.local_date, datetime.min.time(), tzinfo=zone), 24.7136, 46.6753, zone, annual=annual)
            self.assertEqual(value.events_today, ('longestDay',) if sample == first else ())
            self.assertFalse(value.combined_day_night_claim_valid)

    def test_extreme_is_not_assumed_to_be_a_solstice(self):
        a = annual_daylight(2026, 0, 0, timezone.utc)
        solstices = {seasonal_event_utc(2026, e).date() for e in (SeasonEvent.JUNE_SOLSTICE, SeasonEvent.DECEMBER_SOLSTICE)}
        self.assertNotIn(a.shortest.days[0].local_date, solstices)
        self.assertEqual(a.shortest.days[0].local_date, date(2026, 3, 20))

    def test_reject_reused_annual_for_different_location_or_year(self):
        f = self.facts('2026-03-15T12:00')
        zone = self.zones.get_timezone('Asia/Riyadh')
        for year, lat in ((2027, 24.7136), (2026, -24.7136)):
            with self.assertRaises(ValueError):
                seasonal_daylight(datetime(year, 3, 15, tzinfo=zone), lat, 46.6753, zone, annual=f.annual)

    def test_polar_unavailable_without_invented_durations(self):
        for lat in (78.2232, -78.2232, 90, -90):
            for month in (6, 12):
                f = self.facts(f'2026-{month:02}-22T12:00', lat, 15.6469, 'Etc/UTC')
                self.assertIsNone(f.current)
                self.assertIsNone(f.change)
                self.assertIsNone(f.annual.longest)
                self.assertIsNone(f.annual.shortest)
                self.assertTrue(f.annual.unavailable_dates)
                self.assertFalse(f.events_today)

    def test_year_boundaries_and_leap_year(self):
        for year in (1901, 2024, 2099):
            for suffix in ('01-01', '12-31'):
                f = self.facts(f'{year}-{suffix}T12:00', 1.8721, -157.4278, 'Pacific/Kiritimati')
                self.assertEqual(f.annual.year, year)
                self.assertIsNotNone(f.change)
                if suffix == '01-01':
                    self.assertEqual(f.reference_local_date.year, year - 1)
        with self.assertRaises(AstronomyRangeError):
            self.facts('2100-01-01T12:00')

    def test_skipped_civil_date_does_not_produce_partial_year_extrema(self):
        zone = self.zones.get_timezone('Pacific/Apia')
        annual = annual_daylight(2011, -13.8333, -171.75, zone)
        self.assertIn(date(2011, 12, 30), annual.unavailable_dates)
        self.assertIsNone(annual.longest)
        self.assertIsNone(annual.shortest)

    def test_dst_elapsed_night_not_wall_clock(self):
        for tz, lat, lon, dates in (
            ('Europe/London', 51.5074, -0.1278, ('2026-03-28', '2026-10-24')),
            ('Australia/Sydney', -33.8688, 151.2093, ('2026-04-04', '2026-10-03')),
        ):
            for text in dates:
                f = self.facts(text + 'T12:00', lat, lon, tz)
                zone = self.zones.get_timezone(tz)
                s = solar_day_for_local_date(f.local_date, lat, lon, zone)
                self.assertEqual(f.current.night, s.next_sunrise_utc - s.sunset_utc)
                wall = s.next_sunrise_utc.astimezone(zone) - s.sunset_utc.astimezone(zone)
                self.assertEqual(abs(wall - f.current.night), timedelta(hours=1))

    def test_service_cache_and_unchanged_existing_read(self):
        clock = EventClock(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)))
        svc = AstronomyService(clock, self.zones)
        location = Location('r', 'Riyadh', 24.7136, 46.6753, 'Asia/Riyadh')
        first = svc.read_daylight(location)
        second = svc.read_daylight(location)
        self.assertIs(first.annual, second.annual)
        self.assertEqual(svc._annual_daylight.cache_info().misses, 1)
        other = svc.read_daylight(Location('s', 'Sydney', -33.8688, 151.2093, 'Australia/Sydney'))
        self.assertIsNot(first.annual, other.annual)
        self.assertEqual(svc.read(location).local_date, first.local_date)

    def test_independent_saved_jpl_durations(self):
        rows = json.loads((ROOT / 'docs/seasonal_daylight_task12/comparisons.json').read_text())
        self.assertGreaterEqual(len(rows), 30)
        for row in rows:
            with self.subTest(site=row['site'], day=row['date']):
                zone = self.zones.get_timezone(row['timezone'])
                s = solar_day_for_local_date(date.fromisoformat(row['date']), row['latitude'], row['longitude'], zone)
                for attr in ('daylight', 'night'):
                    self.assertLessEqual(abs(getattr(s, attr).total_seconds() - row['reference_' + attr + '_seconds']), 120)

    def test_independent_saved_jpl_seasonal_and_extrema(self):
        folder = ROOT / 'docs/seasonal_daylight_task12'
        sites = {r['site']: r for r in json.loads((folder / 'comparisons.json').read_text())}
        annuals = {name: annual_daylight(2026, r['latitude'], r['longitude'], self.zones.get_timezone(r['timezone'])) for name, r in sites.items()}
        for r in json.loads((folder / 'seasonal_comparisons.json').read_text()):
            site = sites[r['site']]
            zone = self.zones.get_timezone(site['timezone'])
            value = seasonal_daylight(datetime.fromisoformat(r['date']).replace(tzinfo=zone), site['latitude'], site['longitude'], zone, annual=annuals[r['site']])
            self.assertEqual(value.reference_local_date.isoformat(), r['reference_date'])
            self.assertLessEqual(abs(value.change.total_seconds() - r['reference_change_seconds']), 240)
        for r in json.loads((folder / 'extrema_comparisons.json').read_text()):
            extreme = getattr(annuals[r['site']], r['kind'])
            self.assertEqual(extreme.days[0].local_date.isoformat(), r['model_date'])
            if r['site'] == 'equator':
                # Nearly flat extrema: report date disagreement, never relabel
                # a sub-second difference as an exact physical tie.
                self.assertLessEqual(r['reference_gap_at_model_date_seconds'], 1)
            else:
                self.assertTrue(r['same_date'], r)
        for r in json.loads((folder / 'polar_comparisons.json').read_text()):
            actual = solar_day_for_local_date(date.fromisoformat(r['date']), r['latitude'], r['longitude'], timezone.utc)
            self.assertEqual(actual.state.value, r['reference_state'])

if __name__ == '__main__':
    unittest.main()
