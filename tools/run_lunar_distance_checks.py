"""Only task 2.3 and directly affected service tests; offline reference replay."""
from pathlib import Path
import hashlib
import json
import runpy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/lunar_distance_task23'
sys.path[:0] = [str(ROOT/'tests'),str(ROOT/'addon/globalPlugins')]


def main():
    runpy.run_path(str(ROOT/'tools/verify_lunar_distance.py'),run_name='__main__')
    files = ('addon/globalPlugins/awqati/domain/lunar_distance.py',
        'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py',
        'addon/globalPlugins/awqati/application/lunar_distance_presentation.py',
        'tests/test_lunar_distance.py','tools/verify_lunar_distance.py','tools/run_lunar_distance_checks.py')
    for name in files:
        compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec')
    modules = ('test_lunar_distance','test_astronomy_service')
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in modules)
    with (OUTPUT/'tests.log').open('w',encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    before = json.loads((OUTPUT/'preservation_before.json').read_text(encoding='utf-8'))
    allowed = {'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py'}
    changed = [name for name,digest in before.items()
        if name not in allowed and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    (OUTPUT/'preservation_result.json').write_text(json.dumps(dict(
        checked=len(before)-len(allowed), allowed_changes=sorted(allowed),
        unexpected_changes=changed, successful=not changed),indent=2),encoding='utf-8')
    summary = dict(python=sys.version,modules=modules,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        compilation_passed=True,preservation_passed=not changed,successful=result.wasSuccessful() and not changed)
    (OUTPUT/'test_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    if not result.wasSuccessful():
        print((OUTPUT/'tests.log').read_text(encoding='utf-8'))
    return int(not summary['successful'])


if __name__ == '__main__':
    raise SystemExit(main())
