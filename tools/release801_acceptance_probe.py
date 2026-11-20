"""Verify installed 8.0.1 bytes, real upgrade, weather UI and core integration."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import addonHandler
import globalVars
import wx

PROFILE = Path(globalVars.appArgs.configPath)
ROOT = Path((PROFILE / 'source-root.txt').read_text('utf-8'))
sys.path.insert(0, str(ROOT / 'tools'))
from weather_801_nvda_probe import GlobalPlugin as WeatherProbe
from release71_install_probe import settings_snapshot


class GlobalPlugin(WeatherProbe):
    def require(self, value, label):
        (self.profile / 'probe-progress.json').write_text(json.dumps(dict(label=label, value=bool(value)), ensure_ascii=False), 'utf-8')
        return super().require(value, label)

    def begin(self):
        addon = next(a for a in addonHandler.getAvailableAddons() if a.name == 'awqati')
        self.require(addon.manifest['version'] == '8.0.1' and addon.isRunning,
                     'installed 8.0.1 running after real NVDA restart')
        self.require(not addon.isPendingInstall and not addon.isPendingRemove, 'installation committed')
        inventory = json.loads((self.profile / 'package-inventory.json').read_text('utf-8'))
        self.require(all(hashlib.sha256((Path(addon.path) / name).read_bytes()).hexdigest() == sha
                         for name, sha in inventory.items()), 'every installed file matches built artifact')
        self.result['installedFilesVerified'] = len(inventory)
        super().begin()
        module = importlib.import_module(self.plugin.__module__)
        self.require(Path(module.__file__).resolve().is_relative_to(Path(addon.path).resolve()),
                     'plugin loaded from installed bundle and not development source')
        current = json.loads(settings_snapshot(self.plugin._context.settings.runtime_settings))
        self.require(current['schema_version'] == 2 and not current['weather']['enabled'],
                     'schema one migrated to schema two with weather disabled by default')
        old = self.profile / 'old-runtime-settings.json'
        if old.exists():
            previous = json.loads(old.read_text('utf-8'))
            previous['weather']['current'].setdefault('apparent_temperature', True)
            self.require(current == previous, 'all 8.0.0 runtime settings preserved after actual upgrade')
        for attr in ('_converter', '_stopwatch', '_countdowns', '_world_clock', '_on_this_day'):
            self.require(getattr(self.plugin, attr) is not None, 'existing service initialized ' + attr)

    def scenarios(self):
        yield from super().scenarios()
        # Test real modal OK/Cancel handlers using real wx controls and events.
        from copy import deepcopy
        settings = self.settings_module.WeatherSettings(enabled=True, unit_system='custom')
        panel = self.ui_module.WeatherSettingsPanel(self.frame, settings,
                    lambda: self.weather.settings.runtime_settings.location, self.weather)
        panel.Show()
        widgets = [panel.enabled, *panel.dependent, panel.custom_units]
        for control in widgets:
            obj = self.obj(control)
            self.require(bool(obj.name), 'weather setting has accessible name and role ' + obj.role.name)
        panel.enabled.SetFocus()
        visited = []
        for _ in range(len(widgets) + 4):
            focused = wx.Window.FindFocus()
            visited.append(focused.GetId())
            focused.Navigate()
        self.require(all(control.GetId() in visited for control in widgets), 'Tab reaches all enabled weather settings')
        panel.enabled.SetFocus()
        reverse = []
        for _ in range(len(widgets) + 4):
            focused = wx.Window.FindFocus(); reverse.append(focused.GetId())
            focused.Navigate(wx.NavigationKeyEvent.IsBackward)
        self.require(all(control.GetId() in reverse for control in widgets), 'Shift Tab reaches all enabled weather settings')
        for kind, action in (('information', panel.information), ('units', panel.units)):
            before = deepcopy(settings)
            for accept in (False, True):
                observed = []
                def edit():
                    expected = self.ui_module.InformationDialog if kind == 'information' else self.ui_module.UnitsDialog
                    dialog = next(d for d in wx.GetTopLevelWindows() if isinstance(d, expected) and d.IsModal())
                    self.require(isinstance(dialog, expected), 'actual modal opens ' + kind)
                    if kind == 'information':
                        check = next(w for w in dialog.pages['current'].GetChildren() if isinstance(w, wx.CheckBox))
                        check.SetValue(not check.GetValue())
                        check.ProcessEvent(wx.CommandEvent(wx.wxEVT_CHECKBOX, check.GetId()))
                    else:
                        choice = next(w for w in dialog.GetChildren() if isinstance(w, wx.Choice))
                        choice.SetSelection((choice.GetSelection() + 1) % choice.GetCount())
                        choice.ProcessEvent(wx.CommandEvent(wx.wxEVT_CHOICE, choice.GetId()))
                    # Real default dialog button processing closes the modal loop.
                    button = dialog.FindWindowById(wx.ID_OK if accept else wx.ID_CANCEL)
                    self.require(bool(self.obj(button).name), 'modal button accessible ' + kind)
                    event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
                    event.SetEventObject(button)
                    button.Command(event)
                    observed.append(True)
                errors = []
                def guarded_edit():
                    try:
                        edit()
                    except Exception:
                        import traceback
                        errors.append(traceback.format_exc())
                        for dialog in wx.GetTopLevelWindows():
                            if isinstance(dialog, wx.Dialog) and dialog.IsModal(): dialog.EndModal(wx.ID_CANCEL)
                wx.CallLater(100, guarded_edit)
                action(None)
                self.require(not errors, 'modal callback succeeded ' + str(errors))
                self.require(bool(observed), 'modal returned after button ' + kind)
                self.require((settings != before) if accept else (settings == before),
                             ('OK saves draft ' if accept else 'Cancel preserves draft ') + kind)
        panel.Destroy()
        persisted = json.loads((self.profile / 'awqati/settings.json').read_text('utf-8'))
        original = json.loads((self.profile / 'original-settings.json').read_text('utf-8'))
        self.require(persisted['schemaVersion'] == 2, 'first settings write persists migrated schema')
        persisted.pop('weather'); original.pop('weather')
        self.require(persisted == original, 'all previous persisted settings preserved after applying weather settings')
        self.require(not (self.profile / 'awqati/settings.json.schema1.bak').exists(),
                     'schema two upgrade does not create a schema one backup')
