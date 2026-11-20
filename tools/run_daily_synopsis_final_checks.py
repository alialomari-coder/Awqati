"""Task 3.2 integration/regression checks without builds or reference refetches."""
from pathlib import Path
import argparse
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/daily_synopsis_task32'
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'addon/globalPlugins')]
MODULES = (
    'test_daily_synopsis_final_editorial', 'test_daily_synopsis_integration',
    'test_daily_info_service', 'test_daily_info_formatters',
    'test_daily_window_preferences', 'test_multi_press_execution',
    'test_task51_multipress', 'test_task51_contract', 'test_command_cleanup',
    'test_prayer_calculator', 'test_prayer_state', 'test_alert_scheduler',
    'test_alert_daily_renewal', 'test_calendar_prayer_integration',
    'test_arabian_calendar', 'test_arabian_calendar_failures',
    'test_settings_schema', 'test_settings_repository',
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui-regression', action='store_true')
    args = parser.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    modules = ('test_task52_localization', 'test_daily_window_preferences', 'test_command_cleanup') if args.ui_regression else MODULES
    prefix = 'ui_regression_' if args.ui_regression else ''
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in modules)
    started = time.perf_counter()
    with (OUTPUT/(prefix+'tests.log')).open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    summary = dict(python=sys.version, modules=modules, tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        seconds=time.perf_counter()-started, successful=result.wasSuccessful())
    (OUTPUT/(prefix+'test_summary.json')).write_text(json.dumps(summary, indent=2), 'utf-8')
    print(json.dumps(summary, indent=2))
    if not result.wasSuccessful():
        print((OUTPUT/(prefix+'tests.log')).read_text('utf-8')[-18000:])
    return int(not result.wasSuccessful())

if __name__ == '__main__':
    raise SystemExit(main())
