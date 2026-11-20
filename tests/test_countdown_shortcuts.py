"""Dev18 timer commands through real service, presenter and native repeat logic."""
import ast
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
import subprocess
import unittest
from unittest.mock import Mock, patch

import test_countdown as fixture
from test_countdown import ROOT
from test_multi_press_execution import plugin_driver
from test_corrective_followup import Translator
from awqati.domain.countdown import Countdown
from awqati.domain import AlertEvent, AlertEventType, AlertAction
from awqati.nvda_adapter import compat

PLUGIN=ROOT/'addon/globalPlugins/awqati/nvda_adapter/plugin.py'
MAP={
    'countdownSelected':'kb:NVDA+y', 'countdownToggle':'kb:NVDA+shift+y',
    'countdownWindow':'kb:NVDA+alt+y', 'countdownStopAlert':'kb:NVDA+control+y',
    'countdownRestart':'kb:NVDA+control+shift+y',
    'countdownNext':'kb:NVDA+windows+y', 'countdownPrevious':'kb:NVDA+windows+shift+y',
}

class TimerShortcutTests(unittest.TestCase):
    def setUp(self):
        self.model=fixture.CountdownTests();self.model.setUp()
        self.control,self.messages,self.ns=self.model.control()
        self.service=self.model.service;self.identity=self.model.identity
        self.driver,self.queue=plugin_driver();self.driver._countdowns=self.control

    def press(self, name, count=0):
        with patch.object(compat,'script_repeat_count',return_value=count):
            getattr(self.driver,'script_'+name)(None)

    def test_seven_exact_unique_defaults_and_other_scripts_bytecode_ast_unchanged(self):
        tree=ast.parse(PLUGIN.read_text('utf8'))
        scripts={n.name:n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('script_')}
        for name,key in MAP.items():
            node=scripts['script_'+name]
            self.assertEqual([key],[k.value.value for d in node.decorator_list for k in d.keywords if k.arg=='gesture'])
            self.assertTrue(any(k.arg=='category' for d in node.decorator_list for k in d.keywords))
        previous=ast.parse(subprocess.check_output(['git','show','0e8348d:'+PLUGIN.relative_to(ROOT).as_posix()],cwd=ROOT))
        for node in ast.walk(previous):
            if isinstance(node,ast.FunctionDef) and node.name.startswith('script_') and not node.name.startswith('script_countdown'):
                self.assertEqual(ast.dump(node),ast.dump(scripts[node.name]),node.name)
        defaults=[k.value.value.lower() for n in scripts.values() for d in n.decorator_list for k in d.keywords if k.arg=='gesture']
        self.assertEqual(len(defaults),len(set(defaults)))

    def test_single_double_immediate_localized_no_writes_or_queue(self):
        for language in ('ar','en'):
            self.ns['_']=Translator(language);self.messages.clear()
            before=deepcopy(self.service.rows);writes=self.model.repo.writes
            self.press('countdownSelected');self.assertEqual(1,len(self.messages))
            self.assertIn('Reading',self.messages[-1])
            self.press('countdownSelected',1);self.assertEqual(2,len(self.messages))
            self.assertIn('1',self.messages[-1]);self.assertIn('Reading',self.messages[-1])
            self.assertEqual(before,self.service.rows);self.assertEqual(writes,self.model.repo.writes)
            self.assertEqual([],self.queue)

    def test_toggle_start_pause_resume_and_fast_repeats_do_not_toggle(self):
        for state in ('running','paused','running'):
            self.press('countdownToggle');self.assertEqual(state,self.service.rows[self.identity]['state'])
            self.press('countdownToggle',1);self.assertEqual(state,self.service.rows[self.identity]['state'])

    def test_open_window_and_restart_queued_once(self):
        self.driver._showCountdowns=Mock()
        self.press('countdownWindow');self.queue.pop()();self.driver._showCountdowns.assert_called_once()
        self.press('countdownRestart');self.press('countdownRestart',1)
        self.assertEqual(1,len(self.queue))
        self.queue.pop()();self.assertEqual('ready',self.service.rows[self.identity]['state'])

    def test_restart_always_confirms_in_all_states_and_preserves_other_timer(self):
        other=Countdown.create('Other',120);self.service.put(other)
        self.service.transition(other.timer_id,'start')
        for state in ('ready','running','paused','finished','cancelled'):
            self.service.rows[self.identity]['state']=state
            before=deepcopy(self.service.rows);prompts=[]
            self.ns['wx'].MessageBox=lambda *a:prompts.append(a) or 0
            self.control.restart();self.assertEqual(before,self.service.rows);self.assertEqual(1,len(prompts))
            self.ns['wx'].MessageBox=lambda *a:1
            self.control.restart()
            self.assertEqual(60*10**9,self.service.remaining(self.identity))
            self.assertEqual(before[other.timer_id],self.service.rows[other.timer_id])

    def test_navigation_wrap_empty_single_and_stale_selection_never_writes(self):
        self.control.selected=None;self.press('countdownNext');self.assertEqual(self.identity,self.control.selected)
        self.press('countdownPrevious');self.assertEqual(self.identity,self.control.selected)
        other=Countdown.create('Other',120);self.service.put(other)
        self.model.start();self.service.transition(other.timer_id,'start')
        before=deepcopy(self.service.rows);writes=self.model.repo.writes
        self.press('countdownNext');self.assertEqual(other.timer_id,self.control.selected)
        self.press('countdownNext',1);self.assertEqual(self.identity,self.control.selected)
        self.press('countdownPrevious');self.assertEqual(other.timer_id,self.control.selected)
        self.assertEqual(before,self.service.rows);self.assertEqual(writes,self.model.repo.writes)
        self.control.selected='deleted';self.press('countdownPrevious');self.assertEqual(other.timer_id,self.control.selected)
        for identity in list(self.service.definitions):self.service.delete(identity)
        self.press('countdownNext');self.assertIn('no countdown',self.messages[-1])

    def test_navigation_syncs_native_list_and_close_keeps_selection(self):
        manager=self.model.manager();manager.control=self.control;self.control.dialog=manager
        other=Countdown.create('Other',120);self.service.put(other)
        self.press('countdownNext');token=manager.tokens[self.control.selected]
        self.assertEqual(token,manager.list.selection);self.assertEqual(token,manager.list.focus)
        manager.control.cancel_preview=Mock();manager.EndModal=Mock()
        manager.on_close.__func__.__globals__['wx'].ID_CANCEL=99
        selected=self.control.selected;manager.on_close(None)
        self.assertEqual(selected,self.control.selected)

    def test_silence_current_unselected_one_per_press_preserves_queued_timer(self):
        self.service.put(replace(self.model.timer,repeat=True))
        first=self.model.finish();other=Countdown.create('Other',1)
        self.service.put(other);self.service.transition(other.timer_id,'start');self.model.advance(1)
        second=next(e for e in self.service.poll(self.model.instant()) if e.metadata['timer_id']==other.timer_id)
        runtime=self.control.runtime;runtime.scheduler.schedule_many([first,second]);runtime.presenter.present_next()
        self.control.selected=other.timer_id
        self.press('countdownStopAlert');self.assertTrue(self.service.rows[self.identity]['ack'])
        self.assertTrue(runtime.scheduler.has_pending('timers.'+other.timer_id))
        self.assertIn('Reading',self.messages[-1]);self.assertEqual(other.timer_id,self.control.selected)
        runtime.presenter.present_next();self.press('countdownStopAlert',1)
        self.assertIn('Other',self.messages[-1]);self.assertIsNone(runtime.presenter.current)
        self.ns['_']=Translator('ar');self.press('countdownStopAlert',2)
        self.assertEqual('لا يوجد رنين حاليًا',self.messages[-1])

    def test_no_ring_never_cancels_other_alerts(self):
        runtime=self.control.runtime
        runtime.scheduler.schedule(AlertEvent('personal',AlertEventType.PERSONAL_ALARM,self.model.instant(),
            action=AlertAction.SPEECH,metadata={'name':'Personal','duration':60}))
        runtime.presenter.present_next();self.press('countdownStopAlert')
        self.assertEqual(AlertEventType.PERSONAL_ALARM,runtime.presenter.current.event_type)

    def test_silence_stops_output_even_when_acknowledgement_cannot_be_saved(self):
        self.service.put(replace(self.model.timer,repeat=True))
        event=self.model.finish();runtime=self.control.runtime
        runtime.scheduler.schedule(event);runtime.presenter.present_next()
        self.model.repo.fail=True
        self.press('countdownStopAlert')
        self.assertIsNone(runtime.presenter.current)
        self.assertNotIn('stopped',self.messages[-1])
        self.assertIn('could not be saved',self.messages[-1])

    def test_missing_selection_never_changes_another_timer(self):
        self.control.selected=None
        before=deepcopy(self.service.rows)
        for name in ('countdownSelected','countdownToggle','countdownRestart'):
            self.press(name)
            while self.queue:self.queue.pop(0)()
        self.assertEqual(before,self.service.rows)
        self.assertTrue(all('Select a countdown' in text for text in self.messages))

    def test_native_repeat_engine_dispatches_both_queries_without_wait(self):
        import weakref
        source=(ROOT/'development_baseline/multipress-audit/2026.3/scriptHandler.py').read_text('utf8')
        now=[100.];errors=[]
        ns={'weakref':weakref,'time':NS(time=lambda:now[0]),'config':NS(conf={'keyboard':{'multiPressTimeout':500}}),
            '_lastScriptTime':0,'_lastScriptRef':None,'_lastScriptCount':0,'_isScriptRunning':False,
            'willSayAllResume':lambda g:False,'log':NS(exception=lambda *a:errors.append(a))}
        functions=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in ('executeScript','getLastScriptRepeatCount')]
        exec(compile(ast.Module(body=functions,type_ignores=[]),'official repeat engine','exec'),ns)
        with patch.object(compat,'script_repeat_count',ns['getLastScriptRepeatCount']):
            for index in range(2):
                now[0]+=.1;ns['executeScript'](self.driver.script_countdownSelected,None)
                self.assertEqual(index+1,len(self.messages))
        self.assertIn('Timers: 1',self.messages[-1]);self.assertEqual([],errors);self.assertEqual([],self.queue)

if __name__=='__main__':unittest.main()
