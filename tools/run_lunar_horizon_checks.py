"""Task 2.1 only; exclude reference suites for tasks 1.1, 1.2 and 1.3."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/lunar_horizon_task21'
sys.path[:0] = [str(ROOT/'tests'),str(ROOT/'addon/globalPlugins')]
MODULES = ('test_lunar_horizon','test_astronomy_service',
           'test_daily_info_service','test_daily_info_formatters')


def main():
    files = ['addon/globalPlugins/awqati/domain/_lunar_terms.py',
        'addon/globalPlugins/awqati/domain/lunar_horizon.py',
        'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py',
        'addon/globalPlugins/awqati/application/lunar_horizon_presentation.py',
        'tests/test_lunar_horizon.py','tools/verify_lunar_horizon.py',
        'tools/run_lunar_horizon_checks.py']
    for name in files:
        compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec')
    with (OUTPUT/'tests.log').open('w',encoding='utf-8') as stream:
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in MODULES)
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    summary=dict(python=sys.version,modules=MODULES,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        compilation_passed=True,successful=result.wasSuccessful())
    (OUTPUT/'test_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return int(not result.wasSuccessful())


if __name__=='__main__': raise SystemExit(main())
