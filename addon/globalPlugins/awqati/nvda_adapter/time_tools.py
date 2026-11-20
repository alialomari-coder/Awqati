"""Embedded views reuse the existing dialog builders and every command handler.

Services belong to the plugin. Destroying a view only detaches its UI observer.
The legacy dialog adapters remain available for internal compatibility.
"""
import addonHandler
import wx
from .alarm_dialogs import AlarmManager
from .countdown_dialog import CountdownDialog
from .stopwatch_dialog import StopwatchDialog
from .world_clock_dialog import WorldClockPanel

addonHandler.initTranslation()

TOOL_ORDER = ("alarms", "timers", "stopwatch", "world_clock")


class TimeToolsState:
    def __init__(self, runtime, countdowns, stopwatch, world_clock=None):
        self.runtime, self.countdowns, self.stopwatch = runtime, countdowns, stopwatch
        self.selected = "alarms"
        self.panel = None
        self.requested = None
        self.world_clock = world_clock

    def request(self, identity):
        if identity not in TOOL_ORDER:
            raise ValueError(identity)
        self.requested = identity
        panel = self.panel() if self.panel else None
        if panel:
            panel.show_time_tool(identity)
            self.requested = None


class EmbeddedView(wx.Panel):
    def attach(self, control):
        self.control = control
        control.dialog = self
        self.Bind(wx.EVT_WINDOW_DESTROY, self._detach)

    def _detach(self, event):
        if event.GetEventObject() is self:
            if getattr(self, "timer", None):
                self.timer.Stop()
            if self.control.dialog is self:
                self.control.dialog = None
        event.Skip()

    def EndModal(self, result):
        # Only controller shutdown uses this compatibility adapter.
        self.Destroy()


class AlarmPanel(wx.Panel):
    _build_controls = AlarmManager._build_controls
    selected = AlarmManager.selected
    refresh = AlarmManager.refresh
    edit = AlarmManager.edit
    change = AlarmManager.change
    delete = AlarmManager.delete
    toggle = AlarmManager.toggle
    enable_all = AlarmManager.enable_all

    def __init__(self, parent, runtime):
        super().__init__(parent)
        self._build_controls(runtime, embedded=True)


class CountdownPanel(EmbeddedView):
    _build_controls = CountdownDialog._build_controls
    selected = CountdownDialog.selected
    update_buttons = CountdownDialog.update_buttons
    refresh = CountdownDialog.refresh
    edit = CountdownDialog.edit
    delete = CountdownDialog.delete
    preview = CountdownDialog.preview

    def __init__(self, parent, control):
        super().__init__(parent)
        self._build_controls(control, embedded=True)
        self.attach(control)


class StopwatchPanel(EmbeddedView):
    _build_controls = StopwatchDialog._build_controls
    change_mode = StopwatchDialog.change_mode
    tick = StopwatchDialog.tick
    refresh = StopwatchDialog.refresh

    def __init__(self, parent, control):
        super().__init__(parent)
        self._build_controls(control, embedded=True)
        self.attach(control)


class TimeToolsHost:
    def __init__(self, parent, sizer, state, layout):
        self.parent, self.sizer, self.state, self.layout = parent, sizer, state, layout
        self.views = {}
        sizer.Add(wx.StaticText(parent, label=_("Time tools:")), flag=wx.TOP, border=8)
        self.choice = wx.Choice(parent, choices=[_("Alarms"), _("Timers"), _("Stopwatch"), _("World clock")],
            name=_("Time tools"))
        self.choice.SetSelection(TOOL_ORDER.index(state.selected))
        sizer.Add(self.choice, flag=wx.EXPAND)
        self.choice.Bind(wx.EVT_CHOICE, self.on_choice)
        self.show(state.selected)

    def select(self, identity):
        self.choice.SetSelection(TOOL_ORDER.index(identity))
        self.show(identity)
        self.choice.SetFocus()

    def on_choice(self, event):
        self.show(TOOL_ORDER[self.choice.GetSelection()])
        self.choice.SetFocus()
        event.Skip()

    def show(self, identity):
        # Retain native controls and selection; hiding a parent excludes its
        # descendants from Windows keyboard navigation and the active UI.
        for view in self.views.values():
            view.Hide()
        if identity not in self.views:
            state = self.state
            if identity == "alarms":
                view = AlarmPanel(self.parent, state.runtime)
            elif identity == "timers" and state.countdowns.service is not None:
                view = CountdownPanel(self.parent, state.countdowns)
            elif identity == "stopwatch" and state.stopwatch.watch is not None:
                view = StopwatchPanel(self.parent, state.stopwatch)
            elif identity == "world_clock" and state.world_clock is not None and state.world_clock.service is not None:
                view = WorldClockPanel(self.parent, state.world_clock)
            else:
                view = wx.Panel(self.parent)
                box = wx.BoxSizer(wx.VERTICAL)
                message = (_("World clock data could not be read. Existing files were preserved.") if identity == "world_clock" else
                    _("Countdown data could not be read. The existing file was preserved.") if identity == "timers" else
                    _("Stopwatch data could not be read. The existing file was preserved; other Awqati features remain available."))
                box.Add(wx.StaticText(view, label=message))
                view.SetSizer(box)
            self.views[identity] = view
            self.sizer.Add(view, flag=wx.EXPAND)
        view = self.views[identity]
        view.Show()
        view.MoveAfterInTabOrder(self.choice)
        self.state.selected = identity
        self.layout()
