"""Native wx controls, stable lap list and silent numerical display updates."""
import addonHandler
import languageHandler
import wx
from .settings_sections import is_rtl_language
from .stopwatch_formatter import numeric, MODE_LABELS, STATE_LABELS, ACTION_LABELS

addonHandler.initTranslation()


class StopwatchDialog(wx.Dialog):
    def __init__(self, parent, control):
        super().__init__(parent, title=_("Stopwatch"))
        self._build_controls(control)

    def _build_controls(self, control, embedded=False, preferences=True):
        self.control = control
        self.SetLayoutDirection(wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage()) else wx.Layout_LeftToRight)
        box = wx.BoxSizer(wx.VERTICAL)
        self.time = wx.StaticText(self, label="00:00:00.000", name=_("Elapsed time"))
        box.Add(self.time, flag=wx.ALL, border=8)
        self.status = wx.StaticText(self, label="")
        box.Add(self.status, flag=wx.ALL, border=8)
        self.toggle = wx.Button(self, label=_("Start"))
        box.Add(self.toggle, flag=wx.ALL, border=4)
        self.toggle.Bind(wx.EVT_BUTTON, lambda event: control.toggle())
        self.lap = wx.Button(self, label=_("Record lap"))
        box.Add(self.lap, flag=wx.ALL, border=4)
        self.lap.Bind(wx.EVT_BUTTON, lambda event: control.lap())
        self.reset = wx.Button(self, label=_("Reset stopwatch"))
        box.Add(self.reset, flag=wx.ALL, border=4)
        self.reset.Bind(wx.EVT_BUTTON, lambda event: control.reset())
        box.Add(wx.StaticText(self, label=_("Recorded laps")), flag=wx.ALL, border=4)
        self.laps = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, name=_("Recorded laps"), size=(620, 230))
        for index, label in enumerate((_("Lap number"), _("Lap duration"), _("Total elapsed"))):
            self.laps.InsertColumn(index, label, width=180)
        box.Add(self.laps, flag=wx.ALL | wx.EXPAND, border=4)
        copy = wx.Button(self, label=_("Copy results"))
        box.Add(copy, flag=wx.ALL, border=4)
        copy.Bind(wx.EVT_BUTTON, lambda event: control.copy())
        if preferences:
            self._build_preferences(control, box)
        if not embedded:
            close = wx.Button(self, wx.ID_CANCEL, label=_("Close"))
            box.Add(close, flag=wx.ALL, border=8)
            self.SetSizerAndFit(box)
        else:
            self.SetSizer(box)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.tick, self.timer)
        if not embedded:
            self.Bind(wx.EVT_CLOSE, self.on_close)
            close.Bind(wx.EVT_BUTTON, self.on_close)
        self.timer.Start(100)
        self.refresh()
        if not embedded:
            self.toggle.SetFocus()

    def _build_preferences(self, control, box):
        box.Add(wx.StaticText(self, label=_("Confirmation sounds")), flag=wx.ALL, border=4)
        self.mode = wx.Choice(self, choices=[_(label) for label in MODE_LABELS], name=_("Confirmation sounds"))
        self.mode.SetSelection(control.mode)
        self.mode.Bind(wx.EVT_CHOICE, self.change_mode)
        box.Add(self.mode, flag=wx.ALL, border=4)
        box.Add(wx.StaticText(self, label=_("Preview tone")), flag=wx.ALL, border=4)
        self.preview = wx.Choice(self, choices=[_("Start"), _("Pause"), _("Resume"), _("Record lap"), _("Reset stopwatch")], name=_("Preview tone"))
        self.preview.SetSelection(0)
        box.Add(self.preview, flag=wx.ALL, border=4)
        play = wx.Button(self, label=_("Play preview"))
        box.Add(play, flag=wx.ALL, border=4)
        play.Bind(wx.EVT_BUTTON, lambda event: control.preview(("start", "pause", "resume", "lap", "reset")[self.preview.GetSelection()]))
        stop = wx.Button(self, label=_("Stop preview"))
        box.Add(stop, flag=wx.ALL, border=4)
        stop.Bind(wx.EVT_BUTTON, lambda event: control.cancel_feedback())

    def change_mode(self, event):
        if not self.control.set_mode(self.mode.GetSelection()):
            self.mode.SetSelection(self.control.mode)

    def tick(self, event=None):
        # No ui.message, focus change, control reconstruction or disk writes.
        self.time.SetLabel(numeric(self.control.watch.elapsed_ns()))

    def refresh(self):
        watch = self.control.watch
        self.tick()
        label = _(STATE_LABELS[watch.state])
        if self.status.GetLabel() != label:
            self.status.SetLabel(label)
        toggle_label = _(ACTION_LABELS[watch.state])
        if self.toggle.GetLabel() != toggle_label:
            self.toggle.SetLabel(toggle_label)
        self.lap.Enable(watch.state == "running")
        # Keep reset reachable while running so its explanatory message is available.
        count = self.laps.GetItemCount()
        if count > len(watch.laps):
            self.laps.DeleteAllItems()
            count = 0
        for lap in watch.laps[count:]:
            index = self.laps.InsertItem(self.laps.GetItemCount(), str(lap.number))
            self.laps.SetItem(index, 1, numeric(lap.duration_ns))
            self.laps.SetItem(index, 2, numeric(lap.total_ns))

    def on_close(self, event):
        self.timer.Stop()
        self.control.cancel_feedback()
        self.EndModal(wx.ID_CANCEL)
