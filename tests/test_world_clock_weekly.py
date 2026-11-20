"""Offline weekly scheduling, native controller boundaries and real TZif rule updates."""
from datetime import datetime,timezone
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from queue import Queue
import sys
import tempfile
from threading import Event,Thread,get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from urllib.request import urlopen
from zipfile import BadZipFile
from time_tools_driver import definitions,ROOT
from test_world_clock import Memory,DATA
import test_world_clock_updates as fixture
from awqati.application.world_clock_updates import WorldUpdatePolicy,WEEK
from awqati.application.world_clock import WorldClockService
from awqati.domain import ClockType,ClockPresentationSettings
from awqati.infrastructure.stopwatch import StopwatchRepository
from awqati.infrastructure.world_clock import (WorldClockUpdater,WorldDataError,WorldDataIncompatible,load_data,active_root,canonical,CHANNEL,PREFIX,download,trusted_url)
sys.path.insert(0,str(ROOT/'tools'))
from world_clock_live_probe import historical_fixture


class WeeklyPolicyTests(unittest.TestCase):
    def setUp(self):self.now=[1000000];self.repo=Memory();self.policy=WorldUpdatePolicy(self.repo,lambda:self.now[0])

    def test_default_enabled_due_and_no_writes_on_read(self):
        self.assertTrue(self.policy.enabled);self.assertTrue(self.policy.due());self.assertEqual(0,self.repo.writes)

    def test_weekly_success_and_actual_update_dates_are_independent(self):
        self.policy.success(True);updated=self.policy.state['lastDataUpdate']
        self.now[0]+=100;self.policy.success(False)
        self.assertEqual(updated,self.policy.state['lastDataUpdate']);self.assertEqual(self.now[0],self.policy.state['lastSuccessfulCheck'])
        self.now[0]+=WEEK-1;self.assertFalse(self.policy.due());self.now[0]+=1;self.assertTrue(self.policy.due())

    def test_bounded_persistent_backoff_does_not_mark_success(self):
        for delay in (3600,21600,86400,WEEK,WEEK):
            self.policy.failure('URLError: offline');self.assertIsNone(self.policy.state['lastSuccessfulCheck'])
            self.assertEqual(self.now[0]+delay,self.policy.deadline());self.assertFalse(self.policy.due());self.now[0]+=delay
            self.assertTrue(self.policy.due())
        self.assertEqual(4,self.policy.state['failures'])
        restored=WorldUpdatePolicy(self.repo,lambda:self.now[0]);self.assertEqual(self.policy.state,restored.state)

    def test_disable_persists_and_success_clears_failures(self):
        self.policy.set_enabled(False);self.assertFalse(self.policy.due());self.policy.failure('offline');self.policy.success(False)
        self.assertEqual(0,self.policy.state['failures']);self.assertIsNone(self.policy.state['lastError'])
        self.assertFalse(WorldUpdatePolicy(self.repo).enabled)

    def test_failed_setting_save_preserves_value_and_bad_file_is_not_overwritten(self):
        self.repo.fail=True
        with self.assertRaises(OSError):self.policy.set_enabled(False)
        self.assertTrue(self.policy.enabled)
        corrupt=Memory({'schemaVersion':99});policy=WorldUpdatePolicy(corrupt);self.assertFalse(policy.enabled);self.assertEqual(0,corrupt.writes)


class Job:
    def __init__(self,delay,callback):self.delay,self.callback,self.stopped=delay,callback,False
    def Stop(self):self.stopped=True


