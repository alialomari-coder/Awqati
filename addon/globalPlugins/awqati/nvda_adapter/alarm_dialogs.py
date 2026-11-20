"""Native keyboard accessible personal alarm manager and transactional editor."""
from dataclasses import replace
from pathlib import Path
import threading

import addonHandler
import languageHandler
import ui
import wx

from ..domain import AlertAction, AlertEventType, SoundReference
from ..domain.personal_alarms import PersonalAlarm, DURATIONS, SNOOZE_MINUTES, validate_alarm_fields
from ..domain.alerts import utc
from .settings_sections import is_rtl_language
from .sound_staging import SoundStagingSession
from .audio_service import AudioService

addonHandler.initTranslation()
N_ = lambda text: text
DAY_ORDER = (6, 0, 1, 2, 3, 4, 5)
DAY_NAMES = (N_("Sunday"), N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"))
ACTIONS = (AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH)
ACTION_NAMES = (N_("Speech only"), N_("Sound file only"), N_("Sound file and speech"))
DURATION_NAMES = (N_("30 seconds"), N_("One minute"), N_("Two minutes"), N_("Five minutes"))
SNOOZE_NAMES = (N_("One minute"), N_("Two minutes"), N_("Five minutes"), N_("Ten minutes"), N_("Fifteen minutes"), N_("Thirty minutes"))
OUTCOME_LABELS = {
    "interruptedByPrayer": N_("Last cycle interrupted by a prayer alert."),
    "interruptedByTimeAlert": N_("Last cycle interrupted by a higher-priority time alert."),
    "expiredInQueue": N_("Last cycle expired while waiting for another alert."),
    "expiredSnooze": N_("The previous snooze expired."),
    "quietHours": N_("Last cycle suppressed by quiet hours."),
    "invalidState": N_("This alarm needs state recovery before automatic playback."),
}


def set_direction(window):
    window.SetLayoutDirection(wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage()) else wx.Layout_LeftToRight)


def reschedule_saved_changes(parent, runtime):
    """A scheduling failure after persistence must never be called a failed save."""
    try:
        runtime.alarms_changed()
    except (OSError, ValueError, RuntimeError):
        wx.MessageBox(_("The changes were saved, but the alarm schedule could not be updated. Restart NVDA before relying on the changed alarms."),
            _("Personal alarm error"), wx.OK | wx.ICON_ERROR, parent)


