"""Task 3.2: real NVDA/wx/MSAA, synthetic gestures and isolated clock/location.

No physical-key or human-auditory acceptance claim. Clipboard is tested by a
separate worker on its own window station, never the interactive clipboard.
"""
import importlib
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
import core
import inputCore
import keyboardHandler
import scriptHandler
import ui
import wx
import globalPluginHandler

# Reuse only the existing private-profile guard, error recording and MSAA helper.
import globalVars
ROOT = Path((Path(globalVars.appArgs.configPath)/'source-root.txt').read_text('utf-8'))
sys.path.insert(0, str(ROOT/'tools'))
from converter_integration_nvda_probe import GlobalPlugin as BaseProbe


class GlobalPlugin(BaseProbe):
    def begin(self):
        import systemUtils
        self.require(systemUtils._getDesktopName().startswith('AwqatiTask3_'), 'private desktop verified')
        self.plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
        self.prefix = self.plugin.__module__.rsplit('.nvda_adapter.', 1)[0]
        self.dialogs = importlib.import_module(self.prefix+'.nvda_adapter.text_dialog').SelectableTextDialog
        self.domain = importlib.import_module(self.prefix+'.domain')
        self.result['scope'] = 'Real NVDA InputManager, speech submission, wx and MSAA; programmatic gestures/navigation; no physical keys or human listening'
        self.messages = []
        self.original_message = ui.message
        def message(text, *args, **kwargs):
            self.messages.append(text)
            return self.original_message(text, *args, **kwargs)
        ui.message = message
        self.content = self.plugin._content
        self.language = self.plugin._language()
        self.prayer_before = self.content.daily_prayer_times(lambda s:s)
        self.date_before = self.content.primary_date(self.language)
        self.alert_before = self.content.alert_status(lambda s:s)
        self.settings = self.content._settings()
        self.saved_settings_provider = self.content._settings
        self.content._settings = lambda: self.settings
        self.saved_include = self.settings.calendar.include_arabian_calendar_in_daily_info
        self.saved_location = self.settings.location
        class Clock:
            def now(inner):
                return self.domain.Instant(inner.value)
        self.clock = Clock()
        self.clock.value = datetime(2026, 11, 19, 9, tzinfo=timezone.utc)
        self.astronomy = self.content.daily_info._astronomy
        self.heritage = self.content.daily_info._arabian_calendar
        self.saved_clocks = (self.astronomy._clock, self.heritage._clock)
        self.astronomy._clock = self.heritage._clock = self.clock
        self.settings.location = self.domain.StoredLocation(self.domain.LocationKind.CUSTOM,
            self.domain.Location('fixture', 'Riyadh fixture',24.7136,46.6753,'Asia/Riyadh'))
        self.frame = wx.Frame(None, title='Task 3.2 isolated synopsis test')
        self.opener = wx.Button(self.frame, label='Return focus here')
        self.frame.Show()
        self.opener.SetFocus()
        self.flow = self.scenarios()
        self.advance()

    def send(self, key):
        gesture = keyboardHandler.KeyboardInputGesture.fromName(key)
        wanted = self.plugin.script_dailyInformation if key == 'NVDA+control+h' else self.plugin.script_timeDateInfo
        self.require(scriptHandler.findScript(gesture) == wanted, 'unchanged binding '+key)
        inputCore.manager.executeGesture(gesture)

    def presses(self, key, count):
        scriptHandler.clearLastScript()
        start = len(self.messages)
        for _ in range(count):
            self.send(key)
            yield 80
        yield 650
        self.result['timings'].append(dict(key=key,count=count,messages=len(self.messages)-start))

    def scenarios(self):
        yield 250
        start = time.perf_counter()
        scientific = self.content.scientific_info_text(self.language)
        self.result['coldCalculationMs'] = (time.perf_counter()-start)*1000
        expected = (ROOT/'docs/daily_synopsis_task31/final_editorial'/('approved_ar.txt' if self.language=='ar' else 'scientific_en.txt')).read_text('utf-8')
        self.require(scientific.split() == expected.split(), 'approved language baseline and five paragraphs')
        self.require(len(scientific.splitlines()) == 5, 'approved paragraph order')
        # Timer jitter while executing the unchanged synchronous command path.
        ticks = []
        last = [time.perf_counter()]
        def tick():
            now = time.perf_counter()
            ticks.append((now-last[0])*1000)
            last[0] = now
        self.timer = wx.Timer(self.frame)
        self.frame.Bind(wx.EVT_TIMER, lambda e:tick(), self.timer)
        self.timer.Start(20)
        yield from self.presses('NVDA+control+h', 1)
        self.require(self.messages[-1] == scientific, 'single press submits exact scientific text to real NVDA speech')
        yield from self.presses('NVDA+control+h', 2)
        self.require(self.messages[-1] == self.content.arabian_detailed(self.language), 'double press retains independent heritage command')
        for include in (False, True):
            self.settings.calendar.include_arabian_calendar_in_daily_info = include
            expected_window = self.content.daily_info_text(self.language)
            self.require(expected_window.startswith(scientific), 'heritage switch preserves scientific paragraphs')
            self.require((len(expected_window)>len(scientific)) == include, 'heritage included only when enabled')
            start = len(self.messages)
            yield from self.presses('NVDA+control+h', 3)
            self.require(self.messages[start:] == [scientific,self.content.arabian_detailed(self.language)], 'triple press retains approved immediate single then double then window sequence')
            d = self.dialogs._instance
            self.require(d is not None and wx.Window.FindFocus() is d.text, 'window opens with text focus')
            self.require(d.text.GetValue() == expected_window, 'window text equals combined spoken content')
            obj = self.obj(d.text)
            self.require(obj.role.name == 'EDITABLETEXT' and bool(obj.name), 'real named MSAA editable text')
            self.require(obj.value.replace('\r\n','\n') == expected_window, 'NVDA accessible value exposes complete text')
            self.require(not d.text.IsEditable(), 'report read only')
            d.text.SetSelection(-1,-1)
            self.require(d.text.GetStringSelection() == expected_window, 'all report text selectable')
            d.text.SetInsertionPoint(0)
            self.require(d.text.GetInsertionPoint() == 0, 'caret can return to start')
            d.text.SetInsertionPointEnd()
            self.require(d.text.GetInsertionPoint() == d.text.GetLastPosition(), 'caret can reach end')
            d.text.Navigate()
            close = wx.Window.FindFocus()
            self.require(isinstance(close,wx.Button) and close.GetId()==wx.ID_CLOSE, 'Tab reaches named Close button')
            self.require(bool(self.obj(close).name), 'Close button actual accessible name')
            close.Navigate(wx.NavigationKeyEvent.IsBackward)
            self.require(wx.Window.FindFocus() is d.text, 'Shift Tab returns to text')
            event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
            event.SetKeyCode(wx.WXK_ESCAPE)
            d.GetEventHandler().ProcessEvent(event)
            yield 250
            self.require(self.dialogs._instance is None, 'Escape handler closes report')
            self.require(wx.Window.FindFocus() is self.opener, 'focus restored to opener after close')
            yield from self.presses('NVDA+f12',3)
            self.require(self.messages[-1] == expected_window, 'existing F12 triple press speaks exact window text')
        self.timer.Stop()
        self.result['heartbeat'] = dict(samples=len(ticks),maximumGapMs=max(ticks), targetIntervalMs=20)
        self.require(len(ticks)>20 and max(ticks)<500, 'warm commands maintain heartbeat below 500ms')
        warm=[]
        for _ in range(10):
            start=time.perf_counter(); self.content.scientific_info_text(self.language)
            warm.append((time.perf_counter()-start)*1000)
        self.result['warmCalculationMs']=warm
        a=self.content.daily_info.read(self.content._location()).scientific
        self.clock.value=datetime(2026,11,19,18,tzinfo=timezone.utc)
        b=self.content.daily_info.read(self.content._location()).scientific
        self.require(a.daily_details.sun_distance != b.daily_details.sun_distance and a.daily_details.lunar_distance != b.daily_details.lunar_distance and a.lunar != b.lunar, 'instant Sun Moon distance and phase refresh on same civil day')
        self.require(a.daily_details.horizon is b.daily_details.horizon, 'daily event cache reused independently of instant data')
        self.result['exceptionalCases']=[]
        for label,lat,lon,zone,when in (
            ('polar night',78.2232,15.6,'Arctic/Longyearbyen',(2026,12,21,9)),
            ('geographic pole',90,15.6,'Arctic/Longyearbyen',(2026,6,21,9)),
            ('southern season',-33.8688,151.2093,'Australia/Sydney',(2026,11,19,9)),
            ('DST fold',51.5,0,'Europe/London',(2026,10,25,1)),
            ('year boundary',1.87,-157.4,'Pacific/Kiritimati',(2026,12,31,12))):
            self.clock.value=datetime(*when,tzinfo=timezone.utc)
            self.settings.location=self.domain.StoredLocation(self.domain.LocationKind.CUSTOM,
                self.domain.Location(label,label,lat,lon,zone))
            start=time.perf_counter()
            text=self.content.scientific_info_text(self.language)
            self.result['exceptionalCases'].append(dict(case=label,ms=(time.perf_counter()-start)*1000,text=text))
            self.require(text and 'None' not in text and 'nan' not in text, 'real NVDA exceptional rendering '+label)
            yield 40
        self.astronomy._clock,self.heritage._clock=self.saved_clocks
        self.settings.location=self.saved_location
        self.settings.calendar.include_arabian_calendar_in_daily_info=self.saved_include
        self.content._settings=self.saved_settings_provider
        self.require(self.content.daily_prayer_times(lambda s:s)==self.prayer_before, 'prayer times unchanged after synopsis')
        self.require(self.content.primary_date(self.language)==self.date_before, 'calendar unchanged after synopsis')
        self.require(self.content.alert_status(lambda s:s)==self.alert_before, 'alert state unchanged after synopsis')

    def finish(self):
        if hasattr(self,'timer'): self.timer.Stop()
        if hasattr(self,'saved_clocks'):
            self.astronomy._clock,self.heritage._clock=self.saved_clocks
            self.settings.location=self.saved_location
            self.settings.calendar.include_arabian_calendar_in_daily_info=self.saved_include
        if hasattr(self,'saved_settings_provider'): self.content._settings=self.saved_settings_provider
        if hasattr(self,'original_message'): ui.message=self.original_message
        if hasattr(self,'dialogs') and self.dialogs._instance: self.dialogs._instance.Close()
        if self.frame: self.frame.Destroy()
        (self.profile/'live-result.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2),'utf-8')
        wx.CallLater(300,core.triggerNVDAExit)
