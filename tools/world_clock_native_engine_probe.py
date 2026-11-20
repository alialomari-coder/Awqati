"""Run the installed NVDA repeat engine outside NVDA; never inject keys or profiles.

Requires CPython 3.13 to read the installed NVDA bytecode. This does not claim
live speech, braille or an NVDA add-on installation test.
"""
import importlib.util
import io
import gettext
import json
import marshal
from pathlib import Path
import sys
from types import CodeType, ModuleType
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'addon/globalPlugins')]


def strings(code):
    for value in code.co_consts:
        if isinstance(value,str):yield value
        elif isinstance(value,CodeType):yield from strings(value)


def audit(archive_path):
    scanned=0;skipped=[];hits=[]
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if not name.endswith('.pyc'):continue
            data=archive.read(name)
            if data[:4]!=importlib.util.MAGIC_NUMBER:
                skipped.append(name);continue
            code=marshal.loads(data[16:]);scanned+=1
            for value in strings(code):
                gesture=value.lower().replace('ctrl','control')
                if gesture.startswith('kb') and ':' in gesture:
                    keys=gesture.split(':',1)[1].split('+')
                    if sorted(keys)==['control','f12','nvda']:hits.append({'module':name,'gesture':value})
    return {'archive':str(archive_path),'modulesScanned':scanned,'unsupportedBytecode':skipped,'gestureMatches':hits}


def main():
    if sys.version_info[:2]!=(3,13):raise RuntimeError('Use CPython 3.13 for the installed NVDA engine')
    from test_stopwatch import GesturesTests
    from test_stopwatch_followup import NativeFollowupDispatchTests
    from test_world_clock_gestures import WorldGestureTests
    suite=unittest.TestSuite((
        GesturesTests('test_installed_native_engine_all_three_counts_and_two_maps'),
        NativeFollowupDispatchTests('test_production_scripts_with_native_engine_no_unintended_operations'),
        WorldGestureTests('test_native_nvda_engine_reaches_production_world_clock_script')))
    # The existing stopwatch fixture reads PO through Babel, which requires a
    # full stdlib zoneinfo installation. NVDA deliberately omits that module.
    # Supply the actual compiled runtime translations at this fixture boundary;
    # retain every assertion and the production script/repeat code unchanged.
    class NativeTranslator:
        def __init__(self,language):
            self.language=language
            self.translate=gettext.translation('nvda',ROOT/'build/awqati/locale',languages=[language],fallback=True).gettext
        def __call__(self,message):return self.translate(message)
    fixture=ModuleType('tests.test_corrective_followup');fixture.Translator=NativeTranslator
    output=io.StringIO()
    with patch.dict(sys.modules,{'tests.test_corrective_followup':fixture}):
        result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    audits=[audit(p) for p in (Path(r'C:\Program Files\NVDA\library.zip'),Path(r'C:\NVDA\library.zip')) if p.exists()]
    report={'python':sys.version,'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skipped':len(result.skipped),'result':output.getvalue(),'defaultGestureAudit':audits,
        'liveKeyInjection':False,'liveNvdaSpeechAndBraille':False,
        'translationFixture':'Production compiled gettext MO replaces the build-time Babel PO reader only; assertions and production scripts unchanged.'}
    path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'docs/world_clock_native_engine.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('result','defaultGestureAudit')},ensure_ascii=True))
    if not result.wasSuccessful() or result.skipped or any(a['gestureMatches'] for a in audits):
        print(output.getvalue());return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
