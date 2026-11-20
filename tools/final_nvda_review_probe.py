"""Opt-in scratchpad probe for isolated release review; not manual testing."""
import json
from pathlib import Path
import traceback
import globalPluginHandler
import globalVars
import languageHandler
import versionInfo
import wx
import core
import addonHandler


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        self.root = Path(globalVars.appArgs.configPath)
        if not self.root.name.startswith('final5-live-'):
            raise RuntimeError('Isolated final review profile required')
        self.command = json.loads((self.root/'review-command.json').read_text('utf8'))
        self.result = {'phase': self.command['phase'], 'language': languageHandler.getLanguage(),
                       'nvdaVersion': versionInfo.version, 'checks': [], 'passed': False,
                       'scope': 'Real isolated NVDA and official installer APIs; programmatic wx interaction, no physical keys or human listening.'}
        wx.CallLater(4000, self.start)

    def require(self, condition, label):
        if not condition:
            raise AssertionError(label)
        self.result['checks'].append(label)

    def done(self):
        (self.root/('review-'+self.command['phase']+'.json')).write_text(
            json.dumps(self.result, ensure_ascii=False, indent=2)+'\n', 'utf8')
        wx.CallLater(300, core.triggerNVDAExit)

    def start(self):
        try:
            import systemUtils
            self.require(systemUtils._getDesktopName().startswith('AwqatiFinal5_'), 'Private desktop confirmed')
            phase = self.command['phase']
            if phase in ('install4', 'upgrade'):
                if phase == 'upgrade':
                    plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
                    self.require(plugin._runtime is not None, 'Actual 4.0.0 plugin initialized')
                    self.require(addonHandler.getCodeAddon(plugin.__class__).manifest['version'] == '4.0.0', 'Published stable version loaded')
                    draft = plugin._context.settings.open_draft()
                    draft.settings.adhkar.daily_wird.text = 'محفوظ من 4.0.0 — stable reminder'
                    plugin._context.settings.apply(draft)
                    (self.root/'settings-before-upgrade.json').write_bytes((self.root/'awqati/settings.json').read_bytes())
                    old = next(a for a in addonHandler.getAvailableAddons() if a.name == 'awqati')
                    old.requestRemove()
                bundle = addonHandler.AddonBundle(self.command['package'])
                installed = addonHandler.installAddonBundle(bundle)
                self.require(installed is not None and not bundle._installExceptions, 'Official AddonBundle install succeeds')
                self.result['passed'] = True
                self.done()
                return
            self.plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
            self.require(self.plugin._runtime is not None, 'Current packaged plugin initialized after upgrade')
            self.require(addonHandler.getCodeAddon(self.plugin.__class__).manifest['version'] == self.command['version'], 'Candidate manifest version loaded')
            if phase == 'custom-auto':
                dialog = next(w for w in wx.GetTopLevelWindows() if isinstance(w, wx.SingleChoiceDialog))
                self.require(dialog.GetSelection() == 0, 'Affected older settings prompt at startup with no guessed selection')
                dialog.EndModal(wx.ID_CANCEL)
                wx.CallLater(350, self.check_startup_cancel)
                return
            before = json.loads((self.root/'settings-before-upgrade.json').read_text('utf8'))
            after = json.loads((self.root/'awqati/settings.json').read_text('utf8'))
            self.require(before == after, 'All stable settings preserved by NVDA upgrade startup')
            self.require((self.root/'awqati/sentinel.txt').read_text('utf8') == 'preserve synthetic user file', 'Unrelated user data preserved')
            content = self.plugin._content
            from globalPlugins.awqati.domain import CalendarId, ClockType
            lang = self.result['language']
            for identity in CalendarId:
                self.require(bool(content.date_text(identity, lang)), 'Calendar produces localized date: '+identity.value)
            for identity in ClockType:
                self.require(bool(content.clock_text(identity, lang)), 'Clock produces localized time: '+identity.value)
            for name in ('daily_info_text', 'scientific_info_text', 'arabian_short', 'arabian_detailed', 'qibla_text'):
                self.require(bool(getattr(content, name)(lang)), 'Content available: '+name)
            self.require(len(content.daily_prayer_times(lambda t:t).splitlines()) == 9, 'Eight daily prayer and night times produced')
            self.check_custom_method_choice()
            self.plugin._showDailyInfo()
            wx.CallLater(350, self.check_text)
        except Exception:
            self.fail()

    def check_startup_cancel(self):
        try:
            from globalPlugins.awqati.domain import CalculationMethod
            path = self.root/'awqati/settings.json'
            self.require(path.read_bytes() == (self.root/'settings-before-choice.json').read_bytes(), 'Startup cancellation leaves stored bytes unchanged')
            def accept():
                dialog = next(w for w in wx.GetTopLevelWindows() if isinstance(w, wx.SingleChoiceDialog))
                methods = tuple(m for m in CalculationMethod if m is not CalculationMethod.AUTO)
                dialog.SetSelection(methods.index(CalculationMethod.MAKKAH) + 1)
                dialog.EndModal(wx.ID_OK)
            wx.CallLater(200, accept)
            self.plugin._show_custom_method_setup()
            self.require(self.plugin._context.settings.runtime_settings.prayer.calculation_method is CalculationMethod.MAKKAH, 'Startup explicit method saved to runtime')
            self.require(json.loads(path.read_text('utf8')) != json.loads((self.root/'settings-before-choice.json').read_text('utf8')), 'Startup explicit choice saved to disk')
            self.require(bool(self.plugin._content.daily_prayer_times(lambda t:t)), 'Prayer calculation works after startup repair')
            self.result['passed'] = True
            self.done()
        except Exception:
            self.fail()

    def check_custom_method_choice(self):
        from copy import deepcopy
        from globalPlugins.awqati.domain import CalculationMethod
        from globalPlugins.awqati.nvda_adapter.ui import choose_custom_calculation_method
        settings = self.plugin._context.settings.runtime_settings
        settings.prayer.calculation_method = CalculationMethod.AUTO
        before = deepcopy(settings)
        def respond(accept):
            dialog = next(w for w in wx.GetTopLevelWindows() if isinstance(w, wx.SingleChoiceDialog))
            self.require(dialog.GetSelection() == 0, 'Native method dialog has no guessed selection')
            if accept:
                methods = tuple(m for m in CalculationMethod if m is not CalculationMethod.AUTO)
                dialog.SetSelection(methods.index(CalculationMethod.MAKKAH) + 1)
            dialog.EndModal(wx.ID_OK if accept else wx.ID_CANCEL)
        wx.CallLater(200, lambda: respond(False))
        self.require(not choose_custom_calculation_method(None, settings), 'Native method dialog cancellation returns without saving')
        self.require(settings == before, 'Cancellation preserves all settings')
        wx.CallLater(200, lambda: respond(True))
        self.require(choose_custom_calculation_method(None, settings), 'Native method dialog accepts explicit method')
        self.require(settings.prayer.calculation_method is CalculationMethod.MAKKAH, 'Explicit Makkah selection retained')
        draft = self.plugin._context.settings.open_draft()
        draft.settings.prayer.calculation_method = settings.prayer.calculation_method
        self.plugin._context.settings.apply(draft)
        from globalPlugins.awqati.domain import ClockType
        self.require(bool(self.plugin._content.clock_text(ClockType.GHURUBI, self.result['language'])), 'Custom location Ghurubi calculation works after explicit choice')

    def check_text(self):
        try:
            from globalPlugins.awqati.nvda_adapter.text_dialog import SelectableTextDialog
            self.dialog = SelectableTextDialog._instance
            self.require(self.dialog is not None and bool(self.dialog.text.GetValue()), 'Real daily-information text dialog opens')
            self.require(not self.dialog.text.IsEditable(), 'Information text is read-only')
            self.result['dailyInformation'] = self.dialog.text.GetValue()
            self.dialog.Close()
            self.plugin._showStopwatch()
            wx.CallLater(500, self.check_tools)
        except Exception:
            self.fail()

    def check_tools(self):
        try:
            from gui.settingsDialogs import NVDASettingsDialog
            from globalPlugins.awqati.nvda_adapter.time_tools import TOOL_ORDER
            dialogs = [w for w in wx.GetTopLevelWindows() if isinstance(w, NVDASettingsDialog)]
            self.require(len(dialogs) == 1, 'One NVDA settings dialog')
            panel = dialogs[0].currentCategory
            self.require(panel.__class__.__name__ == 'AwqatiSettingsPanel', 'Awqati settings category active')
            self.result['tools'] = []
            for identity in TOOL_ORDER:
                self.plugin._openTimeTool(identity)
                host = panel._time_tools
                self.require(host.state.selected == identity, 'Tool selected: '+identity)
                self.require(host.views[identity].IsShown(), 'Selected tool visible: '+identity)
                self.require(all(not view.IsShown() for key, view in host.views.items() if key != identity), 'Other tool views hidden: '+identity)
                self.result['tools'].append({'identity': identity, 'selectorName': host.choice.GetName(),
                    'children': [{'class': c.__class__.__name__, 'name': c.GetName()} for c in host.views[identity].GetChildren()]})
            from globalPlugins.awqati.domain import CalculationMethod
            before = (self.root/'awqati/settings.json').read_bytes()
            panel._draft.settings.prayer.calculation_method = CalculationMethod.AUTO
            def answer(accept):
                dialog = next(w for w in wx.GetTopLevelWindows() if isinstance(w, wx.SingleChoiceDialog))
                if accept:
                    methods = tuple(m for m in CalculationMethod if m is not CalculationMethod.AUTO)
                    dialog.SetSelection(methods.index(CalculationMethod.MAKKAH) + 1)
                dialog.EndModal(wx.ID_OK if accept else wx.ID_CANCEL)
            wx.CallLater(200, lambda: answer(False))
            self.require(not panel.isValid(), 'Settings Apply cancelled without an explicit method')
            self.require((self.root/'awqati/settings.json').read_bytes() == before, 'Cancelled Apply preserves stored bytes')
            wx.CallLater(200, lambda: answer(True))
            self.require(panel.isValid(), 'Settings validation accepts explicit method')
            panel.onSave()
            self.require(self.plugin._context.settings.runtime_settings.prayer.calculation_method is CalculationMethod.MAKKAH, 'Settings Apply commits chosen method')
            dialogs[0].Close()
            self.result['passed'] = True
            self.done()
        except Exception:
            self.fail()

    def fail(self):
        self.result['error'] = traceback.format_exc()
        self.done()
