"""Focused task 1.2 gate, per owner request; no task 1.1 reference or build."""
from pathlib import Path
import json
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/seasonal_daylight_task12'
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'addon/globalPlugins')]
MODULES = ('test_seasonal_daylight', 'test_astronomy', 'test_astronomy_service',
    'test_daily_info_service', 'test_daily_info_formatters')

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    for name in ('addon/globalPlugins/awqati/domain/astronomy.py',
        'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py',
        'tests/test_seasonal_daylight.py', 'tools/verify_seasonal_daylight.py',
        'tools/run_seasonal_daylight_checks.py'):
        compile((ROOT / name).read_text(encoding='utf-8-sig'), name, 'exec')
    with (OUTPUT / 'tests.log').open('w', encoding='utf-8') as stream:
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    diff = subprocess.run(['git', 'diff', '--check', '--',
        'addon/globalPlugins/awqati/domain/astronomy.py',
        'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py',
        'docs/data_sources.md', 'ASTRONOMY_ENHANCEMENT_STUDY.md', 'STATUS.md', 'changelog.md'],
        cwd=ROOT, capture_output=True, text=True)
    (OUTPUT / 'whitespace.log').write_text(diff.stdout + diff.stderr, encoding='utf-8')
    summary = dict(python=sys.version, modules=MODULES, tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        seconds=time.perf_counter()-started, compilation_passed=True, whitespace_exit_code=diff.returncode,
        successful=result.wasSuccessful() and diff.returncode == 0)
    (OUTPUT / 'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return int(not summary['successful'])

if __name__ == '__main__':
    raise SystemExit(main())
