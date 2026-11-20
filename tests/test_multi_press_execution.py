"""Dev17 regression: actual adapter/controller bodies with isolated boundaries.

These are unit/integration tests, not claims of audible or physical key testing.
"""
import ast
import __future__
import hashlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from test_stopwatch import controller_driver, ROOT
from awqati.nvda_adapter import compat
import test_personal_alarm_followup as alarm_fixture
from test_personal_alarm_followup import command_driver

ADAPTER=ROOT/'addon/globalPlugins/awqati/nvda_adapter'

def plugin_driver():
    tree=ast.parse((ADAPTER/'plugin.py').read_text('utf8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
    cls.bases=[]
    cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and (n.name.startswith('script_') or n.name=='_press')]
    for method in cls.body:method.decorator_list=[]
    queued=[]
    ns={'compat':compat,'wx':NS(CallAfter=lambda cb,*a,**kw:queued.append(lambda:cb(*a,**kw)))}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'actual plugin','exec',flags=__future__.annotations.compiler_flag),ns)
    obj=ns['GlobalPlugin']();obj._actions=NS(invalidate_feedback=Mock(),verify_online=Mock())
    obj._terminated=False
    return obj,queued

class ImmediateStopwatchTests(unittest.TestCase):
    def make(self,language='en'):
        d,queue=plugin_driver()
        control,clock,repo,ns,messages,copied,tones,confirms=controller_driver(language)
        d._stopwatch=control
        return d,queue,control,clock,repo,ns,messages,confirms

    def press(self,d,name,count=0):
        with patch.object(compat,'script_repeat_count',return_value=count):getattr(d,name)(None)

    def test_start_pause_resume_are_immediate_and_fast_extra_presses_do_not_toggle(self):
        d,q,c,clock,repo,ns,msg,confirms=self.make()
        pending=[];c.mode=2;c._play_tone=lambda action,done:pending.append(done) or True
        self.press(d,'script_stopwatchInfo')
        self.assertEqual('running',c.watch.state)
        self.assertEqual([],q);self.assertEqual([],msg)
        clock.advance(7)
        for i in range(1,6):self.press(d,'script_stopwatchInfo',i)
        self.assertEqual('running',c.watch.state)
        self.press(d,'script_stopwatchInfo')
        self.assertEqual('paused',c.watch.state);self.assertEqual(7_000_000_000,c.watch.elapsed_ns())
        self.press(d,'script_stopwatchInfo')
        self.assertEqual('running',c.watch.state);self.assertEqual([],q)

    def test_new_lap_is_recorded_once_queries_never_record_or_mutate(self):
        for language in ('ar','en'):
            d,q,c,clock,repo,ns,msg,confirms=self.make(language);c.mode=1;c.toggle();clock.advance(9)
            for i in range(5):self.press(d,'script_stopwatchLaps',i)
            self.assertEqual(1,len(c.watch.laps))
            self.assertIn('تم إنشاء جولة جديدة' if language=='ar' else 'A new lap has been created',msg[-1])
            self.assertEqual(9_000_000_000,c.watch.laps[0].duration_ns)
            clock.advance(3);writes=repo.writes
            for name in ('script_stopwatchTotal','script_stopwatchCurrentLap'):
                for i in range(5):self.press(d,name,i)
            self.assertEqual(writes,repo.writes);self.assertEqual('running',c.watch.state)
            self.assertEqual(1,len(c.watch.laps));self.assertEqual([],q)

    def test_reset_running_is_refused_paused_requires_confirmation_and_ignores_repeats(self):
        d,q,c,clock,repo,ns,msg,confirms=self.make();c.mode=1;c.toggle();clock.advance(2)
        self.press(d,'script_stopwatchReset');q.pop()()
        self.assertEqual('running',c.watch.state);self.assertEqual([],confirms)
        c.toggle();self.press(d,'script_stopwatchReset');q.pop()()
        self.assertEqual('paused',c.watch.state);self.assertEqual(1,len(confirms))
        for i in range(1,5):self.press(d,'script_stopwatchReset',i)
        self.assertEqual([],q)
        ns['wx'].MessageBox=lambda *a:ns['wx'].YES
        self.press(d,'script_stopwatchReset');q.pop()()
        self.assertEqual('idle',c.watch.state)

    def test_both_queries_localize_empty_laps_without_new_actions(self):
        for language in ('ar','en'):
            d,q,c,clock,repo,ns,msg,confirms=self.make(language)
            for i in range(2):self.press(d,'script_stopwatchCurrentLap',i)
            self.assertEqual(2,len(msg));self.assertEqual(0,repo.writes)
            self.assertEqual('idle',c.watch.state)

    def test_actual_native_counter_immediate_selection_timeout_and_script_change(self):
        # Official 2026.3 source engine, same semantics as all audited releases.
        source=(ROOT/'development_baseline/multipress-audit/2026.3/scriptHandler.py').read_text('utf8')
        import weakref
        now=[100.];errors=[]
        space={'weakref':weakref,'time':NS(time=lambda:now[0]),'config':NS(conf={'keyboard':{'multiPressTimeout':500}}),
            '_lastScriptTime':0,'_lastScriptRef':None,'_lastScriptCount':0,'_isScriptRunning':False,
            'willSayAllResume':lambda g:False,'log':NS(exception=lambda *a:errors.append(a))}
        functions=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in ('executeScript','getLastScriptRepeatCount')]
        exec(compile(ast.Module(body=functions,type_ignores=[]),'official counter','exec'),space)
        d,q,c,clock,repo,ns,msg,confirms=self.make();c.mode=1
        with patch.object(compat,'script_repeat_count',space['getLastScriptRepeatCount']):
            for _ in range(5):now[0]+=.1;space['executeScript'](d.script_stopwatchInfo,None)
            self.assertEqual('running',c.watch.state)
            now[0]+=1;space['executeScript'](d.script_stopwatchInfo,None)
            self.assertEqual('paused',c.watch.state)
            space['executeScript'](d.script_stopwatchTotal,None)
            space['executeScript'](d.script_stopwatchInfo,None)
            self.assertEqual('running',c.watch.state)
        self.assertEqual([],errors);self.assertEqual([],q)

