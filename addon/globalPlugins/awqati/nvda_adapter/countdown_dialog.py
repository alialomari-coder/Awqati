"""Native Windows controls, stable identities and keyboard-only timer editing."""
from pathlib import Path
from uuid import uuid4
import addonHandler
import languageHandler
import wx
from ..domain import AlertAction
from ..domain.countdown import Countdown, INTERVALS
from ..infrastructure.audio_files import validate_wav, atomic_copy
from .settings_sections import is_rtl_language
from .countdown_formatter import STATE_LABELS
from .native_accessibility import set_list_name

addonHandler.initTranslation()


def direction(window):
    window.SetLayoutDirection(wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage()) else wx.Layout_LeftToRight)


def duration(ns):
    seconds = max(0, (int(ns) + 999999999) // 10**9)
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


class TimerEditor(wx.Dialog):
    def __init__(self, parent, control, timer=None):
        super().__init__(parent, title=_("Edit countdown timer") if timer else _("New countdown timer"))
        direction(self)
        self.control, self.original, self.reference = control, timer, timer.sound_ref if timer else None
        self.result, self.start_now = None, False
        self.content = wx.ScrolledWindow(self, style=wx.VSCROLL | wx.TAB_TRAVERSAL)
        self.content.SetScrollRate(0, 16)
        self.box = wx.BoxSizer(wx.VERTICAL)
        self.name = self.field(_("Timer name"), wx.TextCtrl, value=timer.name if timer else "")
        seconds = timer.duration if timer else 300
        self.hours = self.field(_("Hours (0-999)"), wx.SpinCtrl, min=0, max=999, initial=seconds // 3600)
        self.minutes = self.field(_("Minutes (0-59)"), wx.SpinCtrl, min=0, max=59, initial=seconds // 60 % 60)
        self.seconds = self.field(_("Seconds (0-59)"), wx.SpinCtrl, min=0, max=59, initial=seconds % 60)
        self.saved = wx.CheckBox(self.content, label=_("Save as a reusable timer"))
        self.saved.SetValue(timer.saved if timer else False)
        self.box.Add(self.saved, flag=wx.ALL, border=4)
        self.ticking = wx.CheckBox(self.content, label=_("Play clock ticking"))
        self.ticking.SetValue(timer.ticking if timer else False)
        self.box.Add(self.ticking, flag=wx.ALL, border=4)
        self.actions = (AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH)
        self.action = self.field(_("Alert method"), wx.Choice, choices=[_("Speech only"), _("Sound only"), _("Sound and speech")])
        self.action.SetSelection(self.actions.index(timer.action) if timer else 2)
        self.sound = wx.StaticText(self.content, label=_("Custom WAV sound") if self.reference else _("Default timer sound"))
        self.box.Add(self.sound, flag=wx.ALL, border=4)
        self.button(_("Choose WAV file"), self.choose_sound)
        self.button(_("Use default timer sound"), self.default_sound)
        self.button(_("Test sound"), lambda event: control.preview(self.reference))
        self.button(_("Stop preview"), lambda event: control.cancel_preview())
        self.pattern = self.field(_("Alert pattern"), wx.Choice, choices=[_("Once"), _("Repeated")])
        self.pattern.SetSelection(1 if timer and timer.repeat else 0)
        self.repeat_panel = wx.Panel(self.content)
        repeat_box = wx.BoxSizer(wx.VERTICAL)
        repeat_box.Add(wx.StaticText(self.repeat_panel, label=_("Interval between alerts")), flag=wx.ALL, border=4)
        labels = (_("5 seconds"), _("10 seconds"), _("15 seconds"), _("30 seconds"), _("1 minute"), _("2 minutes"), _("5 minutes"))
        self.interval = wx.Choice(self.repeat_panel, choices=list(labels), name=_("Interval between alerts"))
        self.interval.SetSelection(INTERVALS.index(timer.interval) if timer else 3)
        repeat_box.Add(self.interval, flag=wx.ALL, border=4)
        repeat_box.Add(wx.StaticText(self.repeat_panel, label=_("Total alerts (1-100)")), flag=wx.ALL, border=4)
        self.count = wx.SpinCtrl(self.repeat_panel, min=1, max=100, initial=timer.count if timer else 3, name=_("Total alerts (1-100)"))
        repeat_box.Add(self.count, flag=wx.ALL, border=4)
        self.repeat_panel.SetSizer(repeat_box)
        self.box.Add(self.repeat_panel, flag=wx.EXPAND)
        self.pattern.Bind(wx.EVT_CHOICE, self.pattern_changed)
        self.quiet = wx.CheckBox(self.content, label=_("Obey quiet hours for this timer"))
        self.quiet.SetValue(timer.obey_quiet_hours if timer else False)
        self.box.Add(self.quiet, flag=wx.ALL, border=4)
        self.button(_("Save timer"), lambda event: self.accept(False))
        self.button(_("Start timer now"), lambda event: self.accept(True))
        cancel = wx.Button(self.content, wx.ID_CANCEL, label=_("Cancel"))
        self.box.Add(cancel, flag=wx.ALL, border=4)
        self.content.SetSizer(self.box)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.content, proportion=1, flag=wx.EXPAND)
        self.SetSizer(outer)
        self.SetSize((600, min(760, wx.GetDisplaySize().height - 100)))
        self.pattern_changed()
        self.name.SetFocus()

    def field(self, label, kind, **options):
        self.box.Add(wx.StaticText(self.content, label=label), flag=wx.ALL, border=4)
        field = kind(self.content, name=label, **options)
        self.box.Add(field, flag=wx.EXPAND | wx.ALL, border=4)
        return field

    def button(self, label, handler):
        button = wx.Button(self.content, label=label)
        button.Bind(wx.EVT_BUTTON, handler)
        self.box.Add(button, flag=wx.ALL, border=4)

    def pattern_changed(self, event=None):
        self.repeat_panel.Show(self.pattern.GetSelection() == 1)
        self.content.FitInside()
        self.Layout()

    def choose_sound(self, event):
        with wx.FileDialog(self, _("Choose WAV file"), wildcard="WAV (*.wav)|*.wav", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            try:
                source = Path(dialog.GetPath())
                info = validate_wav(source)
                if info.frame_count / info.frame_rate > 30:
                    raise ValueError("timer WAV exceeds 30 seconds")
                files = self.control.runtime.audio.files
                files.ensure_sound_directories()
                target = files.sound_root / "timers" / ("awqati-managed-" + uuid4().hex + ".wav")
                atomic_copy(source, target)
                self.control.cancel_preview()
                self.reference = files.reference_for_existing(target).value
                self.sound.SetLabel(_("Custom WAV sound"))
            except (OSError, ValueError):
                wx.MessageBox(_("Choose a valid readable PCM WAV file of at most 30 seconds."), _("Countdown Timers"), parent=self)

    def default_sound(self, event):
        self.control.cancel_preview()
        self.reference = None
        self.sound.SetLabel(_("Default timer sound"))

    def accept(self, start):
        seconds = self.hours.GetValue() * 3600 + self.minutes.GetValue() * 60 + self.seconds.GetValue()
        if seconds <= 0:
            wx.MessageBox(_("The timer duration must be greater than zero."), _("Countdown Timers"), parent=self)
            self.seconds.SetFocus()
            return
        name = self.name.GetValue().strip()
        if not name:
            used = {timer.name for timer in self.control.service.definitions.values()}
            number = 1
            name = _("Timer {number}").format(number=number)
            while name in used:
                number += 1
                name = _("Timer {number}").format(number=number)
        try:
            self.result = Countdown(self.original.timer_id if self.original else uuid4().hex, name, seconds,
                saved=self.saved.GetValue(), action=self.actions[self.action.GetSelection()], sound_ref=self.reference,
                repeat=self.pattern.GetSelection() == 1, interval=INTERVALS[self.interval.GetSelection()],
                count=self.count.GetValue(), obey_quiet_hours=self.quiet.GetValue(), ticking=self.ticking.GetValue())
        except ValueError:
            wx.MessageBox(_("Enter a timer name of at most 200 characters and a valid duration."), _("Countdown Timers"), parent=self)
            self.name.SetFocus()
            return
        self.start_now = start
        self.EndModal(wx.ID_OK)


class CountdownDialog(wx.Dialog):
    def __init__(self, parent, control):
        super().__init__(parent, title=_("Countdown Timers"))
        self._build_controls(control)

    def _build_controls(self, control, embedded=False):
        direction(self)
        self.control, self.tokens, self.next_token = control, {}, 1
        self.refreshing = False
        self.order = None
        box = wx.BoxSizer(wx.VERTICAL)
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(750, 260), name=_("Timers list"))
        set_list_name(self.list, _("Timers list"))
        for index, label in enumerate((_("Timer name"), _("Original duration"), _("State"), _("Remaining"), _("Reusable"))):
            self.list.InsertColumn(index, label, width=145)
        box.Add(self.list, flag=wx.ALL | wx.EXPAND, border=8)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.selected)
        self.buttons = {}
        for key, label, handler in (
            ("new", _("New countdown timer"), lambda event: self.edit()),
            ("toggle", _("Start or resume"), lambda event: control.toggle()),
            ("pause", _("Pause"), lambda event: control.change("pause")),
            ("restart", _("Restart"), lambda event: control.restart()),
            ("cancel", _("Cancel timer"), lambda event: control.change("cancel")),
            ("edit", _("Edit"), lambda event: self.edit(True)),
            ("delete", _("Delete"), self.delete),
            ("stop", _("Stop timer alert"), lambda event: control.stop_alert()),
            ("preview", _("Test sound"), self.preview),
            ("query", _("Announce selected timer"), lambda event: control.announce())):
            button = wx.Button(self, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            self.buttons[key] = button
            box.Add(button, flag=wx.ALL, border=3)
        if not embedded:
            close = wx.Button(self, wx.ID_CANCEL, label=_("Close"))
            close.Bind(wx.EVT_BUTTON, self.on_close)
            self.Bind(wx.EVT_CLOSE, self.on_close)
            box.Add(close, flag=wx.ALL, border=8)
            self.SetSizerAndFit(box)
        else:
            self.SetSizer(box)
        self.refresh()
        for index in range(self.list.GetItemCount()):
            if self.list.GetItemData(index) == self.tokens.get(control.selected):
                self.list.Select(index)
                self.list.Focus(index)
        if not embedded:
            self.list.SetFocus()

    def selected(self, event):
        if not self.refreshing:
            token = self.list.GetItemData(event.GetIndex())
            self.control.selected = next((i for i, value in self.tokens.items() if value == token), None)
            self.update_buttons()

    def update_buttons(self):
        identity, service = self.control.selected, self.control.service
        valid = identity in service.definitions
        state = service.rows[identity]["state"] if valid else None
        for key in self.buttons:
            self.buttons[key].Enable(key == "new" or bool(valid))
        self.buttons["toggle"].Enable(state in ("ready", "paused"))
        self.buttons["pause"].Enable(state == "running")
        self.buttons["edit"].Enable(bool(valid) and state not in ("running", "paused"))
        self.buttons["cancel"].Enable(state in ("ready", "running", "paused", "finished"))
        active = valid and self.control.runtime.scheduler.has_pending("timers." + identity)
        self.buttons["stop"].Enable(state == "finished" and (not service.rows[identity]["ack"] or bool(active)))

    def refresh(self):
        service = self.control.service
        self.refreshing = True
        try:
            # Edit rows in place. Native SortItems keeps selected/focused item identity.
            ordered = service.ordered()
            valid_tokens = {self.tokens[i] for i in ordered if i in self.tokens}
            for row in range(self.list.GetItemCount() - 1, -1, -1):
                token = self.list.GetItemData(row)
                if token not in valid_tokens:
                    self.list.DeleteItem(row)
            for identity in ordered:
                if identity not in self.tokens:
                    self.tokens[identity] = self.next_token
                    self.next_token += 1
                    index = self.list.InsertItem(self.list.GetItemCount(), service.definitions[identity].name)
                    self.list.SetItemData(index, self.tokens[identity])
            ranks = {self.tokens[i]: index for index, i in enumerate(ordered)}
            order = tuple(ordered)
            if order != self.order:
                self.list.SortItems(lambda left, right: ranks[left] - ranks[right])
                self.order = order
            reverse = {token: identity for identity, token in self.tokens.items()}
            for index in range(self.list.GetItemCount()):
                identity = reverse[self.list.GetItemData(index)]
                timer, row = service.definitions[identity], service.rows[identity]
                values = (timer.name, duration(timer.duration * 10**9), _(STATE_LABELS.get(row.get("state"))),
                    duration(service.remaining(identity)), _("Yes") if timer.saved else _("No"))
                for column, value in enumerate(values):
                    if self.list.GetItemText(index, column) != value:
                        self.list.SetItem(index, column, value)
                # Global navigation and the native list share one selection.
                selected = identity == self.control.selected
                if self.list.IsSelected(index) != selected:
                    self.list.Select(index, selected)
                    if selected:
                        self.list.Focus(index)
            self.update_buttons()
        finally:
            self.refreshing = False

    def edit(self, existing=False):
        identity = self.control.identity() if existing else None
        if existing and not identity:
            return
        timer = self.control.service.definitions.get(identity)
        with TimerEditor(self, self.control, timer) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                def operation():
                    self.control.service.put(dialog.result)
                    self.control.cancel_scope(dialog.result.timer_id)
                    self.control.selected = dialog.result.timer_id
                    if dialog.start_now:
                        self.control.change("start", dialog.result.timer_id)
                self.control.perform(operation)
        self.control.cancel_preview()
        self.refresh()
        for index in range(self.list.GetItemCount()):
            if self.list.GetItemData(index) == self.tokens.get(self.control.selected):
                self.list.Select(index)
                self.list.Focus(index)
        self.list.SetFocus()

    def delete(self, event):
        identity = self.control.identity()
        if identity and wx.MessageBox(_("Delete this countdown timer?"), _("Countdown Timers"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) == wx.YES:
            def operation():
                self.control.service.delete(identity)
                self.control.cancel_scope(identity)
                self.control.selected = None
                for index in range(self.list.GetItemCount()):
                    self.list.Select(index, False)
            self.control.perform(operation)
            self.list.SetFocus()

    def preview(self, event):
        identity = self.control.identity()
        if identity:
            self.control.preview(self.control.service.definitions[identity].sound_ref)

    def on_close(self, event):
        self.control.cancel_preview()
        self.EndModal(wx.ID_CANCEL)
