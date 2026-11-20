"""Focused presentation integration, not a repeat of ephemeris reference tests."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'addon/globalPlugins'), str(ROOT/'tests')]
from awqati.application import (AstronomyService, DailyInfoService, ArabianCalendarService,
    ArabicDailyInfoFormatter, EnglishDailyInfoFormatter)
from awqati.application.daily_info_formatters import _synopsis_formats
from awqati.domain import Instant, Location, SolarTransitState
from awqati.domain.lunar_horizon import LunarEventState, LunarHorizonEvents
from awqati.domain.lunar_phases import upcoming_lunar_phases
from awqati.domain.lunar_transit import LunarMaximum, MaximumKind, LunarTransitState
from awqati.infrastructure import BundledTimezoneProvider, BundledArabianCalendarRepository
from support.event_clock import EventClock

UTC = timezone.utc
RIYADH = Location('riyadh', 'Riyadh', 24.7136, 46.6753, 'Asia/Riyadh')
SYDNEY = Location('sydney', 'Sydney', -33.8688, 151.2093, 'Australia/Sydney')
FORMATTERS = (ArabicDailyInfoFormatter(), EnglishDailyInfoFormatter())


class CountingClock(EventClock):
    calls = 0
    def now(self):
        self.calls += 1
        return super().now()


class DailySynopsisIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zones = BundledTimezoneProvider()
        cls.clock = CountingClock(Instant(datetime(2026, 11, 19, 9, tzinfo=UTC)))
        cls.astronomy = AstronomyService(cls.clock, cls.zones)
        cls.base = DailyInfoService(cls.astronomy).read(RIYADH).scientific

    def with_details(self, **changes):
        return replace(self.base, daily_details=replace(self.base.daily_details, **changes))

    def texts(self, reading):
        return [f.format_scientific(reading) for f in FORMATTERS]

    def test_complete_real_reading_and_solar_before_lunar(self):
        ar, en = self.texts(self.base)
        for text, solar, lunar in ((ar, 'تشرق الشمس', 'أما القمر'),
                                   (en, 'The Sun rises', 'The Moon is in')):
            self.assertLess(text.index(solar), text.index(lunar))
            for invalid in ('None', 'nan', 'inf', 'الساعة الساعة'):
                self.assertNotIn(invalid, text)
        self.assertIn('147.9 مليون', ar)
        self.assertIn('الأخير ساعتين و47 دقيقة', ar)
        self.assertIn('388 thousand', en)
        self.assertIn('at 7:28 PM', en)
        self.assertIn('at 7:30 PM', en)
        self.assertNotIn('ظاهر', ar)

    def test_single_clock_and_bounded_daily_cache_invalidation(self):
        clock = CountingClock(Instant(datetime(2026, 11, 19, 9, tzinfo=UTC)))
        service = AstronomyService(clock, self.zones)
        a = DailyInfoService(service).read(RIYADH).scientific
        clock.set(Instant(datetime(2026, 11, 19, 12, tzinfo=UTC)))
        b = DailyInfoService(service).read(RIYADH).scientific
        self.assertEqual(clock.calls, 2)
        self.assertIs(a.daily_details.horizon, b.daily_details.horizon)
        self.assertIs(a.daily_details.transit, b.daily_details.transit)
        self.assertNotEqual(a.daily_details.lunar_distance, b.daily_details.lunar_distance)
        self.assertEqual(service._annual_daylight.cache_info().misses, 1)
        clock.set(Instant(datetime(2026, 11, 20, 9, tzinfo=UTC)))
        c = DailyInfoService(service).read(RIYADH).scientific
        self.assertIsNot(b.daily_details.horizon, c.daily_details.horizon)
        DailyInfoService(service).read(SYDNEY)
        self.assertEqual(service._annual_daylight.cache_info().misses, 2)
        self.assertEqual(service._daily_horizon.cache_info().maxsize, 8)

    def test_signed_change_in_both_hemispheres(self):
        for location, expected in ((RIYADH, -1), (SYDNEY, 1)):
            r = AstronomyService(EventClock(Instant(datetime(2026, 11, 19, 9, tzinfo=UTC))), self.zones).read(location, include_daily_details=True)
            self.assertEqual(1 if r.daily_details.daylight.change > timedelta(0) else -1, expected)
            ar, en = self.texts(r)
            self.assertIn('ما اكتسبه من طوله' if expected > 0 else 'ما فقده من طوله', ar)
            self.assertIn('has gained' if expected > 0 else 'has lost', en)

    def test_actual_extreme_dates_and_separate_night_date(self):
        annual = self.base.daily_details.daylight.annual
        days = {annual.longest.announcement_date, annual.shortest.announcement_date,
                *annual.longest_night_dates, *annual.shortest_night_dates}
        for day in days:
            self.clock.set(Instant(datetime(day.year, day.month, day.day, 9, tzinfo=UTC)))
            r = DailyInfoService(self.astronomy).read(RIYADH).scientific
            ar, en = self.texts(r)
            for label, occurs in (
                ('the longest day', day == annual.longest.announcement_date),
                ('the shortest day', day == annual.shortest.announcement_date),
                ('the longest night', day in annual.longest_night_dates),
                ('the shortest night', day in annual.shortest_night_dates)):
                self.assertEqual(label in en, occurs, (day, label))
        self.assertNotIn('of the year', self.texts(self.base)[1])
        self.assertNotEqual(annual.longest.announcement_date, annual.shortest_night_dates[0])

    def test_rise_set_order_absence_and_errors(self):
        def at(h): return datetime(2026, 11, 19, h, tzinfo=UTC)
        for rises, sets in (((at(6),), (at(19),)), ((at(19),), (at(6),)),
                            ((at(6),), ()), ((), (at(19),)), ((), ())):
            horizon = LunarHorizonEvents(self.base.local_date, UTC, rises, sets,
                LunarEventState.AVAILABLE if rises else LunarEventState.NO_EVENT,
                LunarEventState.AVAILABLE if sets else LunarEventState.NO_EVENT)
            ar, en = self.texts(self.with_details(horizon=horizon))
            if rises and sets:
                self.assertIn('It rises today' if rises[0] < sets[0] else 'It sets today', en)
            if not rises: self.assertIn('لا يشرق القمر', ar)
            if not sets: self.assertIn('does not set today', en)
        horizon = replace(horizon, rise_state=LunarEventState.CALCULATION_ERROR,
                          set_state=LunarEventState.CALCULATION_ERROR)
        ar, en = self.texts(self.with_details(horizon=horizon))
        self.assertIn('تعذر حساب شروق القمر', ar)
        self.assertNotIn('does not rise', en)

    def test_missing_transit_is_not_a_maximum_or_midnight(self):
        for state in (LunarTransitState.NO_EVENT, LunarTransitState.UNDEFINED_MERIDIAN,
                      LunarTransitState.CALCULATION_ERROR):
            t = replace(self.base.daily_details.transit, transits=(), transit_state=state)
            ar, en = self.texts(self.with_details(transit=t))
            self.assertNotIn('upper meridian transit is at 7:28', en)
            self.assertIn('greatest altitude', en)
            self.assertNotIn('12:00 AM', en)

    def test_negative_and_boundary_maxima_never_claim_visibility(self):
        for kind in MaximumKind:
            t = self.base.daily_details.transit
            p = LunarMaximum(datetime(2026, 11, 19, 21, tzinfo=UTC), -16.7, kind)
            t = replace(t, maxima=(p,))
            ar, en = self.texts(self.with_details(transit=t))
            self.assertIn('below the horizon throughout', en)
            self.assertIn('-16.7', en)
            self.assertNotIn('visible', en)
            if kind is MaximumKind.DAY_END_LIMIT:
                self.assertIn('not an interior maximum attained', en)
                self.assertNotIn('reaches its greatest altitude today at', en)
            elif kind is MaximumKind.DAY_START:
                self.assertIn('occurs at its start', en)
            else:
                self.assertIn('greatest geometric altitude is at', en)

    def test_real_polar_day_night_and_geographic_pole(self):
        for latitude, month in ((78.2232, 6), (78.2232, 12), (90, 6), (-90, 6)):
            location = Location('polar', 'Polar', latitude, 15.6, 'Arctic/Longyearbyen')
            service = AstronomyService(EventClock(Instant(datetime(2026, month, 21, 9, tzinfo=UTC))), self.zones)
            r = DailyInfoService(service).read(location).scientific
            ar, en = self.texts(r)
            self.assertIn('polar', en)
            self.assertNotIn('Sunrise is at', en)
            self.assertNotIn('the longest day', en)
            if abs(latitude) == 90:
                self.assertIn('undefined at the geographic pole', en)

    def test_all_optional_failures_keep_rest_of_synopsis(self):
        service = AstronomyService(EventClock(Instant(datetime(2026, 11, 19, 9, tzinfo=UTC))), self.zones)
        with patch('awqati.application.astronomy_service.sun_distance', side_effect=ArithmeticError), \
             patch('awqati.application.astronomy_service.lunar_distance', side_effect=ArithmeticError), \
             patch('awqati.application.astronomy_service.upcoming_lunar_phases', side_effect=ValueError), \
             patch.object(service, '_annual_daylight', side_effect=ArithmeticError), \
             patch.object(service, '_daily_horizon', side_effect=ArithmeticError), \
             patch.object(service, '_daily_transit', side_effect=ArithmeticError):
            r = DailyInfoService(service).read(RIYADH).scientific
        for text in self.texts(r):
            self.assertNotIn('None', text)
            self.assertNotIn('0 million', text)
        self.assertIn('could not be calculated', self.texts(r)[1])
        self.assertIn('أما القمر، فهو في طور', self.texts(r)[0])

    def test_nonfinite_values_are_not_spoken(self):
        facts = self.base.daily_details
        r = self.with_details(sun_distance=replace(facts.sun_distance, distance_km=float('nan')),
            lunar_distance=replace(facts.lunar_distance, distance_km=float('inf')))
        for text in self.texts(r):
            self.assertNotIn('nan', text)
            self.assertNotIn('inf', text)
        self.assertIn('solar distance could not', self.texts(r)[1])

    def test_unavailable_solar_transit_and_failed_maximum(self):
        r = replace(self.base, solar_day=replace(self.base.solar_day,
            transit_state=SolarTransitState.NO_TRANSIT, transit_utc=None, transit_altitude_degrees=None))
        for text in self.texts(r):
            self.assertNotIn('None', text)
        self.assertIn('No definite upper meridian transit', self.texts(r)[1])
        t = replace(self.base.daily_details.transit, maximum_state=LunarEventState.CALCULATION_ERROR)
        self.assertIn('No greatest lunar altitude is available', self.texts(self.with_details(transit=t))[1])
        self.assertNotIn('reaches its greatest altitude today', self.texts(self.with_details(transit=t))[1])

    def test_multiple_fold_events_keep_order_and_offsets_once(self):
        zone = self.zones.get_timezone('Europe/London')
        a = datetime(2026, 10, 25, 0, 45, tzinfo=UTC)
        b = datetime(2026, 10, 25, 1, 15, tzinfo=UTC)
        horizon = LunarHorizonEvents(date(2026, 10, 25), zone, (a, b), (),
            LunarEventState.MULTIPLE, LunarEventState.NO_EVENT)
        for text in self.texts(self.with_details(horizon=horizon)):
            self.assertLess(text.index('UTC+0100'), text.index('UTC+0000'))
            self.assertEqual(text.count('UTC+0100'), 1)
            self.assertEqual(text.count('UTC+0000'), 1)

    def test_phases_single_new_source_legacy_timestamps_ignored(self):
        sentinel = datetime(2026, 2, 2, tzinfo=UTC)
        r = replace(self.base, next_new_moon_local=sentinel, next_full_moon_local=sentinel)
        ar, en = self.texts(r)
        self.assertNotIn('February', en)
        self.assertEqual(en.splitlines()[-1].count('new moon'), 1)
        self.assertEqual(en.splitlines()[-1].count('full moon'), 1)
        self.assertEqual(en.splitlines()[-1].count('first quarter'), 1)
        self.assertEqual(en.splitlines()[-1].count('last quarter'), 1)
        events = r.daily_details.phases.events
        self.assertEqual(len(events), 4)

    def test_real_phase_near_local_day_boundary_and_exact_event(self):
        zone = self.zones.get_timezone('Pacific/Kiritimati')
        phases = upcoming_lunar_phases(datetime(2026, 1, 1, tzinfo=UTC), zone)
        self.assertEqual(phases.next_local.date(), date(2026, 1, 4))
        ar, en = self.texts(self.with_details(phases=phases))
        self.assertIn('January 4 at 12:03 AM', en)
        self.assertIn('4 يناير', ar)
        nexts = upcoming_lunar_phases(phases.next_event.at_utc, zone)
        self.assertNotEqual(nexts.next_event, phases.next_event)
        self.assertNotIn('January 4', self.texts(self.with_details(phases=nexts))[1])

    def test_date_and_clock_round_together_at_midnight_and_dst(self):
        for lang in ('ar', 'en'):
            clock, day = _synopsis_formats(lang)
            at = datetime(2026, 12, 31, 23, 59, 45, tzinfo=UTC)
            self.assertIn('2027', day(at))
            self.assertIn('2027', clock(at))
            zone = self.zones.get_timezone('Europe/London')
            a = datetime(2026, 10, 25, 0, 45, tzinfo=UTC).astimezone(zone)
            b = datetime(2026, 10, 25, 1, 15, tzinfo=UTC).astimezone(zone)
            self.assertIn('UTC+0100', clock(a))
            self.assertIn('UTC+0000', clock(b))

    def test_modeled_ut_warning_and_exhausted_range(self):
        for year in (1950, 2050):
            phases = upcoming_lunar_phases(datetime(year, 1, 1, tzinfo=UTC))
            ar, en = self.texts(self.with_details(phases=phases))
            self.assertIn('ΔT', ar)
            self.assertIn('do not represent confirmed UTC', en)
        phases = upcoming_lunar_phases(datetime(2099, 12, 31, 23, 59, tzinfo=UTC))
        self.assertFalse(phases.events)
        self.assertIn('No upcoming lunar phase', self.texts(self.with_details(phases=phases))[1])

    def test_local_year_range_does_not_leak_instant_calculations(self):
        r = AstronomyService(EventClock(Instant(datetime(1900, 12, 31, 21, tzinfo=UTC))), self.zones).read(RIYADH, include_daily_details=True)
        self.assertIsNone(r.daily_details.phases)
        self.assertIsNone(r.daily_details.lunar_distance)
        self.assertIn('within the supported range', self.texts(r)[1])

    def test_heritage_unchanged_in_both_languages_and_independent(self):
        clock = EventClock(Instant(datetime(2026, 11, 19, 9, tzinfo=UTC)))
        heritage = ArabianCalendarService(BundledArabianCalendarRepository(), clock, self.zones)
        service = DailyInfoService(AstronomyService(clock, self.zones), heritage)
        without = service.read(RIYADH)
        with_heritage = service.read(RIYADH, include_arabian_calendar=True)
        for formatter in FORMATTERS:
            expected = formatter._arabian_calendar.format_combined(with_heritage.heritage)
            self.assertEqual(formatter.format(with_heritage), formatter.format(without) + '\n\n' + expected)


if __name__ == '__main__':
    unittest.main()
