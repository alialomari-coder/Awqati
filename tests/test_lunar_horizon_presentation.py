"""Text-only checks with supplied instants; no astronomical calculations."""
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addon/globalPlugins'))
from awqati.domain.lunar_horizon import LunarHorizonEvents, LunarEventState as State
from awqati.application.lunar_horizon_presentation import format_lunar_horizon
from awqati.infrastructure import BundledTimezoneProvider


class LunarHorizonPresentationTests(unittest.TestCase):
    def events(self, rises=(), sets=(), zone=timezone.utc, error=False):
        def state(values):
            return State.CALCULATION_ERROR if error else State.MULTIPLE if len(values)>1 else State.AVAILABLE if values else State.NO_EVENT
        return LunarHorizonEvents(date(2026,10,25),zone,rises,sets,state(rises),state(sets))

    def at(self, hour, minute=0):
        return datetime(2026,10,25,hour,minute,tzinfo=timezone.utc)

    def text(self, events, language):
        return format_lunar_horizon(events,language,lambda t:t.strftime('%H:%M'))

    def test_set_before_rise_names_moon_first_in_both_languages(self):
        r=self.events((self.at(13,8),),(self.at(0,30),))
        self.assertEqual(self.text(r,'ar'),'يغرب القمر اليوم عند الساعة 00:30، ويشرق عند الساعة 13:08.')
        self.assertEqual(self.text(r,'en'),'The Moon sets today at 00:30, and rises at 13:08.')

    def test_rise_before_set_names_moon_first_in_both_languages(self):
        r=self.events((self.at(6),),(self.at(19),))
        self.assertEqual(self.text(r,'ar'),'يشرق القمر اليوم عند الساعة 06:00، ويغرب عند الساعة 19:00.')
        self.assertEqual(self.text(r,'en'),'The Moon rises today at 06:00, and sets at 19:00.')

    def test_single_event_missing_events_and_errors_name_moon(self):
        for rises,sets in [((self.at(6),),()),((),(self.at(19),)),((),())]:
            for language in ('ar','en'):
                text=self.text(self.events(rises,sets),language)
                self.assertIn('القمر' if language=='ar' else 'Moon',text)
                self.assertNotIn('None',text)
                if not rises: self.assertIn('لا يشرق القمر' if language=='ar' else 'The Moon does not rise',text)
                if not sets: self.assertIn('لا يغرب القمر' if language=='ar' else 'The Moon does not set',text)
        self.assertEqual(self.text(self.events(error=True),'ar'),'تعذر حساب شروق القمر اليوم، وتعذر حساب غروب القمر اليوم.')
        self.assertEqual(self.text(self.events(error=True),'en'),'Moonrise could not be calculated today, and Moonset could not be calculated today.')

    def test_multiple_events_are_interleaved_in_time_order(self):
        r=self.events((self.at(20),self.at(6)),(self.at(23),self.at(1)))
        for language in ('ar','en'):
            text=self.text(r,language)
            positions=[text.index(time) for time in ('01:00','06:00','20:00','23:00')]
            self.assertEqual(positions,sorted(positions))
            self.assertEqual(text.count('UTC+0000'),4)
            self.assertTrue(text.startswith('يغرب القمر' if language=='ar' else 'The Moon sets'))

    def test_fold_order_uses_absolute_instants_not_wall_clock(self):
        zone=BundledTimezoneProvider().get_timezone('Europe/London')
        r=self.events((self.at(0,45),self.at(1,15)),(),zone)
        for language in ('ar','en'):
            text=self.text(r,language)
            self.assertLess(text.index('01:45 (UTC+0100)'),text.index('01:15 (UTC+0000)'))


if __name__=='__main__': unittest.main()
