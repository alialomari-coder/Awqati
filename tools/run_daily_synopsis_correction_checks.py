"""Targeted task 3.1 follow-up; no package build or reference-suite rerun."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/daily_synopsis_task31/correction'
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'addon/globalPlugins')]
MODULES = ('test_daily_synopsis_correction', 'test_daily_synopsis_integration',
    'test_daily_info_formatters',
    'test_astronomy.LunarAstronomyTests.test_primary_angles_and_intermediate_intervals_are_deterministic',
    'test_lunar_phases.LunarPhasesTests.test_arabic_english_all_phase_names_and_local_callbacks')
CHANGED = {
    'addon/globalPlugins/awqati/domain/astronomy.py',
    'addon/globalPlugins/awqati/application/daily_astronomy_presentation.py',
    'addon/globalPlugins/awqati/application/daily_info_formatters.py',
    'addon/globalPlugins/awqati/application/lunar_phases_presentation.py',
}


def main():
    for name in (*CHANGED, 'tests/test_daily_synopsis_correction.py',
        'tests/test_daily_synopsis_integration.py', 'tests/test_daily_info_formatters.py',
        'tests/test_astronomy.py', 'tools/run_daily_synopsis_correction_checks.py'):
        compile((ROOT/name).read_text(encoding='utf-8-sig'), name, 'exec')
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
    start = time.perf_counter()
    with (OUTPUT/'tests.log').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    summary = dict(python=sys.version, tests=result.testsRun, modules=MODULES,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        seconds=time.perf_counter()-start, compilation_passed=True, successful=result.wasSuccessful())
    (OUTPUT/'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if not result.wasSuccessful():
        print((OUTPUT/'tests.log').read_text(encoding='utf-8'))
        return 1

    from awqati.application import (AstronomyService, DailyInfoService, ArabianCalendarService,
        ArabicDailyInfoFormatter, EnglishDailyInfoFormatter)
    from awqati.infrastructure import BundledTimezoneProvider, BundledArabianCalendarRepository
    from awqati.domain import Instant, Location
    from support.event_clock import EventClock
    at = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
    clock, zones = EventClock(Instant(at)), BundledTimezoneProvider()
    location = Location('riyadh', 'Riyadh', 24.7136, 46.6753, 'Asia/Riyadh')
    service = DailyInfoService(AstronomyService(clock, zones),
        ArabianCalendarService(BundledArabianCalendarRepository(), clock, zones))
    reading = service.read(location, include_arabian_calendar=True)
    heritage = {}
    for formatter in (ArabicDailyInfoFormatter(), EnglishDailyInfoFormatter()):
        lang = formatter.language
        text = formatter.format(reading)
        old = (OUTPUT/f'example_before_{lang}.txt').read_text(encoding='utf-8')
        heritage[lang] = old.split('\n\n', 1)[1] == (text+'\n').split('\n\n', 1)[1]
        for folder in (OUTPUT, OUTPUT.parent):
            (folder/f'example_{lang}.txt').write_text(text+'\n', encoding='utf-8')
        (OUTPUT/f'scientific_{lang}.txt').write_text(formatter.format_scientific(reading.scientific)+'\n', encoding='utf-8')
    lunar = reading.scientific.lunar
    diagnosis = dict(observed_at_utc=at.isoformat(), old_phase='firstQuarter',
        old_primary_sector_degrees=[67.5, 112.5], new_phase=lunar.phase.value,
        elongation_degrees=lunar.elongation_degrees, age_days=lunar.age_days,
        illumination_fraction=lunar.illumination_fraction,
        cause='nearest 45-degree sector incorrectly used an instantaneous primary-phase name',
        source='https://aa.usno.navy.mil/faq/moon_phases')
    (OUTPUT/'diagnosis.json').write_text(json.dumps(diagnosis, indent=2), encoding='utf-8')
    before = json.loads((OUTPUT/'source_before.json').read_text(encoding='utf-8'))
    mismatches = [name for name, digest in before.items() if name not in CHANGED
        and (not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest)]
    preservation = dict(checked=len(before)-len(CHANGED), excluded_source_changes=sorted(CHANGED),
        mismatches=mismatches, heritage_examples_unchanged=heritage,
        stable_package_sha256=hashlib.sha256((ROOT/'dist/awqati-7.0.0.nvda-addon').read_bytes()).hexdigest(),
        successful=not mismatches and all(heritage.values()))
    (OUTPUT/'preservation_result.json').write_text(json.dumps(preservation, indent=2), encoding='utf-8')
    print(json.dumps(preservation, indent=2))
    return int(not preservation['successful'])


if __name__ == '__main__':
    raise SystemExit(main())