class AlarmSafetyTests(unittest.TestCase):
    setUp=alarm_fixture.AlarmCommandFollowupTests.setUp
    start=alarm_fixture.AlarmCommandFollowupTests.start
    def test_triple_stop_and_all_extra_presses_never_snooze_or_repeat_stop(self):
        alarm=self.start(snooze_minutes=5);d=command_driver(self.runtime,'ar',self.messages)
        with patch.object(d,'_snoozePersonalAlarm',wraps=d._snoozePersonalAlarm) as snooze,patch.object(d,'_stopPersonalAlarm',wraps=d._stopPersonalAlarm) as stop:
            for i in range(7):
                with patch.object(compat,'script_repeat_count',return_value=i):d.script_personalAlarmInfo(None)
            snooze.assert_not_called();stop.assert_called_once()
        self.assertIsNone(self.runtime._last_snooze)
        self.assertIsNone(self.runtime.alarms.state[alarm.alarm_id]['snooze'])

    def test_independent_snooze_never_calls_stop_and_extra_presses_do_not_resave(self):
        self.start(snooze_minutes=5);d=command_driver(self.runtime,'ar',self.messages)
        with patch.object(d,'_stopPersonalAlarm') as stop,patch.object(d,'_snoozePersonalAlarm',wraps=d._snoozePersonalAlarm) as snooze:
            for i in range(5):
                with patch.object(compat,'script_repeat_count',return_value=i):d.script_snoozePersonalAlarm(None)
            stop.assert_not_called();snooze.assert_called_once()
        self.assertIn('تم تفعيل وضع الغفوة',self.messages[0])

class PrayerSeparationTests(unittest.TestCase):
    def test_window_never_schedules_verification_and_verification_repeats_do_not_open_it(self):
        d,q=plugin_driver();d._showPrayerTimes=Mock()
        d.script_prayerTimesWindow(None)
        self.assertEqual(1,len(q));q.pop()();d._showPrayerTimes.assert_called_once();d._actions.verify_online.assert_not_called()
        for i in range(5):
            with patch.object(compat,'script_repeat_count',return_value=i):d.script_prayerVerification(None)
        self.assertEqual(1,len(q));q.pop()()
        d._actions.verify_online.assert_called_once_with(from_global_command=True)
        d._showPrayerTimes.assert_called_once()

