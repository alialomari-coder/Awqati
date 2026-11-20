"""Task 1.3 focused checks only; no previous reference suites or build."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/sun_distance_task13'
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'addon/globalPlugins')]
MODULES = ('test_sun_distance', 'test_astronomy', 'test_astronomy_service',
    'test_daily_info_service', 'test_daily_info_formatters')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ('addon/globalPlugins/awqati/domain/astronomy.py',
                 'addon/globalPlugins/awqati/domain/__init__.py',
                 'addon/globalPlugins/awqati/application/astronomy_service.py',
                 'addon/globalPlugins/awqati/application/sun_distance_presentation.py',
                 'tests/test_sun_distance.py', 'tools/verify_sun_distance.py',
                 'tools/verify_sun_distance_preservation.py',
                 'tools/run_sun_distance_checks.py'):
        compile((ROOT / name).read_text(encoding='utf-8-sig'), name, 'exec')
    with (OUTPUT / 'tests.log').open('w', encoding='utf-8') as stream:
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    summary = dict(python=sys.version, modules=MODULES, tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        compilation_passed=True, successful=result.wasSuccessful())
    (OUTPUT / 'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
