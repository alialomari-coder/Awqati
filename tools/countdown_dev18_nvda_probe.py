"""Opt-in packaged dev18 tests inside an isolated NVDA profile and desktop.

Programmatic input dispatch and real wx/synth/audio, not physical key testing.
"""
import ctypes
from ctypes import wintypes
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import time
import traceback
import globalPluginHandler
import globalVars
import languageHandler
import versionInfo
import wx
import ui
import core
import keyboardHandler
import inputCore


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        self.root=Path(globalVars.appArgs.configPath)
        if not self.root.name.startswith('dev18-live-'):
            raise RuntimeError('Dedicated dev18 profile required')
        self.result={'version':versionInfo.version,'language':languageHandler.getLanguage(),
            'scope':'Private desktop, synthetic InputManager events, real wx/synth/audio; no physical keys or human listening.',
            'checks':[],'messages':[],'handlerCalls':[],'passed':False}
        self.original_message=ui.message
        def message(text,*args,**kwargs):
            self.result['messages'].append({'at_ns':time.perf_counter_ns(),'text':text})
            return self.original_message(text,*args,**kwargs)
        ui.message=message
        wx.CallLater(4000,self.start)

    def require(self, condition, label):
        if not condition:raise RuntimeError(label)
        self.result['checks'].append(label)

    def save(self):
        (self.root/'live-result.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

    def start(self):
        try:
            import systemUtils
            self.require(systemUtils._getDesktopName().startswith('AwqatiDev18_'),'private desktop confirmed inside NVDA')
            self.plugin=next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
            self.control=self.plugin._countdowns
            self.custom_hash=hashlib.sha256((self.root/'gestures.ini').read_bytes()).hexdigest()
            custom=keyboardHandler.KeyboardInputGesture({(0x2D,True),(0x11,False),(0x12,False)},0x59,0x15,False)
            self.require(custom.script is not None and custom.script.__name__=='script_countdownSelected','saved custom timer shortcut remains active')
            from globalPlugins.awqati.domain.countdown import Countdown
            self.first=Countdown.create('Reading',600,ticking=True)
            self.second=Countdown.create('Other',1200)
            self.control.service.put(self.first);self.control.service.put(self.second)
            self.control.selected=self.first.timer_id
            self.frame=wx.Frame(None,title='Awqati dev18 isolated timer tests')
            self.text=wx.TextCtrl(self.frame,name='Timer test focus');self.frame.Show();self.text.SetFocus()
            # Use each real Windows input layout on the NVDA test thread only.
            self.user32=ctypes.WinDLL('user32',use_last_error=True)
            self.user32.LoadKeyboardLayoutW.argtypes=[wintypes.LPCWSTR,wintypes.UINT]
            self.user32.LoadKeyboardLayoutW.restype=wintypes.HKL
            self.user32.ActivateKeyboardLayout.argtypes=[wintypes.HKL,wintypes.UINT]
            self.user32.ActivateKeyboardLayout.restype=wintypes.HKL
            self.layouts=['00000409','00000401'];self.layout_index=0
            self.run_layout()
        except Exception:self.fail()

    def run_layout(self):
        try:
            if self.layout_index==len(self.layouts):
                self.finish();return
            hkl=self.user32.LoadKeyboardLayoutW(self.layouts[self.layout_index],0x80)
            self.require(bool(hkl),'load keyboard layout '+self.layouts[self.layout_index])
            self.user32.ActivateKeyboardLayout(hkl,0)
            self.result['inputLayout']=self.layouts[self.layout_index]
            self.control.service.put(self.second)
            self.control.selected=self.first.timer_id
            # Reset only test data, and leave enough time to test native repeats.
            self.control.service.transition(self.first.timer_id,'restart',confirmed=True)
            self.steps=[
                ('NVDA+y',self.check_single),('NVDA+y',self.check_double),
                ('NVDA+windows+y',lambda:self.check_selected(self.second.timer_id)),
                ('NVDA+windows+shift+y',lambda:self.check_selected(self.first.timer_id)),
                ('NVDA+shift+y',lambda:self.check_state('paused')),
                ('NVDA+control+shift+y',self.check_restart_declined),
                ('NVDA+control+shift+y',self.check_restart_accepted),
                ('NVDA+alt+y',self.check_window),
                ('NVDA+control+y',self.check_no_ring),
                ('NVDA+control+y',self.check_silenced),
            ]
            self.index=0;wx.CallLater(650,self.step)
        except Exception:self.fail()

    def step(self):
        try:
            if self.index==len(self.steps):
                self.layout_index+=1;self.run_layout();return
            key,self.after=self.steps[self.index]
            if self.index==5:
                self.original_box=wx.MessageBox;self.prompts=[]
                wx.MessageBox=lambda *a,**kw:self.prompts.append(a) or wx.NO
            if self.index==6:
                wx.MessageBox=lambda *a,**kw:self.prompts.append(a) or wx.YES
            if self.index==9:self.prepare_ring()
            modifiers={(0x2D,True)}
            for part in key.lower().split('+')[1:-1]:
                modifiers.add(({'shift':0x10,'control':0x11,'alt':0x12,'windows':0x5B}[part],False))
            gesture=keyboardHandler.KeyboardInputGesture(modifiers,0x59,0x15,False)
            self.require(gesture.script is not None and gesture.script.__self__ is self.plugin,'live timer binding '+key)
            self.message_count=len(self.result['messages'])
            inputCore.manager.executeGesture(gesture)
            self.result['handlerCalls'].append({'key':key,'layout':self.layouts[self.layout_index]})
            # Only the query pair is within NVDA's native repeat interval.
            wx.CallLater(120,self.after_step)
        except Exception:self.fail()

    def after_step(self):
        try:
            self.after();self.index+=1
            wx.CallLater(10 if self.index==1 else 650,self.step)
        except Exception:self.fail()

    def check_single(self):
        self.require(len(self.result['messages'])==self.message_count+1,'first query immediately submits one message')
        self.require('Reading' in self.result['messages'][-1]['text'],'first query names selection')

    def check_double(self):
        text=self.result['messages'][-1]['text']
        self.require('Reading' in text and '2' in text,'native second press reports selection state and total two timers')

    def check_selected(self, identity):
        self.require(self.control.selected==identity,'navigation selects intended timer')
        self.require(self.control.service.rows[self.first.timer_id]['state']=='running','navigation preserves running state')
        self.require(self.control.service.rows[self.second.timer_id]['state']=='ready','navigation preserves other state')

    def check_state(self,state):
        self.require(self.control.service.rows[self.first.timer_id]['state']==state,'toggle state '+state)

    def check_restart_declined(self):
        self.require(len(self.prompts)==1,'restart displayed confirmation')
        self.check_state('paused')

    def check_restart_accepted(self):
        self.require(len(self.prompts)==2,'second restart displayed confirmation')
        self.check_state('running')
        self.require(self.control.service.remaining(self.first.timer_id)>599*10**9,'accepted restart uses original duration')
        wx.MessageBox=self.original_box

    def check_window(self):
        self.require(self.control.dialog is not None,'Alt Y opens embedded timer view')
        panel=self.control.dialog
        self.require(panel.list.GetName() in ('Timers list','قائمة المؤقتات'),'native list has localized accessible name')
        from gui.settingsDialogs import NVDASettingsDialog
        for window in wx.GetTopLevelWindows():
            if isinstance(window,NVDASettingsDialog):window.Close()
        self.require(self.control.selected==self.first.timer_id,'closing settings retains selected timer')
        mappings=inputCore.manager.getAllGestureMappings()
        names={info.scriptName for category in mappings.values() for info in category.values()}
        self.require({'countdownSelected','countdownToggle','countdownWindow','countdownStopAlert',
            'countdownRestart','countdownNext','countdownPrevious'}<=names,'all seven commands appear in Input Gestures mappings')

    def check_no_ring(self):
        text=self.result['messages'][-1]['text']
        self.require(text==('لا يوجد رنين حاليًا' if self.result['language'].startswith('ar') else 'There is no ringing timer currently.'),'localized no-ring response')

    def prepare_ring(self):
        from globalPlugins.awqati.domain import AlertAction
        runtime=self.control.runtime
        draft=runtime.settings.open_draft()
        draft.settings.general.all_automatic_alerts_enabled=True
        draft.settings.prayer.alerts_enabled=False
        draft.settings.adhkar.alerts_enabled=False
        draft.settings.clock.automatic_alert_enabled=False
        runtime.settings.apply(draft)
        timer=replace(self.second,duration=1,action=AlertAction.SOUND)
        self.control.service.put(timer);self.control.service.transition(timer.timer_id,'start')
        # Advance just this synthetic timer's deadline; use the real presenter.
        self.control.service.rows[timer.timer_id]['deadline']=self.control.service.clock()-10**9
        self.control.tick()
        # The scheduler uses civil instants. Re-read now after the synchronous
        # poll/atomic write so a newly queued event is due even on a clock tick.
        runtime.presenter.present_next()
        self.result.setdefault('ringDiagnostics',[]).append({
            'state':dict(self.control.service.rows[timer.timer_id]),
            'scopeEnabled':runtime.scheduler.scope_enabled('timers.'+timer.timer_id),
            'current':str(runtime.presenter.current),
            'queued':[str(e) for e in runtime.scheduler.waiting],
        })
        self.require(runtime.presenter.current is not None,'real timer audio presentation active')
        self.require(self.control.selected==self.first.timer_id,'ringing timer is not selected')

    def check_silenced(self):
        self.require(self.control.runtime.presenter.current is None,'Ctrl Y silences current presentation')
        self.require('Other' in self.result['messages'][-1]['text'],'silence announces unselected ringing name')
        self.require(self.control.selected==self.first.timer_id,'silence retains selection')

    def finish(self):
        self.require(self.custom_hash==hashlib.sha256((self.root/'gestures.ini').read_bytes()).hexdigest(),'saved custom gestures file unchanged')
        self.frame.Destroy();self.result['passed']=True;self.save();ui.message=self.original_message
        wx.CallLater(300,core.triggerNVDAExit)

    def fail(self):
        self.result['error']=traceback.format_exc();self.save();ui.message=self.original_message
        if hasattr(self,'original_box'):wx.MessageBox=self.original_box
        wx.CallLater(300,core.triggerNVDAExit)
