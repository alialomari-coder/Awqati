"""Task 2.4 only and its directly affected service tests; fully offline."""
from pathlib import Path
import hashlib
import json
import runpy
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/lunar_phases_task24'
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'addon/globalPlugins')]


def main():
    sys.argv=[str(ROOT/'tools/verify_lunar_phases.py'),'--diagnostic']
    runpy.run_path(sys.argv[0],run_name='__main__')
    sys.argv=[str(ROOT/'tools/verify_lunar_phases_jpl.py')]
    runpy.run_path(sys.argv[0],run_name='__main__')
    runpy.run_path(str(ROOT/'tools/describe_lunar_phases_evidence.py'),run_name='__main__')
    sources=(
        'addon/globalPlugins/awqati/domain/astronomy.py',
        'addon/globalPlugins/awqati/domain/lunar_phases.py',
        'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py',
        'addon/globalPlugins/awqati/application/lunar_phases_presentation.py',
        'tools/verify_lunar_phases.py','tools/verify_lunar_phases_jpl.py',
        'tools/run_lunar_phases_checks.py','tests/test_lunar_phases.py',
        'tools/describe_lunar_phases_evidence.py')
    for name in sources:
        compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec')
    modules=('test_lunar_phases','test_astronomy_service')
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in modules)
    with (OUT/'tests.log').open('w',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    before=json.loads((OUT/'preservation_before.json').read_text(encoding='utf-8'))
    allowed={sources[0],sources[2],sources[3]}
    changed=[name for name,digest in before.items() if name not in allowed
             and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    preservation=dict(checked=len(before)-len(allowed),allowed_changes=sorted(allowed),
                      unexpected_changes=changed,successful=not changed)
    (OUT/'preservation_result.json').write_text(json.dumps(preservation,indent=2),encoding='utf-8')
    summary=dict(python=sys.version,modules=modules,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        compilation_passed=True,preservation_passed=not changed,
        primary_reference='96 JPL TT roots within 90 seconds',
        usno_diagnostic='295; original 120-second margin failed at 2099; see report',
        successful=result.wasSuccessful() and not changed)
    (OUT/'test_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    if not result.wasSuccessful():
        print((OUT/'tests.log').read_text(encoding='utf-8'))
    return int(not summary['successful'])


if __name__=='__main__':
    raise SystemExit(main())
