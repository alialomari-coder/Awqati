"""Isolated NVDA scratchpad probe; never shipped in the add-on.

Copy into a dedicated test profile's scratchpad/globalPlugins directory.
No personal profile paths are accessed. This is an in-process integration
probe, not a substitute for owner listening, braille or physical key tests.
"""
from pathlib import Path
import json
import traceback
import globalPluginHandler
import globalVars
import versionInfo
import languageHandler
import gui
import wx


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self):
        super().__init__()
        self.root = Path(globalVars.appArgs.configPath)
        wx.CallLater(4500, self.run)

    def run(self):
        results = {"version": versionInfo.version, "language": languageHandler.getLanguage(), "checks": []}
        try:
            plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__ == "awqati.nvda_adapter.plugin")
            control = plugin._countdowns
            assert control.service is not None
            results["checks"].append("packaged plugin and countdown control loaded")
            from awqati.domain.countdown import Countdown
            from awqati.nvda_adapter.countdown_dialog import CountdownDialog, TimerEditor
            first, second = Countdown.create("First probe", 90), Countdown.create("Second probe", 45, saved=True)
            control.service.put(first)
            control.service.put(second)
            control.service.transition(first.timer_id, "start")
            control.service.transition(second.timer_id, "start")
            control.service.transition(first.timer_id, "pause")
            assert control.service.rows[second.timer_id]["state"] == "running"
            control.service.transition(first.timer_id, "resume")
            assert control.service.ordered()[0] == second.timer_id
            results["checks"].append("two independent timers, ordering, pause and resume")
            dialog = CountdownDialog(gui.mainFrame, control)
            control.dialog = dialog
            dialog.Show()
            dialog.list.Select(0)
            dialog.list.Focus(0)
            token = dialog.list.GetItemData(0)
            control.selected = next(i for i, t in dialog.tokens.items() if t == token)
            selected = control.selected
            dialog.refresh()
            assert control.selected == selected
            results["checks"].append("native manager construction and stable selected identity")
            with TimerEditor(dialog, control) as editor:
                editor.Show()
                assert not editor.repeat_panel.IsShown()
                editor.pattern.SetSelection(1)
                editor.pattern_changed()
                assert editor.repeat_panel.IsShown()
                editor.count.SetValue(7)
                editor.pattern.SetSelection(0)
                editor.pattern_changed()
                assert not editor.repeat_panel.IsShown() and editor.count.GetValue() == 7
                results["checks"].append("native editor and dependent repeat controls preserve values")
                results["controlNames"] = {key: getattr(editor, key).GetName() for key in ("name", "hours", "minutes", "seconds", "action", "pattern", "interval", "count")}
                editor.Hide()
            results["loaded"] = True
            # Leave the manager available for read-only UI Automation inspection.
        except Exception:
            results["error"] = traceback.format_exc()
        (self.root / "countdown_probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
