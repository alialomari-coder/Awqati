"""Read-only historical dev16 audit (plugin pinned to f141e9a). Writes docs/multi_press_evidence.json only.

Uses pinned official archives already present in development_baseline. Extracts
actual function ASTs into isolated namespaces; never imports live NVDA, sends
keys, accesses user settings, or changes add-on behavior. No sleep in timings.
"""
import ast
import hashlib
import json
import statistics
import sys
import tarfile
import time
import weakref
import wave
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'addon/globalPlugins/awqati/nvda_adapter'
sys.path.insert(0, str(ROOT / 'addon'))
from globalPlugins.awqati.nvda_adapter import compat
sys.path.insert(0, str(ROOT / 'tests'))
from legacy_stopwatch_gestures import StopwatchGestures
import subprocess
HISTORICAL_PLUGIN = subprocess.check_output(['git', 'show', 'f141e9a:addon/globalPlugins/awqati/nvda_adapter/plugin.py'], cwd=ROOT).decode('utf8')


def functions(source, names, namespace):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(nodes) != len(names):
        raise AssertionError(names)
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<audited actual source>', 'exec'), namespace)
    return namespace


def timing(callback, n=500):
    samples = []
    for _ in range(n):
        start = time.perf_counter_ns()
        callback()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return {'iterations': n, 'median_ms': statistics.median(samples),
            'p95_ms': sorted(samples)[int(n * .95)], 'max_ms': max(samples)}


def normal(value):
    if not value.lower().startswith('kb') or ':' not in value:
        return None
    return frozenset(t.replace('ctrl', 'control') for t in value.lower().split(':', 1)[1].split('+'))