def next_alarm_text(runtime):
    now = runtime.now.now()
    entries = [(runtime.alarms.next_run(alarm, now), alarm) for alarm in runtime.alarms.alarms.values() if alarm.enabled]
    entries = [(when, alarm) for when, alarm in entries if when]
    if not entries:
        return _("No enabled personal alarms.")
    when, alarm = min(entries, key=lambda entry: utc(entry[0]))
    seconds = max(0, int((utc(when) - utc(now)).total_seconds()))
    return _("Next alarm: {name}; {when}; remaining: {hours} hours and {minutes} minutes.").format(
        name=alarm.name, when=when.value.astimezone(runtime.alarms.zone_provider()).strftime("%Y-%m-%d %H:%M"),
        hours=((seconds + 59) // 60) // 60, minutes=((seconds + 59) // 60) % 60)


class AlarmEditor(wx.Dialog):
    def __init__(self, parent, runtime, alarm=None):
        super().__init__(parent, title=_("Edit personal alarm") if alarm else _("Add personal alarm"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        set_direction(self)
        self.runtime, self.original = runtime, alarm
        self.saved = False
        self._busy = False
        self._alive = True
        self.sound_ref = alarm.sound_ref if alarm else None
        self.staging = SoundStagingSession(runtime.audio.files.user_data_root, runtime.audio.files)
        self.preview = AudioService(runtime.audio.files)
        runtime.previews.add(self.preview)
        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
        grid.AddGrowableCol(1)

        def text(label, value=""):
            grid.Add(wx.StaticText(self, label=label))
            control = wx.TextCtrl(self, value=value, name=label)
            grid.Add(control, flag=wx.EXPAND)
            return control

        def choice(label, values, index):
            grid.Add(wx.StaticText(self, label=label))
            control = wx.Choice(self, choices=values, name=label)
            control.SetSelection(index)
            grid.Add(control, flag=wx.EXPAND)
            return control

        self.name = text(_("Alarm name"), alarm.name if alarm else "")
        # Empty new time fields are intentional: midnight is valid but not assumed.
        self.hour = text(_("Hour (0–23)"), str(alarm.hour) if alarm else "")
        self.minute = text(_("Minute (0–59)"), str(alarm.minute) if alarm else "")
        grid.Add(wx.StaticText(self, label=_("Repeat every")))
        # Windows LBS_MULTIPLESEL toggles Space; unmodified arrows move only caret.
        self.days = wx.ListBox(self, choices=[_(name) for name in DAY_NAMES], style=wx.LB_MULTIPLE, name=_("Repeat every"))
        if alarm:
            for i, day in enumerate(DAY_ORDER):
                if day in alarm.weekdays:
                    self.days.SetSelection(i)
        grid.Add(self.days, flag=wx.EXPAND)
        self.action = choice(_("Alert method"), [_(label) for label in ACTION_NAMES], ACTIONS.index(alarm.action) if alarm else 2)
        grid.Add((1, 1))
        self.sound_panel = wx.Panel(self)
        sound_row = wx.BoxSizer(wx.VERTICAL)
        self.sound_status = wx.StaticText(self.sound_panel, label=_("Default alarm sound"))
        sound_row.Add(self.sound_status)
        for label, handler in ((_("Choose custom sound"), self.choose_sound), (_("Preview selected sound"), self.preview_sound),
                (_("Stop preview"), lambda event: self.preview.cancel()), (_("Use default sound"), self.default_sound)):
            button = wx.Button(self.sound_panel, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            sound_row.Add(button, flag=wx.EXPAND)
        self.sound_panel.SetSizer(sound_row)
        grid.Add(self.sound_panel, flag=wx.EXPAND)
        self.duration = choice(_("Playback duration"), [_(label) for label in DURATION_NAMES], DURATIONS.index(alarm.duration) if alarm else 1)
        self.snooze = wx.CheckBox(self, label=_("Enable snooze"))
        self.snooze.SetValue(alarm.snooze_enabled if alarm else True)
        grid.Add(self.snooze)
        grid.Add((1, 1))
        grid.Add((1, 1))
        self.snooze_panel = wx.Panel(self)
        snooze_grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
        snooze_grid.Add(wx.StaticText(self.snooze_panel, label=_("Snooze duration")))
        self.snooze_minutes = wx.Choice(self.snooze_panel, choices=[_(label) for label in SNOOZE_NAMES], name=_("Snooze duration"))
        self.snooze_minutes.SetSelection(SNOOZE_MINUTES.index(alarm.snooze_minutes) if alarm else 2)
        snooze_grid.Add(self.snooze_minutes)
        self.unlimited = wx.CheckBox(self.snooze_panel, label=_("Unlimited snoozes"))
        self.unlimited.SetValue(alarm is not None and alarm.snooze_limit is None)
        snooze_grid.Add(self.unlimited)
        snooze_grid.Add((1, 1))
        self.limit_label = wx.StaticText(self.snooze_panel, label=_("Allowed snooze count"))
        snooze_grid.Add(self.limit_label)
        self.limit = wx.TextCtrl(self.snooze_panel, value=str(alarm.snooze_limit if alarm and alarm.snooze_limit else 3), name=_("Allowed snooze count"))
        snooze_grid.Add(self.limit)
        self.snooze_panel.SetSizer(snooze_grid)
        grid.Add(self.snooze_panel, flag=wx.EXPAND)
        self.quiet = wx.CheckBox(self, label=_("Obey quiet hours"))
        self.quiet.SetValue(alarm.obey_quiet_hours if alarm else False)
        grid.Add(self.quiet)
        grid.Add((1, 1))
        outer.Add(grid, 1, wx.ALL | wx.EXPAND, 12)
        outer.Add(self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.EXPAND, 12)
        self.SetSizerAndFit(outer)
        self.action.Bind(wx.EVT_CHOICE, self.visibility)
        self.snooze.Bind(wx.EVT_CHECKBOX, self.visibility)
        self.unlimited.Bind(wx.EVT_CHECKBOX, self.visibility)
        self.Bind(wx.EVT_BUTTON, self.save, id=wx.ID_OK)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.cleanup)
        self.visibility()
        self.name.SetFocus()

    def visibility(self, event=None):
        self.sound_panel.Show(ACTIONS[self.action.GetSelection()] is not AlertAction.SPEECH)
        self.snooze_panel.Show(self.snooze.GetValue())
        self.limit.Show(not self.unlimited.GetValue())
        self.limit_label.Show(not self.unlimited.GetValue())
        self.sound_status.SetLabel(_("Custom sound: {path}").format(path=self.sound_ref) if self.sound_ref else _("Default alarm sound"))
        self.Layout()
        self.Fit()

    def error(self, message, field):
        wx.MessageBox(message, _("Personal alarm error"), wx.OK | wx.ICON_ERROR, self)
        field.SetFocus()

    def choose_sound(self, event=None):
        if self._busy:
            return
        dialog = wx.FileDialog(self, message=_("Choose custom sound"), wildcard="WAV (*.wav)|*.wav", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
        finally:
            dialog.Destroy()
        self._busy = True
        def worker():
            try:
                reference, error = self.staging.prepare(path, "alarms"), None
            except Exception as caught:
                reference, error = None, caught
            wx.CallAfter(complete, reference, error)
        def complete(reference, error):
            if not self._alive:
                return
            self._busy = False
            if error:
                self.error(_("The sound file could not be loaded. Choose a valid PCM WAV file."), self.action)
            else:
                self.sound_ref = reference.value
                self.visibility()
        threading.Thread(target=worker, name="AwqatiAlarmSoundImport", daemon=True).start()

    def preview_sound(self, event=None):
        if self.runtime.presenter.current:
            ui.message(_("Wait until the current alert finishes before previewing a sound."))
            return
        self.preview.cancel()
        path = self.staging.resolve(SoundReference(self.sound_ref)) if self.sound_ref else None
        self.preview.play_preview(AlertEventType.PERSONAL_ALARM, path, lambda: None, lambda result: None)

    def default_sound(self, event=None):
        self.preview.cancel()
        self.sound_ref = None
        self.visibility()

    def save(self, event=None):
        days = tuple(DAY_ORDER[index] for index in self.days.GetSelections())
        error = validate_alarm_fields(self.hour.GetValue(), self.minute.GetValue(), days)
        if error:
            messages = {
                "timeAndDays": _("Specify an alarm time and at least one day of the week."),
                "time": _("Enter a valid alarm time: hour 0–23 and minute 0–59."),
                "days": _("Select at least one day from the Repeat every list."),
            }
            field = self.days if error == "days" else self.hour
            if error in ("time", "timeAndDays"):
                try:
                    if 0 <= int(self.hour.GetValue()) <= 23:
                        field = self.minute
                except ValueError:
                    pass
            self.error(messages[error], field)
            return
        if self._busy:
            self.error(_("Wait for the sound file to finish loading."), self.action)
            return
        try:
            limit = None if self.unlimited.GetValue() else int(self.limit.GetValue())
            if limit is not None and not 1 <= limit <= 1000000:
                raise ValueError()
        except ValueError:
            self.error(_("Enter a positive whole number of snoozes, or choose unlimited."), self.limit)
            return
        name = self.name.GetValue().strip()
        if not name:
            existing = {alarm.name for alarm in self.runtime.alarms.alarms.values()}
            base, number = _("Personal alarm"), 1
            name = base
            while name in existing:
                number += 1
                name = f"{base} {number}"
        options = dict(action=ACTIONS[self.action.GetSelection()], sound_ref=self.sound_ref,
            duration=DURATIONS[self.duration.GetSelection()], snooze_enabled=self.snooze.GetValue(),
            snooze_minutes=SNOOZE_MINUTES[self.snooze_minutes.GetSelection()], snooze_limit=limit,
            obey_quiet_hours=self.quiet.GetValue())
        alarm = (replace(self.original, name=name, hour=int(self.hour.GetValue()), minute=int(self.minute.GetValue()), weekdays=days, **options)
            if self.original else PersonalAlarm.create(name, int(self.hour.GetValue()), int(self.minute.GetValue()), days, **options))
        commit = None
        try:
            commit = self.staging.begin_commit([self.sound_ref] if self.sound_ref else [])
            self.runtime.alarms.put(alarm)
        except (OSError, ValueError) as error:
            if commit:
                self.staging.rollback(commit)
            self.error(_("The alarm could not be saved. Existing data has been preserved."), self.name)
            return
        self.staging.complete(commit)  # No global cleanup: settings and other alarms own files too.
        reschedule_saved_changes(self, self.runtime)
        self.saved = True
        self.EndModal(wx.ID_OK)

    def cleanup(self, event):
        if event.GetEventObject() is self:
            self._alive = False
            self.preview.close()
            self.runtime.previews.discard(self.preview)
            self.staging.discard()
        event.Skip()


class AlarmManager(wx.Dialog):
    _instance = None

    @classmethod
    def open(cls, parent, runtime):
        if cls._instance:
            cls._instance.Raise()
            cls._instance.list.SetFocus()
            return
        focus = wx.Window.FindFocus()
        dialog = cls._instance = cls(parent, runtime)
        try:
            dialog.ShowModal()
        finally:
            cls._instance = None
            dialog.Destroy()
            if focus:
                try:
                    focus.SetFocus()
                except RuntimeError:
                    pass

    def __init__(self, parent, runtime):
        super().__init__(parent, title=_("Personal Alarms"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._build_controls(runtime)

    def _build_controls(self, runtime, embedded=False):
        set_direction(self)
        self.runtime = runtime
        outer = wx.BoxSizer(wx.VERTICAL)
        if runtime.alarms.storage_error:
            message = (_("Some personal alarm data could not be read. Existing data has been preserved unchanged.")
                if runtime.alarms.repository.read_only else
                _("Personal alarm data could not be saved safely. Automatic personal alarms are paused; existing files are preserved. Other Awqati alerts remain available."))
            outer.Add(wx.StaticText(self, label=message), 0, wx.ALL, 12)
        self.list = wx.ListBox(self, name=_("Saved personal alarms"))
        outer.Add(self.list, 1, wx.ALL | wx.EXPAND, 12)
        row = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
        for label, handler in ((_("Add alarm"), lambda event: self.edit(new=True)), (_("Edit alarm"), lambda event: self.edit()),
                (_("Delete alarm"), self.delete), (_("Enable or disable selected alarm"), self.toggle),
                (_("Enable all alarms"), lambda event: self.enable_all(True)), (_("Disable all alarms"), lambda event: self.enable_all(False)),
                (_("Next alarm"), lambda event: ui.message(next_alarm_text(runtime)))):
            button = wx.Button(self, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            row.Add(button, 0, wx.RIGHT, 6)
        outer.Add(row, 0, wx.ALL, 12)
        if not embedded:
            outer.Add(self.CreateSeparatedButtonSizer(wx.CLOSE), 0, wx.ALL | wx.EXPAND, 12)
            self.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_CLOSE), id=wx.ID_CLOSE)
            self.Bind(wx.EVT_CHAR_HOOK, self.key)
        self.SetSizer(outer)
        if not embedded:
            self.SetSize((1000, 520))
        self.refresh()
        if not embedded:
            self.list.SetFocus()

    def key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CLOSE)
        else:
            event.Skip()

    def selected(self):
        index = self.list.GetSelection()
        return self.rows[index][1] if 0 <= index < len(self.rows) else None

    def refresh(self, identity=None):
        now = self.runtime.now.now()
        self.rows = [(self.runtime.alarms.next_run(alarm, now), alarm) for alarm in self.runtime.alarms.alarms.values()]
        self.rows.sort(key=lambda pair: (pair[0] is None, utc(pair[0]).timestamp() if pair[0] else 0, pair[1].name.casefold(), pair[1].alarm_id))
        labels = []
        for when, alarm in self.rows:
            days = ", ".join(_(DAY_NAMES[index]) for index, day in enumerate(DAY_ORDER) if day in alarm.weekdays)
            labels.append(_("{name}; {hour:02d}:{minute:02d}; {days}; {status}; next: {next}").format(
                name=alarm.name, hour=alarm.hour, minute=alarm.minute, days=days,
                status=_("Enabled") if alarm.enabled else _("Disabled"),
                next=when.value.strftime("%Y-%m-%d %H:%M") if when else _("None")))
            outcome = self.runtime.alarms.state.get(alarm.alarm_id, {}).get("outcome")
            if outcome in OUTCOME_LABELS:
                labels[-1] += " " + _(OUTCOME_LABELS[outcome])
        self.list.Set(labels)
        if self.rows:
            index = next((i for i, pair in enumerate(self.rows) if pair[1].alarm_id == identity), 0)
            self.list.SetSelection(index)

    def edit(self, new=False):
        alarm = None if new else self.selected()
        if not new and alarm is None:
            ui.message(_("Select a personal alarm first."))
            return
        dialog = AlarmEditor(self, self.runtime, alarm)
        try:
            dialog.ShowModal()
        finally:
            dialog.Destroy()
        self.refresh(alarm.alarm_id if alarm else None)
        self.list.SetFocus()

    def change(self, operation):
        try:
            operation()
        except (OSError, ValueError):
            wx.MessageBox(_("The alarm could not be saved. Existing data has been preserved."), _("Personal alarm error"), wx.OK | wx.ICON_ERROR, self)
        else:
            reschedule_saved_changes(self, self.runtime)
        self.refresh()
        self.list.SetFocus()

    def delete(self, event=None):
        alarm = self.selected()
        if alarm and wx.MessageBox(_("Delete alarm {name}?").format(name=alarm.name), _("Personal Alarms"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) == wx.YES:
            self.change(lambda: self.runtime.alarms.delete(alarm.alarm_id))

    def toggle(self, event=None):
        alarm = self.selected()
        if alarm:
            self.change(lambda: self.runtime.alarms.put(replace(alarm, enabled=not alarm.enabled)))

    def enable_all(self, enabled):
        self.change(lambda: self.runtime.alarms.enable_all(enabled))
