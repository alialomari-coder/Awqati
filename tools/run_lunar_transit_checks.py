"""Task 2.2 and directly affected tests only; no tasks 1.x/2.1 reference suites."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs/lunar_transit_task22'
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'addon/globalPlugins')]
MODULES=('test_lunar_transit','test_astronomy_service','test_daily_info_service','test_daily_info_formatters')
AFFECTED=(
    'test_rise_and_set_residuals_cross_in_correct_direction',
    'test_offline_service_uses_one_clock_read_and_location_zone',
    'test_meeus_chapter47_worked_example',
    'test_numerical_failure_is_not_reported_as_absence',
)


def main():
    files=('addon/globalPlugins/awqati/domain/lunar_transit.py',
        'addon/globalPlugins/awqati/domain/lunar_horizon.py',
        'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py',
        'tests/test_lunar_transit.py','tools/verify_lunar_transit.py','tools/run_lunar_transit_checks.py')
    for name in files: compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec')
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
    for name in AFFECTED:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName('test_lunar_horizon.LunarHorizonTests.'+name))
    with (OUTPUT/'tests.log').open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    summary=dict(python=sys.version,modules=MODULES,affected_task21_tests=AFFECTED,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        compilation_passed=True,successful=result.wasSuccessful())
    (OUTPUT/'test_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    if not result.wasSuccessful(): print((OUTPUT/'tests.log').read_text(encoding='utf-8'))
    return int(not result.wasSuccessful())


if __name__=='__main__': raise SystemExit(main())