def run():
    result = {'schema': 1, 'date': '2026-11-03', 'python': sys.version,
              'clock': vars(time.get_clock_info('perf_counter')),
              'limits': 'Isolated actual AST/functions with fake clock/queue/output. No live key-hook, synth or audible latency measured.',
              'sources': [], 'checks': [], 'traces': {}, 'timings': {}}
    prior_path=ROOT/'docs/time_tools_shortcut_audit.json'
    if prior_path.exists():
        prior=json.loads(prior_path.read_text('utf-8'))
        result['priorLayoutEvidence']={'date':prior['date'],
            'sha256':hashlib.sha256(prior_path.read_bytes()).hexdigest(),
            'scope':'Snapshot of existing evidence; no new live layout or input test.',
            'layouts':prior['layouts'],
            'backslashShiftNaming':[{'version':v['version'],'probes':[
                p for p in v['actualNamingMethodsWithRealWindowsAPIs']
                if p['key']=='backslash' and p['identifiers'][1].lower().startswith('kb:nvda+shift+')
                and len(p['identifiers'][1].split('+'))==3]} for v in prior['versions']]}
    def check(name, actual, expected):
        if actual != expected:
            raise AssertionError((name, actual, expected))
        result['checks'].append({'name': name, 'actual': actual, 'passed': True})

    plugin = ast.parse(HISTORICAL_PLUGIN)
    cls = next(n for n in plugin.body if isinstance(n, ast.ClassDef))
    scripts = []
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith('script_'):
            continue
        meta = next(n for n in node.decorator_list if isinstance(n, ast.Call))
        gesture = next((k.value.value for k in meta.keywords if k.arg == 'gesture'), None)
        desc = next(k.value.args[0].value for k in meta.keywords if k.arg == 'description')
        scripts.append({'name': node.name, 'line': node.lineno, 'gesture': gesture, 'description': desc,
                        'source': ast.get_source_segment(HISTORICAL_PLUGIN, node)})
    result['commands'] = scripts
    refs = json.loads((ROOT / 'docs/stopwatch_open_gesture_audit.json').read_text('utf-8'))['nvda']
    candidates = {normal(v) for v in ['kb:NVDA+f8','kb:NVDA+j','kb:NVDA+shift+j','kb:NVDA+control+j',
                                    'kb:NVDA+|','kb:NVDA+shift+\\','kb:NVDA+control+f12','kb:NVDA+f12']}
    for ref in refs:
        archive = ROOT / 'development_baseline/stopwatch-closure' / ('release-' + ref['version'] + '.tar.gz')
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        check(ref['version'] + ' archive hash', sha, ref['archiveSha256'])
        with tarfile.open(archive) as tar:
            sources = {m.name.split('/source/',1)[1]: tar.extractfile(m).read().decode('utf-8-sig')
                       for m in tar.getmembers() if m.isfile() and '/source/' in m.name and m.name.endswith(('.py','.ini'))}
        entry = {k:ref[k] for k in ('version','commit','url','archiveSha256')}
        entry['fileHashes'] = {n: hashlib.sha256(sources[n].encode()).hexdigest() for n in
                               ['scriptHandler.py','inputCore.py','keyboardHandler.py','globalCommands.py','ui.py','speech/speech.py','speech/manager.py','config/configSpec.py']}
        entry['conflicts'] = []
        for path, source in sources.items():
            if path.endswith('.py'):
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) and normal(node.value) in candidates:
                        entry['conflicts'].append({'file':path,'line':node.lineno,'gesture':node.value})
            else:
                for lineno, line in enumerate(source.splitlines(),1):
                    if line.lstrip().startswith(('#',';')) or '=' not in line:
                        continue
                    for value in line.split('=',1)[0].split(','):
                        value = value.strip().strip('"')
                        if normal(value) in candidates:
                            entry['conflicts'].append({'file':path,'line':lineno,'gesture':value})
        entry['functions'] = {}
        for path, names in [('scriptHandler.py', ['executeScript','getLastScriptRepeatCount','clearLastScript']),
                            ('globalCommands.py',['script_dateTime','script_review_currentCharacter'])]:
            entry['functions'][path] = {n.name:{'line':n.lineno,'end':n.end_lineno,
                'astSha256':hashlib.sha256(ast.dump(n).encode()).hexdigest()}
                for n in ast.walk(ast.parse(sources[path])) if isinstance(n,ast.FunctionDef) and n.name in names}
        # Execute original NVDA counter, unmodified, with deterministic clock.
        clock = NS(t=10.)
        ns = functions(sources['scriptHandler.py'], ['executeScript','getLastScriptRepeatCount','clearLastScript'],
            {'time':NS(time=lambda:clock.t),'weakref':weakref,'config':NS(conf={'keyboard':{'multiPressTimeout':500}}),
             '_lastScriptTime':0,'_lastScriptRef':None,'_lastScriptCount':0,'_isScriptRunning':False,
             'willSayAllResume':lambda g:False,'log':NS(exception=lambda *a: (_ for _ in ()).throw(AssertionError(a)))})
        calls = []
        def command(g): calls.append(ns['getLastScriptRepeatCount']())
        def other(g): pass
        for seconds in [10.,10.15,10.30,10.45,11.01]:
            clock.t=seconds; ns['executeScript'](command,None)
        check(ref['version']+' counter 4 presses and timeout', calls, [0,1,2,3,0])
        ns['executeScript'](other,None); ns['executeScript'](command,None)
        check(ref['version']+' different script resets',calls[-1],0)
        ns['clearLastScript'](); ns['executeScript'](command,None)
        check(ref['version']+' clear resets',calls[-1],0)
        clock.t += .501
        check(ref['version']+' getter expires',ns['getLastScriptRepeatCount'](),0)
        ns['clearLastScript']();calls.clear();clock.t=20.;ns['executeScript'](command,None)
        clock.t=20.5;ns['executeScript'](command,None)
        clock.t=21.;ns['executeScript'](command,None)
        check(ref['version']+' inclusive boundary and rolling window',calls,[0,1,2])
        # Native time/date function, real body, fake Win32 format APIs.
        native = next(n for n in ast.walk(ast.parse(sources['globalCommands.py'])) if isinstance(n,ast.FunctionDef) and n.name=='script_dateTime')
        native.decorator_list=[]
        out=[];count=NS(value=0)
        env={'getLastScriptRepeatCount':lambda:count.value,'scriptHandler':NS(getLastScriptRepeatCount=lambda:count.value),'ui':NS(message=out.append),
             'systemUtils':NS(_isSystemClockSecondsVisible=lambda:False),
             'winKernel':NS(LOCALE_NAME_USER_DEFAULT=0,TIME_NOSECONDS=1,DATE_LONGDATE=2,
                            GetTimeFormatEx=lambda *a:'time',GetDateFormatEx=lambda *a:'date')}
        exec(compile(ast.Module(body=[native],type_ignores=[]),'<native dateTime>','exec'),env)
        for i in range(3): count.value=i;env['script_dateTime'](None,None)
        check(ref['version']+' native time/date immediate order',out,['time','date','date'])
        result['timings']['native_date_'+ref['version']]=timing(lambda:env['script_dateTime'](None,None))
        char=next(n for n in ast.walk(ast.parse(sources['globalCommands.py'])) if isinstance(n,ast.FunctionDef) and n.name=='script_review_currentCharacter')
        char.decorator_list=[]
        for arg in char.args.args:arg.annotation=None
        char_out=[]
        info=NS(text='A',obj=None,expand=lambda unit:None)
        char_env={'getLastScriptRepeatCount':lambda:count.value,'scriptHandler':NS(getLastScriptRepeatCount=lambda:count.value),
            'api':NS(getReviewPosition=lambda:NS(copy=lambda:info)),
            'objectBelowLockScreenAndWindowsIsLocked':lambda obj:False,
            'textInfos':NS(UNIT_CHARACTER=1),'controlTypes':NS(OutputReason=NS(CARET=1)),
            'braille':NS(handler=NS(handleReviewMove=lambda **kw:None,message=lambda s:None)),
            'speech':NS(speakTextInfo=lambda *a,**kw:char_out.append('character'),
                spellTextInfo=lambda *a,**kw:char_out.append('description'),
                speakMessage=lambda s:char_out.append(s),speakSpelling=lambda s:char_out.append(s))}
        exec(compile(ast.Module(body=[char],type_ignores=[]),'<native character>','exec'),char_env)
        for i in range(3):count.value=i;char_env['script_review_currentCharacter'](None,None)
        check(ref['version']+' actual triple character command',char_out,['character','description','65,','0x41'])
        result['sources'].append(entry)

    # Actual generic dispatch: every prefix executes, counts past end repeat last.
    counter=NS(value=0);sys.modules['scriptHandler']=NS(getLastScriptRepeatCount=lambda:counter.value)
    out=[]
    handlers=tuple(lambda i=i:out.append(i) for i in range(4))
    for i in range(5): counter.value=i;compat.dispatch_repeated_script(handlers)
    check('generic four presses plus fifth',out,[0,1,2,3,3])
    result['traces']['generic'] = out
    # Virtual CallLater scheduler preserves due times, cancellations and generation.
    class Scheduler:
        def __init__(self):self.now=0;self.jobs=[]
        def schedule(self,ms,cb):
            job=NS(due=self.now+ms,cb=cb,cancelled=False)
            job.cancel=lambda:setattr(job,'cancelled',True)
            self.jobs.append(job);return job
        def advance(self,ms):
            self.now=ms
            for job in self.jobs[:]:
                if job.due<=ms and not job.cancelled:
                    job.cancelled=True;job.cb()
    for presses in [1,2,3,4]:
        s=Scheduler();trace=[]
        dispatcher=StopwatchGestures(schedule=s.schedule,repeat=lambda:counter.value,timeout=lambda:500)
        hs=tuple(lambda i=i:trace.append({'action':i,'at_ms':s.now}) for i in range(3))
        for i in range(presses):
            s.advance(i*150);counter.value=i;dispatcher.submit(hs)
        check('stopwatch no early action '+str(presses),trace,[])
        s.advance((presses-1)*150+500)
        check('stopwatch final selection '+str(presses),trace,
              [{'action':presses-1,'at_ms':(presses-1)*150+500}] if presses<=3 else [])
        result['traces']['stopwatch_'+str(presses)]=trace
    s=Scheduler();trace=[];counter.value=0
    d=StopwatchGestures(schedule=s.schedule,repeat=lambda:counter.value,timeout=lambda:500)
    d.submit((lambda:trace.append('toggle'),));s.advance(150);trace.append('unrelated command');s.advance(500)
    check('pending stopwatch survives unrelated command',trace,['unrelated command','toggle'])
    result['traces']['unrelated_command']=trace
    # Speech cancellation count at actual worldClock method boundary.
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='script_worldClock');node.decorator_list=[]
    speech_events=[];sys.modules['speech']=NS(cancelSpeech=lambda:speech_events.append('explicit cancel'))
    env={'scriptHandler':sys.modules['scriptHandler']}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<worldClock>','exec'),env)
    driver=NS(_terminated=False,_world_clock=NS(announce=lambda i:speech_events.append('message '+str(i))))
    for i in range(3):
        counter.value=i;speech_events.append('inputCore cancel (modeled)');env['script_worldClock'](driver,None)
    check('world clock explicit cancellation count',speech_events.count('explicit cancel'),3)
    result['traces']['world_clock']=speech_events
    counter.value=0
    result['timings']['generic_dispatch_to_sink']=timing(lambda:compat.dispatch_repeated_script((lambda:None,)))
    result['timings']['world_method_to_sink']=timing(lambda:env['script_worldClock'](driver,None))
    result['timings']['empty_probe']=timing(lambda:None)
    # Three timestamp boundaries in the actual _say body. Arrival here means
    # handler entry, not physical keyboard arrival; no global profiling hooks.
    say_node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_say')
    for arg in say_node.args.args:arg.annotation=None
    say_node.returns=None
    marks={}
    def producer():marks['function_start_ns']=time.perf_counter_ns();return 'audit'
    def sink(text):marks['message_submitted_ns']=time.perf_counter_ns()
    say_env={'ui':NS(message=sink)}
    exec(compile(ast.Module(body=[say_node],type_ignores=[]),'<actual say>','exec'),say_env)
    marks['handler_entry_ns']=time.perf_counter_ns();say_env['_say'](None,producer)
    result['traces']['handler_function_message_ns']=marks
    # Real synchronous content computations, bundled data and fixed synthetic
    # location/settings only. One cold call followed by warm calls per operation.
    from datetime import datetime, timezone
    from globalPlugins.awqati.application import (PrayerService, ClockService, CalendarService,
        AstronomyService, ArabianCalendarService, DailyInfoService)
    from globalPlugins.awqati.domain import (Location, Instant, CalculationMethod, AsrMethod,
        HighLatitudeRule, PrayerCalculationRequest, GregorianProvider, SaudiSolarHijriProvider,
        AfghanSolarHijriProvider, PersianSolarHijriProvider, ClockType)
    from globalPlugins.awqati.domain.settings import AwqatiSettings, StoredLocation, LocationKind
    from globalPlugins.awqati.infrastructure import (BundledCalculationMethodRepository, BundledTimezoneProvider,
        UmmAlQuraProvider, BundledArabianCalendarRepository)
    from globalPlugins.awqati.nvda_adapter.commands import CommandContent
    zones=BundledTimezoneProvider();lunar=UmmAlQuraProvider()
    prayers=PrayerService(BundledCalculationMethodRepository(),zones,lunar_calendar=lunar)
    location=Location('audit-riyadh','Riyadh',24.6877,46.7219,'Asia/Riyadh')
    now=NS(now=lambda:Instant(datetime(2026,11,3,9,tzinfo=timezone.utc)))
    def request(day, loc):
        return PrayerCalculationRequest(day,loc.latitude,loc.longitude,loc.timezone_id,
            CalculationMethod.MAKKAH,AsrMethod.STANDARD,HighLatitudeRule.AUTO,country_code='SA')
    settings=AwqatiSettings();settings.location=StoredLocation(LocationKind.CUSTOM,location,'SA')
    arabian=ArabianCalendarService(BundledArabianCalendarRepository(),now,zones)
    from globalPlugins.awqati.application import SettingsService
    isolated_settings=SettingsService.__new__(SettingsService)
    isolated_settings._runtime=settings  # Real getter/deepcopy; no repository/Apply.
    content=CommandContent(isolated_settings,now,zones,prayers,
        ClockService(now,zones,prayers,request),
        CalendarService(now,zones,(GregorianProvider(),lunar,SaudiSolarHijriProvider(),AfghanSolarHijriProvider(),PersianSolarHijriProvider())),
        DailyInfoService(AstronomyService(now,zones),arabian),arabian)
    result['timings']['content']={}
    for name,callback in {'current_details':lambda:content.current_details(str),
        'previous_details':lambda:content.previous_details(str),'daily_prayer_times':lambda:content.daily_prayer_times(str),
        'daily_info':lambda:content.daily_info_text('ar'),'qibla':lambda:content.qibla_text('ar'),
        'ghurubi':lambda:content.clock_text(ClockType.GHURUBI,'ar'),
        'settings_copy':lambda:isolated_settings.runtime_settings}.items():
        cold=timing(callback,1);warm=timing(callback,100)
        result['timings']['content'][name]={'first_call':cold,'warm':warm}
    result['soundDurations_ms']={}
    for path in (ROOT/'addon/globalPlugins/awqati/sounds/stopwatch').glob('*.wav'):
        with wave.open(str(path)) as audio:
            result['soundDurations_ms'][path.name]=1000*audio.getnframes()/audio.getframerate()
    result['productionHashes']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/'addon').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    target=ROOT/'docs/multi_press_evidence.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(result["checks"])} checks passed; {len(scripts)} scripts; evidence: {target}')


if __name__=='__main__':run()
