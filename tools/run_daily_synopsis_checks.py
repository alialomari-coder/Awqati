"""Task 3.1 targeted checks; never build, install or replace a stable package."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/daily_synopsis_task31'
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'addon/globalPlugins')]
MODULES = ('test_daily_synopsis_integration', 'test_daily_info_service',
    'test_daily_info_formatters', 'test_daily_window_preferences',
    'test_astronomy_service', 'test_lunar_horizon_presentation',
    'test_arabian_calendar_formatters', 'test_calendar_prayer_integration',
    'test_prayer_reference_samples', 'test_alert_daily_renewal',
    'test_alert_scheduler', 'test_command_cleanup')
CHANGED_SOURCE = {
    'addon/globalPlugins/awqati/domain/astronomy.py',
    'addon/globalPlugins/awqati/application/astronomy_service.py',
    'addon/globalPlugins/awqati/application/daily_info_service.py',
    'addon/globalPlugins/awqati/application/daily_info_formatters.py',
    'addon/globalPlugins/awqati/application/lunar_horizon_presentation.py',
    'addon/globalPlugins/awqati/application/lunar_phases_presentation.py',
}


def main():
    OUTPUT.mkdir(exist_ok=True)
    for name in (*CHANGED_SOURCE,
                 'addon/globalPlugins/awqati/domain/daily_astronomy.py',
                 'addon/globalPlugins/awqati/application/daily_astronomy_presentation.py',
                 'tests/test_daily_synopsis_integration.py',
                 'tests/test_daily_info_service.py', 'tools/run_daily_synopsis_checks.py'):
        compile((ROOT/name).read_text(encoding='utf-8-sig'), name, 'exec')
    started = time.perf_counter()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
    with (OUTPUT/'tests.log').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    summary = dict(python=sys.version, modules=MODULES, tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        seconds=time.perf_counter()-started, compilation_passed=True, successful=result.wasSuccessful())
    (OUTPUT/'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    if not result.wasSuccessful():
        print((OUTPUT/'tests.log').read_text(encoding='utf-8'))
        return 1

    from awqati.application import (AstronomyService, DailyInfoService, ArabicDailyInfoFormatter,
        EnglishDailyInfoFormatter, ArabianCalendarService)
    from awqati.infrastructure import BundledTimezoneProvider, BundledArabianCalendarRepository
    from awqati.domain import Instant, Location
    from support.event_clock import EventClock
    now = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
    clock, zones = EventClock(Instant(now)), BundledTimezoneProvider()
    location = Location('riyadh', 'Riyadh', 24.7136, 46.6753, 'Asia/Riyadh')
    service = DailyInfoService(AstronomyService(clock, zones),
        ArabianCalendarService(BundledArabianCalendarRepository(), clock, zones))
    for formatter in (ArabicDailyInfoFormatter(), EnglishDailyInfoFormatter()):
        reading = service.read(location, include_arabian_calendar=True)
        text = formatter.format(reading)
        (OUTPUT/f'example_{formatter.language}.txt').write_text(text+'\n', encoding='utf-8')
    measurements = []
    for lat, lon, zone in ((24.7136, 46.6753, 'Asia/Riyadh'),
        (-33.8688, 151.2093, 'Australia/Sydney'),
        (78.2232, 15.6469, 'Arctic/Longyearbyen'), (90, 0, 'Etc/UTC')):
        service = DailyInfoService(AstronomyService(clock, zones))
        place = Location('sample', 'Sample', lat, lon, zone)
        timings = []
        for _ in range(2):
            start = time.perf_counter()
            ArabicDailyInfoFormatter().format(service.read(place))
            timings.append(time.perf_counter()-start)
        measurements.append(dict(latitude=lat, longitude=lon, zone=zone,
            cold_seconds=timings[0], warm_seconds=timings[1]))
    (OUTPUT/'performance.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    before = json.loads((OUTPUT/'source_before.json').read_text(encoding='utf-8'))
    mismatch, checked = [], 0
    for name, expected in before.items():
        if name in CHANGED_SOURCE:
            continue
        checked += 1
        path = ROOT/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mismatch.append(name)
    preservation = dict(checked=checked, intentional_source_changes=sorted(CHANGED_SOURCE),
        mismatches=mismatch, successful=not mismatch,
        stable_package_sha256=hashlib.sha256((ROOT/'dist/awqati-7.0.0.nvda-addon').read_bytes()).hexdigest())
    (OUTPUT/'preservation_result.json').write_text(json.dumps(preservation, indent=2), encoding='utf-8')
    print(json.dumps(preservation, indent=2))
    print(json.dumps(measurements, indent=2))
    return int(bool(mismatch))


if __name__ == '__main__':
    raise SystemExit(main())
