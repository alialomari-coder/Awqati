"""Opt-in scratchpad probe, only in the runner's private dev22 profiles.

Real NVDA process, InputManager, wx and synth; no physical-key/listening claim.
"""
import json
from pathlib import Path
import traceback
import core
import globalPluginHandler
import globalVars
import inputCore
import keyboardHandler
import languageHandler
import speech
import versionInfo
import wx


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        self.root = Path(globalVars.appArgs.configPath)
        if not self.root.name.startswith('dev22-live-'):
            raise RuntimeError('Dedicated test profile required')
        self.result = dict(version=versionInfo.version, language=languageHandler.getLanguage(),
            scope='Private desktop; programmatic real InputManager gestures, real wx and speech synth; no physical keys or listening, no browser Browse Mode claim.',
            checks=[], spokenSections=[], opened=[], passed=False)
        wx.CallLater(3500, self.start)

    def require(self, condition, label):
        if not condition:
            raise RuntimeError(label)
        self.result['checks'].append(label)

    def guarded(self, callback):
        try:
            callback()
        except Exception:
            self.result['error'] = traceback.format_exc()
            self.finish()

    def start(self):
        self.guarded(self.begin)

    def begin(self):
        import systemUtils
        self.require(systemUtils._getDesktopName().startswith('AwqatiDev22_'), 'private desktop confirmed')
        self.plugin = next(p for p in globalPluginHandler.runningPlugins
                           if p.__module__.endswith('awqati.nvda_adapter.plugin'))
        self.presenter = self.plugin._on_this_day
        self.require(self.presenter is not None, 'packaged service composed')
        self.fetches = []
        def forbid_fetch(*args):
            self.fetches.append(1)
            raise RuntimeError('Cache must be reused offline')
        self.presenter.service.provider.fetch = forbid_fetch
        self.original_speak = self.presenter.speak
        def record_speech(lines):
            self.result['spokenSections'].append(lines[0])
            self.require(len(lines) > 1, 'complete section submitted to speech')
            self.require(not any('https://' in line for line in lines), 'no URLs in submitted narration')
            self.original_speak(lines)
        self.presenter.speak = record_speech
        self.frame = wx.Frame(None, title='Awqati On This Day isolated integration')
        self.text = wx.TextCtrl(self.frame, name='Test focus')
        self.frame.Show()
        self.text.SetFocus()
        self.index = 0
        self.press_series(self.direct_done)

    def gesture(self):
        return keyboardHandler.KeyboardInputGesture({(0x2D, True), (0x5B, False)}, 0x7B, 0x58, False)

    def press_series(self, done):
        gesture = self.gesture()
        self.require(gesture.script is not None and gesture.script.__self__ is self.plugin
                     and gesture.script.__name__ == 'script_onThisDay', 'native default gesture resolves to new command')
        inputCore.manager.executeGesture(gesture)
        self.index += 1
        if self.index < 4:
            wx.CallLater(180, lambda: self.guarded(lambda: self.press_series(done)))
        else:
            wx.CallLater(1000, lambda: self.guarded(done))

    def direct_done(self):
        self.require(len(self.result['spokenSections']) == 4, 'all four immediate narration selections reached real speech')
        speech.cancelSpeech()
        self.require(not self.original_speak.__self__.busy, 'real speech cancellation clears ownership; no continuation timer')
        self.require(not self.fetches, 'saved daily cache works without network')
        draft = self.plugin._context.settings.open_draft()
        draft.settings.calendar.on_this_day_web_page = True
        self.plugin._context.settings.apply(draft)
        from globalPlugins.awqati.infrastructure.settings_repository import JsonSettingsRepository
        self.require(JsonSettingsRepository(self.root / 'awqati/settings.json').load().calendar.on_this_day_web_page,
                     'web preference saved and restored through real repository')
        from globalPlugins.awqati.infrastructure.on_this_day_pages import LocalDayPages
        self.presenter.open_page = LocalDayPages(self.root / 'awqati/on_this_day_pages',
            lambda path: self.result['opened'].append(path)).open
        self.index = 0
        self.press_series(self.web_done)

    def web_done(self):
        self.require(len(self.result['opened']) == 1, 'rapid four web presses open exactly one file')
        path = Path(self.result['opened'][0])
        self.require(path.name.endswith('-observances.html'), 'fourth section wins with warm daily cache')
        self.require('dir="rtl"' in path.read_text('utf8') if languageHandler.getLanguage().startswith('ar')
                     else 'dir="ltr"' in path.read_text('utf8'), 'local HTML uses selected language direction')
        self.require(not self.fetches, 'both output modes reuse saved data')
        self.plugin._showStopwatch()  # open the existing NVDA settings shell
        wx.CallLater(500, lambda: self.guarded(self.settings_done))

    def settings_done(self):
        from gui.settingsDialogs import NVDASettingsDialog
        dialogs = [w for w in wx.GetTopLevelWindows() if isinstance(w, NVDASettingsDialog)]
        self.require(len(dialogs) == 1, 'real NVDA settings dialog opens')
        panel = dialogs[0].currentCategory
        # Explicitly build Date's native controls in the live settings panel.
        date_panel = panel._build_date()
        boxes = [w for w in date_panel.GetChildren() if isinstance(w, wx.CheckBox)
                 and ('حدث في مثل' in w.GetLabel() or 'On This Day' in w.GetLabel())]
        self.require(len(boxes) == 1 and boxes[0].GetValue(), 'native labeled checkbox reflects saved preference')
        self.result['checkboxLabel'] = boxes[0].GetLabel()
        date_panel.Destroy()
        dialogs[0].Close()
        self.frame.Destroy()
        self.presenter.close()
        self.require(self.presenter.closed, 'service and timers close safely')
        self.result['passed'] = True
        self.finish()

    def finish(self):
        (self.root / 'live-result.json').write_text(json.dumps(self.result, ensure_ascii=False, indent=2), encoding='utf8')
        wx.CallLater(300, core.triggerNVDAExit)
