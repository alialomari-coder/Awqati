"""Actual NVDA weather integration on an owned private desktop, using synthetic data."""
import importlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
import core
import globalVars
import globalPluginHandler
import inputCore
import keyboardHandler
import scriptHandler
import wx

ROOT = Path((Path(globalVars.appArgs.configPath) / "source-root.txt").read_text("utf-8"))
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests")]
from converter_integration_nvda_probe import GlobalPlugin as BaseProbe
from support.weather_fixtures import fixture


class GlobalPlugin(BaseProbe):
    def begin(self):
        import systemUtils
        self.require(systemUtils._getDesktopName().startswith("AwqatiTask3_"), "private desktop verified")
        self.plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith("awqati.nvda_adapter.plugin"))
        self.prefix = self.plugin.__module__.rsplit(".nvda_adapter.", 1)[0]
        self.weather = self.plugin._weather
        self.require(self.weather is not None, "weather composition initialized independently")
        self.control_module = importlib.import_module(self.prefix + ".nvda_adapter.weather_control")
        self.ui_module = importlib.import_module(self.prefix + ".nvda_adapter.weather_settings")
        self.provider_module = importlib.import_module(self.prefix + ".infrastructure.weather_provider")
        self.settings_module = importlib.import_module(self.prefix + ".domain.weather")
        self.messages = []
        self.weather.speak = self.messages.append
        self.frame = wx.Frame(None, title="Weather isolated test")
        self.opener = wx.Button(self.frame, label="Return focus here")
        self.frame.Show(); self.opener.SetFocus()
        self.flow = self.scenarios()
        self.advance()

    def send(self, key="NVDA+w"):
        # Explicit physical W virtual key avoids VkKeyScanEx depending on an
        # interactive keyboard layout unavailable on an inactive test desktop.
        gesture = keyboardHandler.KeyboardInputGesture([keyboardHandler.getNVDAModifierKeys()[0]], ord("W"), 0, False)
        self.require(scriptHandler.findScript(gesture) == self.plugin.script_weather, "InputManager weather binding " + key)
        inputCore.manager.executeGesture(gesture)

    def scenarios(self):
        yield 200
        self.send()
        yield 700
        self.require(len(self.messages) == 1 and not self.weather.service.cache, "disabled command speaks once without network")
        doc = self.plugin.script_weather.__doc__
        expected = "بالضغط عليه مرة واحدة يعلن عن حالة الطقس الحالية، وبالضغط عليه مرتين يعلن عن توقعات الطقس لليوم، وبالضغط عليه ثلاث مرات يعلن عن توقعات الطقس للأيام القادمة."
        self.require(doc == expected if self.result["language"].startswith("ar") else "Press once" in doc, "exact localized command description")
        self.require("NVDA" not in doc, "description contains no assigned key")
        provider = self.weather.service.provider
        self.calls = []
        def fetch(location, settings):
            import time
            time.sleep(.25)
            self.calls.append("weather")
            zone = provider.zones.get_timezone(location.timezone_id)
            return self.provider_module.parse_weather(fixture(datetime.now(timezone.utc), zone), zone)
        provider.fetch = fetch
        period = self.settings_module.WeatherPeriod
        provider.fetch_air = lambda location: period(datetime.now(timezone.utc), {"us_aqi": 42})
        draft = self.weather.settings.open_draft()
        draft.settings.weather.enabled = True
        draft.settings.weather.detail = "detailed"
        draft.settings.weather.current["us_aqi"] = True
        draft.settings.weather.include_in_daily_info = True
        self.weather.settings.apply(draft)
        heartbeat = []
        wx.CallLater(30, lambda: heartbeat.append(True))
        yield 100
        self.require(bool(heartbeat) and not self.calls, "UI remains responsive while worker fetches")
        yield 500
        self.require(len(self.calls) == 1 and self.weather.service.air_data(), "automatic weather and independent air fetch complete")
        self.require(len(self.messages) == 1, "automatic updates are silent")
        self.result["reports"] = []
        for count, report in ((1, "current"), (2, "today"), (3, "future")):
            self.messages.clear(); scriptHandler.clearLastScript()
            for _ in range(count):
                self.send(); yield 80
                self.require(not self.messages, "no premature report for press count " + str(count))
            yield 650
            self.require(len(self.messages) == 1 and self.weather.last_report == report, "only final requested report " + report)
            self.result["reports"].append(self.messages[-1])
        summary = self.weather.summary(self.result["language"])
        self.require("Open-Meteo" in summary, "cached daily summary includes attribution")
        self.weather.show()
        yield 200
        dialog = self.control_module.WeatherTextDialog._instance
        self.require(dialog and dialog.text.GetValue() and "creativecommons.org" in dialog.text.GetValue(), "independent copyable weather report with licence links")
        self.require(bool(self.obj(dialog.text).name), "weather native edit has accessible name")
        self.require(bool(self.obj(dialog.weather_source_button).name), "source button accessible name")
        self.require(dialog.text.GetWindowStyleFlag() & wx.TE_READONLY, "report native edit is read only")
        dialog.text.SetSelection(0, dialog.text.GetLastPosition())
        self.require(dialog.text.GetStringSelection() == dialog.text.GetValue(), "whole report can be selected")
        dialog.text.SetInsertionPoint(0)
        dialog.text.SetInsertionPointEnd()
        self.require(dialog.text.GetInsertionPoint() == dialog.text.GetLastPosition(), "end navigation supported")
        dialog.text.SetFocus()
        dialog.text.Navigate()
        self.require(wx.Window.FindFocus().GetId() == wx.ID_CLOSE, "Tab reaches Close from report")
        wx.Window.FindFocus().Navigate()
        self.require(wx.Window.FindFocus() is dialog.weather_source_button, "Tab reaches source and licence button")
        dialog.weather_source_button.Navigate(wx.NavigationKeyEvent.IsBackward)
        wx.Window.FindFocus().Navigate(wx.NavigationKeyEvent.IsBackward)
        self.require(wx.Window.FindFocus() is dialog.text, "Shift Tab returns to report")
        # Opening a second report type must keep the text being read intact.
        before = dialog.text.GetValue()
        self.weather.select("current", text=True)
        self.require(dialog.text.GetValue() == before, "open report is never rewritten during reading")
        other = importlib.import_module(self.prefix + ".nvda_adapter.text_dialog").SelectableTextDialog
        other.show(self.frame, "Prayer fixture", "Prayer content")
        self.require(other._instance is not dialog and other._instance.text.GetValue() == "Prayer content", "other information window independent")
        other._instance.Close()
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetKeyCode(wx.WXK_ESCAPE)
        dialog.ProcessEvent(event)
        yield 150
        self.require(self.control_module.WeatherTextDialog._instance is None, "Escape closes report")
        self.require(wx.Window.FindFocus() is self.opener, "report close restores opener focus")
        # Test the exact section implementation used inside the one main panel.
        panel = self.ui_module.WeatherSettingsPanel(self.frame, draft.settings.weather,
            lambda: self.weather.settings.runtime_settings.location, self.weather)
        panel.Show()
        self.require(bool(self.obj(panel.enabled).name), "weather checkbox accessible name")
        self.require(bool(self.obj(panel.system).name), "unit system accessible name")
        panel.unit_system("custom")
        self.require(panel.custom_units.IsEnabled(), "custom units enabled only for custom system")
        panel.unit_system("metric")
        self.require(not panel.custom_units.IsEnabled(), "custom units excluded from keyboard focus in metric")
        information = self.ui_module.InformationDialog(self.frame, draft.settings.weather)
        information.Show(); information.category.SetFocus()
        self.require(bool(self.obj(information.category).name), "category selector accessible name")
        information.select("today")
        self.require(information.pages["today"].IsShown() and not information.pages["current"].IsShown(), "only selected information category visible")
        self.require(not information.pages["future"].IsShown(), "unrelated category excluded from navigation")
        information.category.Navigate()
        self.require(wx.Window.FindFocus().GetParent() is information.pages["today"], "category Tab enters selected page")
        information.Close(); information.Destroy()
        units = self.ui_module.UnitsDialog(self.frame, draft.settings.weather.custom_units)
        units.Show()
        self.require(len([w for w in units.GetChildren() if isinstance(w, wx.Choice)]) == 5, "all five custom unit selectors exist")
        units.Destroy(); panel.Destroy()
        # Instantiate the actual main panel to catch routing and settings draft errors.
        settings_panel = importlib.import_module(self.prefix + ".nvda_adapter.settings_panel").AwqatiSettingsPanel(self.frame)
        sections = importlib.import_module(self.prefix + ".nvda_adapter.settings_sections")
        settings_panel._section = sections.SettingsSection.WEATHER
        settings_panel._render_section()
        self.require(isinstance(settings_panel._section_panel, self.ui_module.WeatherSettingsPanel), "weather is routed inside original settings panel")
        settings_panel.onDiscard(); settings_panel.Destroy()
        # Input Gestures can remap this same one command without fixed-key logic.
        identifier = "kb:NVDA+f2"
        inputCore.manager.userGestureMap.add(identifier, self.plugin.__module__, "GlobalPlugin", "weather")
        gesture = keyboardHandler.KeyboardInputGesture.fromName("NVDA+f2")
        self.require(scriptHandler.findScript(gesture) == self.plugin.script_weather, "weather command can be reassigned in Input Gestures")
        inputCore.manager.userGestureMap.remove(identifier, self.plugin.__module__, "GlobalPlugin", "weather")
        self.require(self.plugin._content.daily_prayer_times(lambda text: text), "prayer command still works")
        self.require(self.plugin._content.scientific_info_text(self.result["language"]), "astronomy command still works")
        self.require(self.plugin._content.arabian_short(self.result["language"]), "heritage command still works")
        self.require("Open-Meteo" in self.plugin._content.daily_info_text(self.result["language"]), "daily synopsis appends cache summary")
        # Invalidate in-flight speech immediately when disabled.
        self.messages.clear()
        self.weather.service.cache = None
        self.weather.service.last_attempt["weather"] = float("-inf")
        self.weather.select("current")
        draft = self.weather.settings.open_draft(); draft.settings.weather.enabled = False
        self.weather.settings.apply(draft)
        yield 500
        self.require(len(self.messages) == 1 and self.messages[0] in ("Please wait", "يُرجى الانتظار"), "disable suppresses pending result after single exact waiting message")
        self.require(self.weather.timer is None, "disabled service has no automatic timer")
        self.weather.close()

    def finish(self):
        if hasattr(self, "weather") and self.weather:
            if not self.weather.closed: self.weather.close()
        if self.frame: self.frame.Destroy()
        (self.profile / "live-result.json").write_text(json.dumps(self.result, ensure_ascii=False, indent=2), "utf-8")
        wx.CallLater(300, core.triggerNVDAExit)
