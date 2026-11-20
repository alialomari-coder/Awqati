"""Opt-in dev17 scratchpad integration probe for a dedicated test profile.

Installed only by run_multi_press_nvda_probe.py on a private Windows desktop.
Uses real NVDA dispatch, wx, speech and audio; no physical key or listening claim.
"""
import json
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
        if not self.root.name.startswith('dev17-live-'):
            raise RuntimeError('Dedicated dev17 test profile required')
        self.result={'version':versionInfo.version,'language':languageHandler.getLanguage(),
            'scope':'Live NVDA process on private desktop; programmatic InputManager gestures, real wx/synth/audio. No physical keys or human listening.',
            'checks':[],'messages':[],'handlerCalls':[],'passed':False}
        self.original_message=ui.message
        def message(text,*args,**kwargs):
            self.result['messages'].append({'at_ns':time.perf_counter_ns(),'text':text})
            return self.original_message(text,*args,**kwargs)
        ui.message=message
        wx.CallLater(4000,self.start)

    def require(self,condition,label):
        if not condition:raise RuntimeError(label)
        self.result['checks'].append(label)

    def save(self):
        (self.root/'live-result.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

    def start(self):
        try:
            import systemUtils
            self.result['desktop']=systemUtils._getDesktopName()
            self.require(self.result['desktop'].startswith('AwqatiDev17_'),'private desktop confirmed inside NVDA')
            self.result['pluginModules']=[p.__module__ for p in globalPluginHandler.runningPlugins]
            self.plugin=next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
            self.require(not hasattr(self.plugin,'_stopwatch_presses'),'retired scheduler absent in live packaged plugin')
            self.control=self.plugin._stopwatch
            self.require(self.control.watch.state=='idle','isolated stopwatch initially idle')
            self.control.set_mode(2)
            world=self.plugin._world_clock
            for name in ('London','Tokyo','Cairo'):
                world.service.add(world.service.catalog.search(name)[0])
            self.network_calls=[]
            self.original_verify=self.plugin._actions.verify_online
            self.plugin._actions.verify_online=lambda **kw:self.network_calls.append(kw)
            self.frame=wx.Frame(None,title='Awqati dev17 isolated integration')
            self.text=wx.TextCtrl(self.frame,name='Awqati test focus')
            self.frame.Show();self.text.SetFocus()
            self.steps=[
                ('NVDA+j','running',0),('NVDA+j','running',0),
                ('NVDA+windows+j','running',0),('NVDA+windows+j','running',0),
                ('NVDA+shift+j','running',1),('NVDA+shift+j','running',1),
                ('NVDA+windows+shift+j','running',1),('NVDA+windows+shift+j','running',1),
                ('NVDA+control+f12','running',1),('NVDA+control+f12','running',1),
                ('NVDA+control+f12','running',1),('NVDA+control+f12','running',1),
                ('NVDA+j','paused',1),('NVDA+alt+p','paused',1),
            ]
            self.index=0
            wx.CallLater(150,self.step)
        except Exception:self.fail()

    def step(self):
        try:
            if self.index==len(self.steps):
                from globalPlugins.awqati.nvda_adapter.text_dialog import SelectableTextDialog
                dialog=SelectableTextDialog._instance
                self.require(dialog is not None and bool(dialog.text.GetValue()),'live localized prayer-times window has selectable text')
                self.require(not self.network_calls,'Alt+P opened local times without verification')
                dialog.Close()
                self.require(len(self.result['messages'])>=8,'real NVDA message submissions recorded')
                self.plugin._actions.verify_online=self.original_verify
                self.check_pages()
                return
            key,state,laps=self.steps[self.index]
            # Native event construction avoids fromName's character lookup,
            # which cannot map Latin 'j' through an Arabic input HKL.
            parts=key.lower().split('+')
            modifiers={(0x2D,True)}
            codes={'windows':0x5B,'shift':0x10,'control':0x11,'alt':0x12}
            for part in parts[1:-1]:modifiers.add((codes[part],False))
            code,scan={'j':(0x4A,0x24),'f12':(0x7B,0x58),'p':(0x50,0x19)}[parts[-1]]
            gesture=keyboardHandler.KeyboardInputGesture(modifiers,code,scan,False)
            script=gesture.script
            self.require(script is not None and getattr(script,'__self__',None) is self.plugin,'live binding '+key)
            before=time.perf_counter_ns()
            inputCore.manager.executeGesture(gesture)
            self.result['handlerCalls'].append({'gesture':key,'queued_at_ns':before})
            wx.CallLater(120,lambda:self.after_step(state,laps))
        except Exception:self.fail()

    def after_step(self,state,laps):
        try:
            self.require(self.control.watch.state==state,f'step {self.index} state {state} before multi-press timeout')
            self.require(len(self.control.watch.laps)==laps,f'step {self.index} lap count {laps}')
            self.index+=1
            self.step()
        except Exception:self.fail()

    def check_pages(self):
        try:
            self.plugin._showStopwatch()
            wx.CallLater(500,self.after_pages)
        except Exception:self.fail()

    def after_pages(self):
        try:
            from gui.settingsDialogs import NVDASettingsDialog
            dialogs=[w for w in wx.GetTopLevelWindows() if isinstance(w,NVDASettingsDialog)]
            self.require(len(dialogs)==1,'one real NVDA settings window reused')
            panel=dialogs[0].currentCategory
            self.require(panel.__class__.__name__=='AwqatiSettingsPanel','Awqati category selected')
            from globalPlugins.awqati.nvda_adapter.time_tools import TOOL_ORDER
            for value in TOOL_ORDER:
                self.plugin._openTimeTool(value)
                self.require(self.plugin._context.time_tools.selected==value,'embedded page '+value)
            dialogs[0].Close()
            self.frame.Destroy()
            self.result['passed']=True;self.save();ui.message=self.original_message
            wx.CallLater(300,core.triggerNVDAExit)
        except Exception:self.fail()

    def fail(self):
        self.result['error']=traceback.format_exc();self.save()
        ui.message=self.original_message
        wx.CallLater(300,core.triggerNVDAExit)