class NetworkFeedbackTests(unittest.TestCase):
    def make(self):
        queued=[];messages=[]
        ns={'wx':NS(CallLater=lambda ms,cb:queued.append(cb)), 'ui':NS(message=messages.append)}
        tree=ast.parse((ADAPTER/'task53_actions.py').read_text('utf8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Task53Actions')
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'actual network actions','exec',flags=__future__.annotations.compiler_flag),ns)
        obj=ns['Task53Actions'].__new__(ns['Task53Actions']);obj._closed=False;obj._feedback_generation=0
        dialog=NS(IsBeingDeleted=lambda:False,IsShown=lambda:True,IsActive=lambda:True)
        return obj,dialog,queued,messages

    def test_old_privacy_or_start_message_suppressed_after_new_command_or_close(self):
        for outcome in ('new_command','close','destroyed','inactive'):
            obj,d,q,msg=self.make();obj._announce_later('old',d,0)
            if outcome=='new_command':obj.invalidate_feedback()
            elif outcome=='close':obj._closed=True
            elif outcome=='destroyed':d.IsBeingDeleted=lambda:True
            else:d.IsActive=lambda:False
            q.pop()();self.assertEqual([],msg)

    def test_current_focus_message_still_delivered_once_after_settle(self):
        obj,d,q,msg=self.make();obj._announce_later('current',d,0)
        self.assertEqual([],msg);q.pop()();self.assertEqual(['current'],msg)

    def test_deleted_wx_wrapper_is_not_dereferenced_by_queued_message(self):
        obj,d,q,msg=self.make()
        class DeletedDialog:
            def __bool__(self):return False
            def IsBeingDeleted(self):raise RuntimeError('wrapped wx object deleted')
        obj._announce_later('old',DeletedDialog(),0)
        q.pop()();self.assertEqual([],msg)

    def test_online_verification_cannot_start_worker_before_session_consent(self):
        obj,d,q,msg=self.make()
        obj.verify_online.__func__.__globals__['_']=str
        obj.settings=NS(runtime_settings=NS(location=object()))
        obj._privacy_approved=False
        obj._show_global_privacy_prompt=Mock()
        obj._start_online_verification=Mock()
        obj.verify_online(from_global_command=True)
        obj._show_global_privacy_prompt.assert_called_once()
        obj._start_online_verification.assert_not_called()
        self.assertFalse(obj._privacy_approved)
        obj._privacy_approved=True
        obj.verify_online(from_global_command=True)
        obj._start_online_verification.assert_called_once_with(obj.settings.runtime_settings.location)

    def test_async_result_is_not_delivered_after_switch_or_close_even_if_already_queued(self):
        for switch_at in ('before_finish','before_complete','close','none'):
            obj,dialog,delayed,messages=self.make()
            callbacks=[];success=[]
            dialog.Show=lambda:None;dialog.cancel_button=NS(SetFocus=lambda:None)
            dialog.Destroy=lambda:None
            module=sys.modules[__name__]
            ns=obj._run_async.__func__.__globals__
            class Token:
                def cancel(self):pass
            class Worker:
                def __init__(self,*,target,**kwargs):self.target=target
                def start(self):self.target()
            ns.update(CancellationToken=Token,_OperationDialog=lambda *a:dialog,
                _interaction_parent=lambda:None,gui=NS(mainFrame=object()),
                threading=NS(Thread=Worker),wx=NS(CallLater=lambda ms,cb:delayed.append(cb),CallAfter=callbacks.append))
            obj._tokens=set()
            obj._run_async('title','start',lambda token:'result',success.append)
            self.assertEqual(1,len(callbacks))
            if switch_at=='before_finish':obj.invalidate_feedback()
            if switch_at=='close':obj._closed=True
            callbacks.pop()()
            if switch_at=='before_complete':obj.invalidate_feedback()
            for callback in delayed:callback()
            self.assertEqual(['result'] if switch_at=='none' else [],success)
            self.assertEqual(set(),obj._tokens)

class IntegrityTests(unittest.TestCase):
    def test_no_retired_dispatcher_in_package_or_plugin_and_all_sounds_byte_exact(self):
        source=(ADAPTER/'plugin.py').read_text('utf8')
        self.assertNotIn('StopwatchGestures',source);self.assertNotIn('_stopwatch_presses',source)
        self.assertFalse((ADAPTER/'stopwatch_gestures.py').exists())
        for p in (ROOT/'addon/globalPlugins/awqati/sounds').rglob('*.wav'):
            old=subprocess.check_output(['git','show','f141e9a:'+p.relative_to(ROOT).as_posix()],cwd=ROOT)
            self.assertEqual(hashlib.sha256(old).digest(),hashlib.sha256(p.read_bytes()).digest(),str(p))

    def test_every_repeated_description_begins_with_owner_approved_arabic_form(self):
        from test_corrective_followup import Translator
        tr=Translator('ar');tree=ast.parse((ADAPTER/'plugin.py').read_text('utf8'))
        for n in ast.walk(tree):
            if isinstance(n,ast.keyword) and n.arg=='description':
                en=n.value.args[0].value
                if en.startswith('Press once'):
                    self.assertTrue(tr(en).startswith('بالضغط عليه'),en)
                    self.assertNotIn('مهلة',tr(en))

if __name__=='__main__':unittest.main()