class WeeklyControllerTests(unittest.TestCase):
    def make(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        callbacks=Queue();messages=[];workers=[];jobs=[]
        class Worker(Thread):
            def __init__(self,**kw):super().__init__(**kw);workers.append(self)
        def later(delay,callback):job=Job(delay,callback);jobs.append(job);return job
        ns={'datetime':datetime,'timezone':timezone,'Path':Path,'Thread':Worker,'Event':Event,'json':json,
            'BadZipFile':BadZipFile,'WorldDataError':WorldDataError,'WorldDataIncompatible':WorldDataIncompatible,
            'WorldUpdatePolicy':WorldUpdatePolicy,'WorldClockService':WorldClockService,'ClockType':ClockType,
            'StopwatchRepository':StopwatchRepository,'WindowsLocalTimezone':lambda:lambda instant:timezone.utc,
            'WorldClockUpdater':WorldClockUpdater,'load_data':load_data,'active_root':active_root,
            'wx':SimpleNamespace(CallAfter=callbacks.put,CallLater=later),'ui':SimpleNamespace(message=lambda *a,**kw:messages.append((a,kw))),
            '_':lambda text:text,'languageHandler':SimpleNamespace(getLanguage=lambda:'en')}
        definitions('world_clock_control.py',ns,{'WorldClockControl'})
        runtime=SimpleNamespace(presenter=SimpleNamespace(current=None),scheduler=SimpleNamespace(current=None))
        control=ns['WorldClockControl'](Path(temp.name),runtime,DATA.parents[1])
        control.policy.clock=lambda:1000000
        self.addCleanup(control.close)
        return control,callbacks,messages,workers,jobs

    def finish(self,callbacks,workers):
        for worker in workers:worker.join(timeout=10);self.assertFalse(worker.is_alive())
        callbacks.get(timeout=1)()

    def test_startup_defers_one_shot_no_initial_network_and_recent_check_waits_week(self):
        control,callbacks,messages,workers,jobs=self.make();self.assertFalse(workers);self.assertFalse(messages)
        self.assertEqual(1,len(jobs));self.assertEqual(60000,jobs[0].delay)
        control.policy.success(False);control.schedule_auto();self.assertTrue(jobs[0].stopped);self.assertEqual(WEEK*1000,jobs[-1].delay)

    def test_automatic_unchanged_is_silent_and_runs_in_worker(self):
        control,callbacks,messages,workers,jobs=self.make();threads=[]
        control.updater.check=lambda *a:(threads.append(get_ident()) or None)
        control.auto_check();self.finish(callbacks,workers)
        self.assertEqual([],messages);self.assertNotEqual(get_ident(),threads[0]);self.assertEqual(1000000,control.policy.state['lastSuccessfulCheck'])
        self.assertIsNone(control.policy.state['lastDataUpdate']);self.assertEqual(WEEK*1000,jobs[-1].delay)

    def test_automatic_network_and_signature_failures_silent_with_diagnostics(self):
        for error in (OSError('offline'),WorldDataError('invalid signature')):
            control,callbacks,messages,workers,jobs=self.make()
            def check(*args):raise error
            control.updater.check=check;control.auto_check();self.finish(callbacks,workers)
            self.assertFalse(messages);self.assertIsNone(control.policy.state['lastSuccessfulCheck']);self.assertIn(str(error),control.policy.state['lastError'])
            self.assertEqual(3600000,jobs[-1].delay)

    def test_disabled_stops_auto_but_manual_ignores_last_check_and_enabled_flag(self):
        control,callbacks,messages,workers,jobs=self.make();control.policy.success(False);control.set_automatic(False)
        control.updater.check=Mock(return_value=None);control.auto_check();control.updater.check.assert_not_called()
        control.update();self.finish(callbacks,workers);control.updater.check.assert_called_once()
        self.assertEqual('World clock data are up to date.',messages[-1][0][0])

    def test_manual_incompatible_is_distinct_from_network_and_invalid(self):
        control,callbacks,messages,workers,jobs=self.make()
        control.updater.check=Mock(side_effect=WorldDataIncompatible('new app required'))
        control.update();self.finish(callbacks,workers)
        self.assertIn('requires a newer version',messages[-1][0][0]);self.assertIsNone(control.policy.state['lastSuccessfulCheck'])

    def test_only_one_worker_and_disabling_during_download_cancels_silently(self):
        control,callbacks,messages,workers,jobs=self.make();entered=Event();release=Event()
        def check(version,cancelled):entered.set();release.wait(timeout=2);return None
        control.updater.check=Mock(side_effect=check);control.update(automatic=True);self.assertTrue(entered.wait(timeout=1))
        control.update();self.assertEqual(1,len(workers));control.set_automatic(False);release.set()
        for worker in workers:worker.join(timeout=3)
        self.assertTrue(callbacks.empty());self.assertFalse(messages);self.assertFalse(control.updating);self.assertIsNone(control.policy.state['lastSuccessfulCheck'])

    def test_notification_waits_for_priority_alert_then_queues_next(self):
        control,callbacks,messages,workers,jobs=self.make();control.runtime.presenter.current=object()
        control.updated_notice();self.assertFalse(messages);self.assertEqual(5000,jobs[-1].delay)
        control.runtime.presenter.current=None
        with patch.dict(sys.modules,{'speech.priorities':SimpleNamespace(Spri=SimpleNamespace(NEXT='next'))}):jobs[-1].callback()
        self.assertEqual('World clock data updated.',messages[-1][0][0]);self.assertEqual('next',messages[-1][1]['speechPriority'])

    def test_close_stops_deadlines_and_late_notification(self):
        control,callbacks,messages,workers,jobs=self.make();control.runtime.presenter.current=object();control.updated_notice()
        control.close();self.assertTrue(all(j.stopped for j in jobs));jobs[-1].callback();self.assertFalse(messages)


class RuleUpdateTests(unittest.TestCase):
    setUpClass=classmethod(fixture.WorldUpdateTests.setUpClass.__func__)
    setUp=fixture.WorldUpdateTests.setUp
    release=fixture.WorldUpdateTests.release
    sign=fixture.WorldUpdateTests.sign
    fetch=fixture.WorldUpdateTests.fetch

    def test_signed_incompatible_minimum_rejected_before_archive(self):
        document=dict(self.manifest);document['minAwqatiVersion']='5.0.0-dev999';self.manifest=self.sign(document)
        with self.assertRaises(WorldDataIncompatible):self.updater.check(self.current)
        self.assertEqual([CHANNEL],self.requests)

    def test_real_iana_rule_replacement_changes_cuba_without_restart_or_other_zones(self):
        old=historical_fixture(self.root/'old',self.bundle);catalog,old_zones,_=load_data(old)
        service=WorldClockService(catalog,Memory());city=catalog.search('Havana')[0];service.add(city)
        service.edit_names(city.city_id,'ar','هافانا الخاصة',city.country_ar);service.edit_names(city.city_id,'en','My Havana',city.country_en)
        before=service.repository.data;stamp=datetime(2026,11,1,6,tzinfo=timezone.utc)
        self.assertEqual(-300,int(stamp.astimezone(old_zones.get_timezone(city.zone)).utcoffset().total_seconds()/60))
        target=self.updater.check(self.current);new_catalog,new_zones,_=load_data(target,full=True);self.updater.activate(target)
        self.assertEqual(-240,int(stamp.astimezone(new_zones.get_timezone(city.zone)).utcoffset().total_seconds()/60))
        self.assertEqual(540,int(stamp.astimezone(new_zones.get_timezone('Asia/Tokyo')).utcoffset().total_seconds()/60))
        self.assertIsNot(old_zones.get_timezone(city.zone),new_zones.get_timezone(city.zone))
        restored=WorldClockService(new_catalog,service.repository);self.assertEqual(before,service.repository.data)
        self.assertEqual('هافانا الخاصة',restored.names(restored.rows[0],'ar')[0]);self.assertEqual('My Havana',restored.names(restored.rows[0],'en')[0])

    def test_controller_atomically_adopts_new_provider_and_preserves_live_user_service(self):
        helper=WeeklyControllerTests();control,callbacks,messages,workers,jobs=helper.make();self.addCleanup(helper.doCleanups)
        old=historical_fixture(self.root/'old-control',self.bundle);catalog,old_zones,_=load_data(old)
        control.service=WorldClockService(catalog,Memory());city=catalog.search('Havana')[0];control.service.add(city)
        control.service.edit_names(city.city_id,'en','Custom Havana','Custom Cuba');control.zones=old_zones;control.updater=self.updater
        old_service=control.service;control.update();helper.finish(callbacks,workers)
        self.assertIs(old_service,control.service);self.assertIsNot(old_zones,control.zones)
        stamp=datetime(2026,11,1,6,tzinfo=timezone.utc)
        self.assertEqual(-240,int(stamp.astimezone(control.zones.get_timezone(city.zone)).utcoffset().total_seconds()/60))
        self.assertEqual(('Custom Havana','Custom Cuba'),control.service.names(control.service.rows[0],'en'))
        self.assertEqual(control.policy.state['lastDataUpdate'],control.policy.state['lastSuccessfulCheck'])

    def test_local_http_server_fetches_manifest_and_archive_without_live_internet(self):
        payloads={'/manifest':canonical(self.manifest),'/archive':self.archive}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                body=payloads[handler.path];handler.send_response(200);handler.send_header('Content-Length',str(len(body)));handler.end_headers();handler.wfile.write(body)
            def log_message(*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def fetch(url,limit,cancelled):
                with urlopen('http://127.0.0.1:'+str(server.server_port)+('/manifest' if url==CHANNEL else '/archive'),timeout=2) as response:return response.read(limit)
            target=WorldClockUpdater(self.bundle,self.user,fetch).check(self.current)
            self.assertEqual('2026-11-03.3',load_data(target)[0].version)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_official_origin_pins_repo_and_branch_and_rejects_path_encoding(self):
        self.assertTrue(trusted_url(CHANNEL));self.assertFalse(trusted_url(PREFIX+'manifest.json?ref=master'))
        self.assertFalse(trusted_url(PREFIX+'%2e%2e/evil'));self.assertFalse(trusted_url('http://api.github.com/anything'))


if __name__=='__main__':unittest.main()
