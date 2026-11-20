"""Owner-approved prose, dynamic event order and exceptional presentation."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'addon/globalPlugins')]
from test_daily_synopsis_integration import RIYADH, FORMATTERS
from awqati.application import AstronomyService, DailyInfoService
from awqati.domain import Instant, Season, SeasonEvent
from awqati.domain.lunar_horizon import LunarEventState
from awqati.domain.lunar_phases import PrincipalPhase
from awqati.domain.lunar_transit import LunarTransitState, MaximumKind
from awqati.infrastructure import BundledTimezoneProvider
from support.event_clock import EventClock

UTC = timezone.utc


class FinalEditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reading = DailyInfoService(AstronomyService(
            EventClock(Instant(datetime(2026, 11, 19, 9, tzinfo=UTC))),
            BundledTimezoneProvider())).read(RIYADH).scientific

    def texts(self, details=None, **changes):
        r = replace(self.reading, **changes)
        if details:
            r = replace(r, daily_details=replace(r.daily_details, **details))
        return [formatter.format_scientific(r) for formatter in FORMATTERS]

    def test_arabic_matches_owner_reference_ignoring_only_whitespace(self):
        expected = (ROOT/'docs/daily_synopsis_task31/final_editorial/approved_ar.txt').read_text(encoding='utf-8')
        self.assertEqual(self.texts()[0].split(), expected.split())
        self.assertEqual(len(self.texts()[0].splitlines()), 5)

    def test_english_has_equivalent_five_paragraph_structure(self):
        paragraphs = self.texts()[1].splitlines()
        self.assertEqual(len(paragraphs), 5)
        for index, phrase in enumerate(('58th day of autumn', 'has lost a total of',
            'upper meridian transit', 'distance between the centers', 'followed by last quarter')):
            self.assertIn(phrase, paragraphs[index])
        self.assertIn('at 11:39 AM', paragraphs[2])
        self.assertNotIn('noon', paragraphs[2])

    def test_numbers_are_dynamic_and_positive_change_does_not_say_lost(self):
        d = replace(self.reading.daily_details.daylight, change=timedelta(hours=1, minutes=3),
                    reference_season=Season.WINTER)
        ar, en = self.texts(details={'daylight': d}, daylight_change_from_previous_day=timedelta(minutes=2))
        self.assertIn('ما اكتسبه من طوله منذ الانقلاب الشتوي الأخير ساعة واحدة و3 دقائق', ar)
        self.assertNotIn('ما فقده', ar)
        self.assertIn('has gained a total of 1 hour and 3 minutes', en)
        self.assertIn('2 minutes longer', en)

    def test_all_daily_lunar_events_are_sorted_by_actual_instant(self):
        t = self.reading.daily_details.transit
        # The independently calculated maximum can precede meridian transit.
        maximum = replace(t.maxima[0], at_utc=t.transits[0].at_utc-timedelta(minutes=2))
        ar, en = self.texts(details={'transit': replace(t, maxima=(maximum,))})
        a = ar.splitlines()[3]
        e = en.splitlines()[3]
        self.assertLess(a.index('يبلغ أعلى ارتفاع'), a.index('يعبر خط الزوال'))
        self.assertLess(e.index('reaches its greatest altitude'), e.index('makes its upper meridian transit'))
        self.assertNotIn('ثم يبلغ', a)
        self.assertNotIn('then reaches', e)

    def test_simultaneous_transit_and_maximum_do_not_use_then(self):
        t = self.reading.daily_details.transit
        maximum = replace(t.maxima[0], at_utc=t.transits[0].at_utc)
        ar, en = self.texts(details={'transit': replace(t, maxima=(maximum,))})
        self.assertNotIn('ثم يبلغ', ar)
        self.assertNotIn('then reaches', en)
        self.assertIn('ويبلغ أعلى ارتفاع', ar)

    def test_rise_first_and_missing_events_do_not_invent_successions(self):
        h = self.reading.daily_details.horizon
        h = replace(h, rises_utc=(datetime(2026, 11, 19, 1, tzinfo=UTC),),
                    sets_utc=(datetime(2026, 11, 19, 9, tzinfo=UTC),))
        ar, en = self.texts(details={'horizon': h})
        self.assertIn('وهو يشرق اليوم', ar)
        self.assertIn('It rises today', en)
        h = replace(h, rises_utc=(), rise_state=LunarEventState.NO_EVENT)
        t = replace(self.reading.daily_details.transit, transits=(), transit_state=LunarTransitState.NO_EVENT)
        ar, en = self.texts(details={'horizon': h, 'transit': t})
        self.assertIn('لا يشرق القمر', ar)
        self.assertIn('no upper meridian transit today', en)
        self.assertNotIn('ثم يبلغ', ar)
        self.assertNotIn('then reaches', en)

    def test_negative_and_end_boundary_maxima_keep_exception_wording(self):
        t = self.reading.daily_details.transit
        for kind in (MaximumKind.INTERIOR, MaximumKind.DAY_END_LIMIT):
            p = replace(t.maxima[0], altitude_degrees=-16.7, kind=kind)
            ar, en = self.texts(details={'transit': replace(t, maxima=(p,))})
            self.assertIn('تحت الأفق طوال اليوم', ar)
            self.assertNotIn('ثم يبلغ', ar)
            if kind is MaximumKind.DAY_END_LIMIT:
                self.assertIn('ليست قمة داخلية حدثت خلال اليوم', ar)
                self.assertIn('not an interior maximum attained', en)

    def test_phase_order_changes_and_year_rollover_are_dynamic(self):
        phases = self.reading.daily_details.phases
        at = datetime(2026, 12, 31, 20, tzinfo=UTC)
        # Unsorted supplied phases: presentation must sort actual instants.
        events = [replace(event, at_utc=at+timedelta(hours=i*2))
                  for i, event in enumerate(reversed(phases.events))]
        r = replace(phases, events=tuple(reversed(events)))
        ar, en = self.texts(details={'phases': r})
        self.assertIn('وسيبلغ القمر طور التربيع الأول يوم 31 ديسمبر', ar)
        self.assertIn('1 يناير 2027', ar)
        self.assertIn('January 1, 2027', en)
        tail = ar.splitlines()[-1]
        positions = [tail.index(name) for name in ('التربيع الأول', 'المحاق', 'التربيع الأخير', 'البدر')]
        self.assertEqual(positions, sorted(positions))

    def test_simultaneous_phase_instants_use_neutral_link(self):
        phases = self.reading.daily_details.phases
        event = phases.events[0]
        same = replace(phases.events[1], at_utc=event.at_utc)
        ar, en = self.texts(details={'phases': replace(phases, events=(event, same))})
        self.assertNotIn('يليه', ar)
        self.assertNotIn('followed by', en)

    def test_new_moon_first_uses_new_moon_verb_and_keeps_other_data(self):
        phases = self.reading.daily_details.phases
        first = replace(phases.events[0], phase=PrincipalPhase.NEW_MOON)
        ar, en = self.texts(details={'phases': replace(phases, events=(first,))})
        self.assertIn('ويحدث المحاق القادم يوم', ar)
        self.assertIn('The next new moon occurs on', en)
        self.assertIn('147.9', ar)
        self.assertIn('388 thousand', en)


if __name__ == '__main__':
    unittest.main()
