"""Four independent tool windows; services remain owned by the plugin."""
import addonHandler
import gui
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
        self.world_clock = world_clock
        self.windows = {}
        self.closing = set()
        self.closed = False
        self.pending_close = None

    def modal_child(self, windows):
        children = []
        for child in wx.GetTopLevelWindows():
            if not isinstance(child, wx.Dialog) or child in windows or not child.IsModal():
                continue
            parent, depth = child.GetParent(), 0
            while parent:
                depth += 1
                if parent in windows:
                    children.append((depth, child))
                    break
                parent = parent.GetParent()
        return max(children, key=lambda pair: pair[0])[1] if children else None

    def request(self, identity):
        if identity not in TOOL_ORDER:
            raise ValueError(identity)
        if self.closed or self.closing:
            return
        # Never bypass a pending editor or confirmation in another tool.
        child = self.modal_child(tuple(self.windows.values()))
        if child:
            child.Raise()
            return
        if identity in self.windows:
            self.windows[identity].Raise()
            self.windows[identity].SetFocus()
            return
        focus = wx.Window.FindFocus()
        gui.mainFrame.prePopup()
        dialog = None
        try:
            dialog = ToolDialog(gui.mainFrame, self, identity, focus)
            self.windows[identity] = dialog
            dialog.Show()
        except Exception:
            self.windows.pop(identity, None)
            if dialog:
                dialog.dispose()
                dialog.Destroy()
            raise
        finally:
            gui.mainFrame.postPopup()
        dialog.Raise()
        wx.CallAfter(dialog.focus_initial)

    def close_window(self, identity):
        window = self.windows.get(identity)
        if window and identity not in self.closing:
            self.closing.add(identity)
            window.dispose()
        self._unwind()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for identity, window in self.windows.items():
            self.closing.add(identity)
            window.dispose()
        self._unwind()

    def _unwind(self):
        if self.pending_close:
            self.pending_close.Stop()
            self.pending_close = None
        targets = tuple(self.windows[key] for key in self.closing if key in self.windows)
        child = self.modal_child(targets)
        if child:
            child.EndModal(wx.ID_CANCEL)
            # Give the inner event loop time to return before its owner dies.
            self.pending_close = wx.CallLater(10, self._unwind)
            return
        for identity in tuple(self.closing):
            window = self.windows.pop(identity, None)
            self.closing.discard(identity)
            if window:
                focus = window.return_focus
                window.Destroy()
                if not self.closed and focus:
                    try:
                        if not focus.IsBeingDeleted():
                            focus.SetFocus()
                    except RuntimeError:
                        pass


class ToolDialog(wx.Dialog):
    def __init__(self, parent, state, identity, return_focus):
        titles = {"alarms": _("Alarms"), "timers": _("Timers"),
            "stopwatch": _("Stopwatch"), "world_clock": _("World clock")}
        super().__init__(parent, title=titles[identity],
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        from .countdown_dialog import direction
        direction(self)
        self.state, self.identity, self.return_focus = state, identity, return_focus
        self.disposed = False
        box = wx.BoxSizer(wx.VERTICAL)
        if identity == "alarms":
            self.view = AlarmPanel(self, state.runtime)
        elif identity == "timers" and state.countdowns.service is not None:
            self.view = CountdownPanel(self, state.countdowns)
        elif identity == "stopwatch" and state.stopwatch.watch is not None:
            self.view = StopwatchPanel(self, state.stopwatch)
        elif identity == "world_clock" and state.world_clock is not None and state.world_clock.service is not None:
            self.view = WorldClockPanel(self, state.world_clock)
        else:
            self.view = wx.Panel(self)
            content = wx.BoxSizer(wx.VERTICAL)
            message = (_("World clock data could not be read. Existing files were preserved.") if identity == "world_clock" else
                _("Countdown data could not be read. The existing file was preserved.") if identity == "timers" else
                _("Stopwatch data could not be read. The existing file was preserved; other Awqati features remain available."))
            content.Add(wx.StaticText(self.view, label=message))
            self.view.SetSizer(content)
        box.Add(self.view, flag=wx.EXPAND | wx.ALL, border=5)
        self.close_button = wx.Button(self, wx.ID_CANCEL, label=_("Close"))
        box.Add(self.close_button, flag=wx.ALL, border=8)
        self.SetSizerAndFit(box)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.close_button.Bind(wx.EVT_BUTTON, self.on_close)

    def focus_initial(self):
        if self.disposed or self.IsBeingDeleted():
            return
        target = getattr(self.view, "list", None) or getattr(self.view, "toggle", None)
        (target or self.close_button).SetFocus()

    def on_close(self, event):
        self.state.close_window(self.identity)

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        timer = getattr(self.view, "timer", None)
        if timer:
            timer.Stop()
        control = getattr(self.view, "control", None)
        if control and getattr(control, "dialog", None) is self.view:
            control.dialog = None
        if self.identity == "stopwatch":
            self.state.stopwatch.cancel_feedback()


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
    _build_preferences = StopwatchDialog._build_preferences
    _build_controls = StopwatchDialog._build_controls
    change_mode = StopwatchDialog.change_mode
    tick = StopwatchDialog.tick
    refresh = StopwatchDialog.refresh

    def __init__(self, parent, control):
        super().__init__(parent)
        self._build_controls(control, embedded=True, preferences=True)
        self.attach(control)
