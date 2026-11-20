"""Focused classification and editorial checks for the task 3.1 follow-up."""
from dataclasses import replace, fields
import ast
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'addon/globalPlugins')]
from test_daily_synopsis_integration import RIYADH, FORMATTERS
from awqati.application import AstronomyService, DailyInfoService
from awqati.domain import Instant, MoonPhase
from awqati.domain.astronomy import classify_moon_phase, lunar_facts
from awqati.infrastructure import BundledTimezoneProvider
from support.event_clock import EventClock

UTC = timezone.utc


class DailySynopsisCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instant = datetime(2026, 11, 19, 9, tzinfo=UTC)
        cls.reading = DailyInfoService(AstronomyService(EventClock(Instant(cls.instant)),
            BundledTimezoneProvider())).read(RIYADH).scientific

    def test_regression_is_fixed_in_calculation_before_formatting(self):
        facts = lunar_facts(self.instant)
        self.assertEqual(facts.phase, MoonPhase.WAXING_GIBBOUS)
        self.assertAlmostEqual(facts.elongation_degrees, 111.66613734582504, places=9)
        self.assertAlmostEqual(facts.age_days, 10.0819976015625, places=9)
        self.assertEqual(round(facts.illumination_fraction*100, 1), 68.6)
        ar, en = [f.format_scientific(self.reading) for f in FORMATTERS]
        self.assertIn('أما القمر، فهو في طور الأحدب المتزايد', ar)
        self.assertIn('waxing gibbous phase', en)

    def test_old_primary_sectors_are_now_intermediate_phases(self):
        for angles, expected in (
            ((.01, 22.5, 67.5, 89.99), MoonPhase.WAXING_CRESCENT),
            ((90.01, 111.666, 112.5, 157.5, 179.99), MoonPhase.WAXING_GIBBOUS),
            ((180.01, 202.5, 247.5, 269.99), MoonPhase.WANING_GIBBOUS),
            ((270.01, 292.5, 337.5, 359.99), MoonPhase.WANING_CRESCENT),
        ):
            for angle in angles:
                self.assertEqual(classify_moon_phase(angle), expected)

    def test_cardinal_angles_wrap_and_nonfinite_inputs(self):
        for angle, phase in ((0, MoonPhase.NEW_MOON), (90, MoonPhase.FIRST_QUARTER),
            (180, MoonPhase.FULL_MOON), (270, MoonPhase.LAST_QUARTER)):
            for turns in (-2, -1, 0, 1, 2):
                self.assertEqual(classify_moon_phase(angle+360*turns), phase)
        for value in (math.inf, -math.inf, math.nan):
            with self.assertRaises(ValueError):
                classify_moon_phase(value)

    def test_classification_uses_longitude_not_rounded_illumination_or_age(self):
        # The primary definition is 90 degrees, not a rounded 50% label,
        # fixed age, or a finite window around the event.
        with patch('awqati.domain.astronomy._lunar_elongation', return_value=(90., 0., 0.)):
            facts = lunar_facts(self.instant)
        self.assertEqual(facts.phase, MoonPhase.FIRST_QUARTER)
        self.assertGreater(facts.illumination_fraction, .5)
        self.assertGreater(facts.age_days, 10)

    def test_other_numeric_lunar_facts_are_preserved_against_saved_source(self):
        path = ROOT/'docs/daily_synopsis_task31/correction/before_astronomy.py'
        spec = importlib.util.spec_from_file_location('_awqati_task31_before', path)
        old = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = old
        spec.loader.exec_module(old)
        for month, day in ((1, 1), (3, 20), (6, 21), (9, 13), (11, 19), (12, 31)):
            at = datetime(2026, month, day, 9, tzinfo=UTC)
            before, after = old.lunar_facts(at), lunar_facts(at)
            for field in fields(after):
                if field.name != 'phase':
                    self.assertEqual(getattr(before, field.name), getattr(after, field.name))

    def test_astronomy_calculations_outside_classifier_are_unchanged(self):
        def retained_ast(path):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            tree.body = [node for node in tree.body
                if not (isinstance(node, ast.FunctionDef) and node.name == 'classify_moon_phase')
                and not (isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == '_PHASES' for target in node.targets))]
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(retained_ast(ROOT/'docs/daily_synopsis_task31/correction/before_astronomy.py'),
            retained_ast(ROOT/'addon/globalPlugins/awqati/domain/astronomy.py'))

    def test_daylight_comparison_stays_in_day_length_paragraph(self):
        for f, length, reference, transit in (
            (FORMATTERS[0], 'طول النهار اليوم', 'منذ الانقلاب الصيفي', 'تشرق الشمس'),
            (FORMATTERS[1], 'Daylight lasts', 'since the last summer solstice', 'The Sun rises'),
        ):
            paragraphs = f.format_scientific(self.reading).splitlines()
            p = next(p for p in paragraphs if length in p)
            self.assertIn(reference, p)
            self.assertNotIn(transit, p)
            self.assertLess('\n'.join(paragraphs).index(reference), '\n'.join(paragraphs).index(transit))

    def test_solar_transit_keeps_civil_am_pm(self):
        for hour, ar_period, en_period in ((8, 'صباحًا', 'AM'), (9, 'مساءً', 'PM')):
            solar = replace(self.reading.solar_day, transit_utc=datetime(2026, 11, 19, hour, 39, tzinfo=UTC))
            reading = replace(self.reading, solar_day=solar)
            ar, en = [f.format_scientific(reading) for f in FORMATTERS]
            a = next(p for p in ar.splitlines() if 'تشرق الشمس' in p)
            e = next(p for p in en.splitlines() if 'The Sun rises' in p)
            hour_text = '11' if hour == 8 else '12'
            self.assertIn(f'وتعبر خط الزوال عند الساعة {hour_text} و39 دقيقة {ar_period}', a)
            self.assertIn(f'upper meridian transit is at {hour_text}:39 {en_period}', e)
            self.assertNotIn('ظهرًا', a)

    def test_punctuation_and_unforced_transitions(self):
        for formatter in FORMATTERS:
            text = formatter.format_scientific(self.reading)
            for unwanted in ('..', '؛.', '،.', 'And Earth', 'And it', 'And the Moon', 'إذ سيدخل'):
                self.assertNotIn(unwanted, text)


if __name__ == '__main__':
    unittest.main()
