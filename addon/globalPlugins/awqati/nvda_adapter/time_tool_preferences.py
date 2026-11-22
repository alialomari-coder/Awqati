"""Service preferences only; operational views are owned by TimeToolsState.

These preferences retain their existing immediate-save semantics and separate
repositories. NVDA's Settings Cancel discards its draft, not these saved values.
"""
import addonHandler
import wx
from .stopwatch_dialog import StopwatchDialog

addonHandler.initTranslation()


class TimeToolPreferences(wx.Panel):
    _build_preferences = StopwatchDialog._build_preferences
    change_mode = StopwatchDialog.change_mode

    def __init__(self, parent, state):
        super().__init__(parent)
        self.control = state.stopwatch
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(self, label=_(
            "Time tool preferences are saved immediately, including when settings are cancelled.")),
            flag=wx.ALL, border=4)
        self._build_preferences(self.control, box)
        control = state.world_clock
        if control is not None:
            box.Add(wx.StaticText(self, label=_("World clock")), flag=wx.ALL, border=4)
            self.automatic = wx.CheckBox(self, label=_("Update data automatically"),
                name=_("Update data automatically"))
            self.automatic.SetValue(control.policy.enabled)
            def changed(event):
                if not control.set_automatic(self.automatic.GetValue()):
                    self.automatic.SetValue(control.policy.enabled)
            self.automatic.Bind(wx.EVT_CHECKBOX, changed)
            box.Add(self.automatic, flag=wx.ALL, border=4)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.destroyed)
        self.SetSizer(box)

    def destroyed(self, event):
        if event.GetEventObject() is self:
            self.control.cancel_feedback()
        event.Skip()
