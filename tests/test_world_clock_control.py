"""The real update controller keeps heavy work and errors off NVDA's GUI thread."""
from datetime import datetime,timezone
from pathlib import Path
from queue import Queue
import sys
from threading import Event,Thread,get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from time_tools_driver import definitions, ROOT
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.infrastructure.world_clock import WorldDataError


class WorldControlTests(unittest.TestCase):
    def make(self,check):
        callbacks=Queue();messages=[];workers=[]
        class ProbeThread(Thread):
            def __init__(self,**options):super().__init__(**options);workers.append(self)
        ns={'Thread':ProbeThread,'wx':SimpleNamespace(CallAfter=callbacks.put),'ui':SimpleNamespace(message=lambda text:messages.append((get_ident(),text))),
            '_':lambda text:text,'WorldDataError':WorldDataError,'BadZipFile':__import__('zipfile').BadZipFile,
            'load_data':lambda root:('catalog','zones','metadata'),'json':SimpleNamespace(loads=lambda text:{'UTC':'Etc/UTC'})}
        definitions('world_clock_control.py',ns,{'WorldClockControl'})
        control=ns['WorldClockControl'].__new__(ns['WorldClockControl'])
        control.closed=Event();control.updating=False;control.dialog=None
        control.service=SimpleNamespace(catalog=SimpleNamespace(version='2026-11-03.2'))
        control.updater=SimpleNamespace(check=check,activate=Mock(return_value=b'old-pointer'),rollback=Mock())
        control.reload=Mock();control.refresh=Mock()
        return control,callbacks,messages,workers

    def finish(self,callbacks,workers):
        for worker in workers:worker.join(timeout=2);self.assertFalse(worker.is_alive())
        callbacks.get(timeout=1)()

    def test_no_update_and_network_or_verification_errors_use_truthful_messages(self):
        for error,expected in ((None,'World clock data are up to date.'),(OSError('offline'),'Could not connect to the update service. No data were changed.'),
                (WorldDataError('invalid signature'),'The update could not be verified. The previous data were retained.')):
            called=[]
            def check(*args):
                called.append(get_ident())
                if error:raise error
                return None
            control,callbacks,messages,workers=self.make(check);main=get_ident()
            control.update();control.update()
            self.finish(callbacks,workers)
            self.assertEqual(1,len(called));self.assertNotEqual(main,called[0])
            self.assertTrue(all(thread==main for thread,_ in messages))
            self.assertEqual(expected,messages[-1][1]);self.assertFalse(control.updating)
            control.updater.activate.assert_not_called()

    def test_late_result_after_shutdown_does_not_announce_or_reload(self):
        entered=Event();release=Event()
        def check(*args):entered.set();release.wait(timeout=1);return None
        control,callbacks,messages,workers=self.make(check)
        control.update();self.assertTrue(entered.wait(timeout=1));control.close();release.set()
        for worker in workers:worker.join(timeout=2);self.assertFalse(worker.is_alive())
        self.assertTrue(callbacks.empty())
        self.assertEqual(1,len(messages));control.reload.assert_not_called()
        control,callbacks,messages,workers=self.make(lambda *args:None)
        control.update()
        for worker in workers:worker.join(timeout=2)
        control.close();callbacks.get(timeout=1)()
        self.assertEqual(1,len(messages));control.reload.assert_not_called()

    def test_reload_failure_after_activation_restores_previous_pointer(self):
        class Target:
            def __truediv__(self,other):return self
            def read_text(self,*args):return '{}'
        control,callbacks,messages,workers=self.make(lambda *args:Target())
        control.reload.side_effect=ValueError('view reload failed')
        control.update();self.finish(callbacks,workers)
        control.updater.rollback.assert_called_once_with(b'old-pointer')
        self.assertEqual('The update could not be verified. The previous data were retained.',messages[-1][1])


if __name__=='__main__':unittest.main()
