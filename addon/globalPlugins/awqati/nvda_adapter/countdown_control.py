"""NVDA commands and lifecycle for the shared countdown engine."""
from pathlib import Path
import time
import addonHandler
import gui
import ui
import wx
from ..application.countdown import CountdownService
from ..application.countdown_ticking import TickPlan
from ..domain import AlertEventType
from ..infrastructure.stopwatch import InterruptClock, StopwatchRepository
from .audio_service import AudioService
from .ticking_audio import TickingAudio

addonHandler.initTranslation()
from .countdown_formatter import STATE_LABELS, spoken


class CountdownControl:
    def __init__(self, root, runtime):
        self.runtime, self.dialog, self.selected = runtime, None, None
        self.closed, self.pending = False, None
        self.error_reported = False
        self.audio = AudioService(runtime.audio.files)
        self.addon_root = runtime.audio.files.addon_root
        self.feedback_audio = AudioService(runtime.audio.files)
        self._feedback_generation, self._deferred_message = 0, None
        self.tick_plan = TickPlan()
        self.tick_audio = TickingAudio(self.addon_root / "sounds" / "timers", self.audio._make_player,
            self.audio._default_diagnostic)
        self.repository = StopwatchRepository(Path(root) / "countdown_timers.json")
        try:
            self.service = CountdownService(InterruptClock(), time.time, self.repository)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.repository.read_only = True
            self.service = None
            wx.CallAfter(ui.message, _("Countdown data could not be read. The existing file was preserved."))
        runtime.countdowns = self.service
        runtime.previews.add(self)
        self.tick()

    @property
    def selected(self):
        return getattr(self, "_selected", None)

    @selected.setter
    def selected(self, identity):
        if identity == self.selected:
            return
        self._selected = identity
        if getattr(self, "tick_audio", None):
            self.tick_audio.cancel()
            self.tick_plan.reset()

    def update_ticking(self):
        identity = self.selected
        timer = self.service.definitions.get(identity)
        row = self.service.rows.get(identity)
        eligible = bool(timer and row and row["state"] == "running" and timer.ticking and self.service.remaining(identity) > 0)
        blocked = bool(self.runtime.presenter.current or self._deferred_message or
            any(instance.busy for instance in tuple(AudioService._instances)))
        if not eligible or blocked:
            self.tick_audio.cancel()
        key = (identity, row["cycle"]) if row else None
        index = self.tick_plan.poll(self.service.clock(), key, eligible=eligible, blocked=blocked)
        if index is not None:
            self.tick_audio.play(index)

    def tick(self):
        if self.closed:
            return
        try:
            if self.service:
                now = self.runtime.now.now()
                for event in self.service.poll(now):
                    if not self.runtime.scheduler.scope_enabled(event.scope):
                        self.service.handled(event, "disabled")
                    else:
                        self.runtime.scheduler.schedule(event)
                self.runtime.presenter.present_next(now)
                if self._deferred_message and not self.runtime.presenter.current:
                    message, self._deferred_message = self._deferred_message, None
                    ui.message(message)
                self.update_ticking()
                if self.service.storage_error and not self.error_reported:
                    self.error_reported = True
                    ui.message(_("The countdown change could not be saved or is not valid for its current state."))
                if self.dialog:
                    self.dialog.refresh()
        except (OSError, ValueError) as error:
            if not self.error_reported:
                self.error_reported = True
                ui.message(_("The countdown change could not be saved or is not valid for its current state."))
        finally:
            if not self.closed:
                self.pending = wx.CallLater(250, self.tick)

    def perform(self, operation):
        if self.closed:
            return
        if not self.service:
            ui.message(_("Countdown data could not be read. The existing file was preserved."))
            return
        try:
            operation()
        except (OSError, ValueError, KeyError):
            ui.message(_("The countdown change could not be saved or is not valid for its current state."))
        finally:
            if self.dialog:
                self.dialog.refresh()

    def identity(self):
        if not self.service or self.selected not in self.service.definitions:
            ui.message(_("Select a countdown timer first."))
            return None
        return self.selected

    def cancel_scope(self, identity):
        current = self.runtime.presenter.current
        if current and current.scope == "timers." + identity:
            self.runtime.presenter.cancel_current()
        self.runtime.scheduler.cancel_scope("timers." + identity)

    def change(self, action, identity=None):
        identity = identity or self.identity()
        if not identity:
            return
        def operation():
            name = self.service.definitions[identity].name
            if self.service.transition(identity, action, confirmed=True):
                if action in ("restart", "cancel", "ack"):
                    self.cancel_scope(identity)
                self.tick_audio.cancel()
                if action in ("start", "resume", "restart", "pause", "cancel"):
                    self.tick_plan.reset()
                messages = {"start": _("Timer {name} started."), "resume": _("Timer {name} resumed."),
                    "pause": _("Timer {name} paused."), "restart": _("Timer {name} restarted."),
                    "cancel": _("Timer {name} cancelled."), "ack": _("Alert for timer {name} stopped.")}
                message = messages[action].format(name=name)
                if action == "ack":
                    ui.message(message)
                else:
                    self.feedback(action, message)
            else:
                ui.message(_("No countdown action is available in the current state."))
        self.perform(operation)

    def toggle(self):
        identity = self.identity()
        if identity:
            state = self.service.rows[identity]["state"]
            self.change({"ready": "start", "running": "pause", "paused": "resume"}.get(state, "start"), identity)

    def restart(self):
        identity = self.identity()
        if not identity:
            return
        if wx.MessageBox(_("Restart this timer from its original duration?"),
                _("Countdown Timers"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self.dialog or gui.mainFrame) != wx.YES:
            return
        self.change("restart", identity)

    def stop_current_alert(self):
        """Silence only the presenting timer, regardless of list selection.

        Cancel output before committing acknowledgement, so a storage failure
        cannot leave the audible ring playing. Queued timers remain untouched.
        """
        current = self.runtime.presenter.current
        if not current or current.event_type is not AlertEventType.COUNTDOWN:
            ui.message(_("There is no ringing timer currently."))
            return
        identity = current.metadata.get("timer_id")
        if not self.service or identity not in self.service.definitions:
            ui.message(_("There is no ringing timer currently."))
            return
        name = self.service.definitions[identity].name
        self.cancel_scope(identity)
        def acknowledge():
            if not self.service.rows[identity]["ack"]:
                self.service.transition(identity, "ack")
            ui.message(_("Alert for timer {name} stopped.").format(name=name))
        self.perform(acknowledge)

    def announce_remaining(self):
        identity = self.identity()
        if identity:
            ui.message(_("{name}. Remaining: {time}.").format(
                name=self.service.definitions[identity].name,
                time=spoken(self.service.remaining(identity), _)))

    def status_count(self):
        identity = self.identity()
        if identity:
            state_label = STATE_LABELS[self.service.rows[identity]["state"]]
            ui.message(_("{name}, {state}. Timers: {count}.").format(
                name=self.service.definitions[identity].name,
                state=_(state_label),
                count=len(self.service.definitions)))

    def navigate(self, step):
        def operation():
            ordered = self.service.ordered()
            if not ordered:
                ui.message(_("There are no countdown timers."))
                return
            if self.selected in ordered:
                index = (ordered.index(self.selected) + step) % len(ordered)
            else:
                index = 0 if step > 0 else len(ordered) - 1
            self.selected = ordered[index]
            self.announce_remaining()
        self.perform(operation)

    def stop_alert(self):
        identity = self.identity()
        if not identity:
            return
        active = self.runtime.scheduler.has_pending("timers." + identity)
        row = self.service.rows[identity]
        if row["state"] == "finished" and (not row["ack"] or active):
            if row["ack"]:
                self.cancel_scope(identity)
                ui.message(_("Alert for timer {name} stopped.").format(name=self.service.definitions[identity].name))
            else:
                self.change("ack", identity)
        else:
            ui.message(_("There is no pending alert for this timer."))

    def describe(self, identity):
        timer, row = self.service.definitions[identity], self.service.rows[identity]
        if row["state"] == "finished":
            return _("Timer {name} finished {time} ago.").format(name=timer.name,
                time=spoken(max(0, self.service.clock() - row["finished"]), _))
        return _("{name}, {state}. Remaining: {time}. Original duration: {duration}.").format(
            name=timer.name, state=_(STATE_LABELS.get(row.get("state"))),
            time=spoken(self.service.remaining(identity), _), duration=spoken(timer.duration * 10**9, _))

    def announce(self):
        identity = self.identity()
        if identity:
            ui.message(self.describe(identity))

    def count(self):
        self.perform(lambda: ui.message(_("Active countdown timers: {count}.").format(
            count=sum(row["state"] == "running" for row in self.service.rows.values()))))

    def nearest(self):
        def operation():
            active = [i for i in self.service.ordered() if self.service.rows[i]["state"] == "running"]
            ui.message(self.describe(active[0]) if active else _("No countdown timers are running."))
        self.perform(operation)

    def preview(self, reference=None):
        self.tick_audio.cancel()
        AudioService.cancel_previews()
        self.audio.cancel()
        path = self.runtime.audio.files.custom_path(reference) if reference else None
        if not self.audio.play_preview(AlertEventType.COUNTDOWN, path, lambda: None, lambda result: None):
            ui.message(_("Sound preview is unavailable during an Awqati alert."))

    def open(self):
        if not self.service:
            self.perform(lambda: None)
            return
        if self.dialog:
            self.dialog.Raise()
            return
        from .countdown_dialog import CountdownDialog
        gui.mainFrame.prePopup()
        try:
            self.dialog = CountdownDialog(gui.mainFrame, self)
            self.dialog.ShowModal()
        finally:
            if self.dialog:
                self.dialog.Destroy()
                self.dialog = None
            gui.mainFrame.postPopup()

    def cancel(self):
        """Central alert claims immediately silence all low-priority effects."""
        self.cancel_feedback()
        self.tick_audio.cancel()
        self.audio.cancel()

    def cancel_preview(self):
        self.audio.cancel()

    def cancel_feedback(self):
        self._feedback_generation += 1
        self._deferred_message = None
        self.feedback_audio.cancel()

    def feedback(self, action, message):
        self.cancel_feedback()
        self.tick_audio.cancel()
        if self.runtime.presenter.current:
            self._deferred_message = message
            return
        AudioService.cancel_previews()
        generation = self._feedback_generation
        def finished(result):
            if self.closed or generation != self._feedback_generation:
                return
            self._feedback_generation += 1
            if not result.cancelled:
                if self.runtime.presenter.current:
                    self._deferred_message = message
                else:
                    ui.message(message)
        accepted = self.feedback_audio.play_preview(None, self.addon_root / "sounds" / "timers" / (action + ".wav"),
            lambda: None, finished)
        if not accepted and generation == self._feedback_generation:
            self._deferred_message = message

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.pending:
            self.pending.Stop()
        self.audio.close()
        self.cancel_feedback()
        self.feedback_audio.close()
        self.tick_audio.close()
        if self.service:
            try:
                self.service.checkpoint()
            except OSError:
                ui.message(_("The countdown change could not be saved or is not valid for its current state."))
        if self.dialog:
            self.dialog.EndModal(wx.ID_CANCEL)
