"""One stopwatch for gestures and the accessible dialog; no scheduler membership."""
from pathlib import Path
import addonHandler
import api
import gui
import ui
import wx
from ..application.stopwatch import Stopwatch
from ..infrastructure.stopwatch import InterruptClock, StopwatchRepository
from .audio_service import AudioService
from .stopwatch_formatter import spoken, results, lap_ordinal, MODE_LABELS, STATE_LABELS

addonHandler.initTranslation()

class StopwatchControl:
    def __init__(self, root, runtime, addon_root):
        self.runtime, self.addon_root = runtime, Path(addon_root)
        self.dialog = None
        self._feedback_generation = 0
        self._closed = False
        self.audio = AudioService(runtime.audio.files)
        # Runtime alert claims cancel both audio and any completion already
        # queued on the main thread, even if the alert ends before it runs.
        runtime.previews.add(self)
        self.repository = StopwatchRepository(root / "stopwatch_state.json")
        self.preferences = StopwatchRepository(root / "stopwatch_preferences.json")
        self.mode = 2  # New profiles only; a valid saved choice always wins below.
        self.error = None
        try:
            self.watch = Stopwatch(InterruptClock(), self.repository)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            self.repository.read_only = True
            self.watch = None
            self.error = error
        try:
            raw = self.preferences.load()
            if raw is not None:
                if type(raw) is not dict or raw.get("version") != 1 or type(raw.get("mode")) is not int or not 0 <= raw["mode"] <= 3:
                    raise ValueError("Invalid stopwatch preferences")
                self.mode = raw["mode"]
        except (OSError, ValueError, KeyError, TypeError):
            self.preferences.read_only = True
            wx.CallAfter(ui.message, _("Stopwatch preferences could not be read. The existing file was preserved."))
        if self.watch and self.watch.restored_running:
            wx.CallAfter(ui.message, _("The stopwatch was restored paused at its last saved value. Time while NVDA was closed was not added."))
        if not self.watch:
            wx.CallAfter(ui.message, _("Stopwatch data could not be read. The existing file was preserved; other Awqati features remain available."))

    def perform(self, operation):
        self.cancel_feedback()
        if self._closed:
            return
        if self.watch is None:
            ui.message(_("Stopwatch data could not be read. The existing file was preserved; other Awqati features remain available."))
            return
        try:
            operation()
        except OSError:
            ui.message(_("The stopwatch change could not be saved. The previous state was preserved."))
        except ValueError:
            ui.message(_("A lap can only be recorded while the stopwatch is running. The safety limit is 100000 laps."))
        finally:
            if self.dialog:
                self.dialog.refresh()

    def set_mode(self, mode):
        self.cancel_feedback()
        try:
            self.preferences.save({"version": 1, "mode": mode})
        except OSError:
            ui.message(_("Stopwatch preferences could not be saved. The previous preference was preserved."))
            return False
        self.mode = mode
        return True

    def cancel_feedback(self):
        """Invalidate queued speech before cancelling its asynchronous tone."""
        self._feedback_generation += 1
        self.audio.cancel()

    def cancel(self):
        """Participate in the existing runtime's preview cancellation hook."""
        self.cancel_feedback()

    def _play_tone(self, action, on_finished):
        if self.runtime.presenter.current:
            return False
        AudioService.cancel_previews()
        return self.audio.play_preview(None, self.addon_root / "sounds" / "stopwatch" / (action + ".wav"),
            lambda: None, on_finished)

    def preview(self, action):
        self.cancel_feedback()
        if not self._play_tone(action, lambda result: None):
            ui.message(_("Stopwatch tones are unavailable during an Awqati alert."))

    def feedback(self, action, message):
        self.cancel_feedback()
        if self._closed:
            return
        generation = self._feedback_generation
        if self.mode == 1:
            ui.message(message)
        elif self.mode in (0, 2):
            speak = self.mode == 2
            def finished(result):
                # AudioService dispatches after WavePlayer.idle() on NVDA's
                # main thread. Cancellation and newer commands suppress stale
                # success speech, including callbacks already queued by wx.
                if self._closed or generation != self._feedback_generation:
                    return
                self._feedback_generation += 1  # Consume the completion once.
                if result.cancelled:
                    return
                if speak and not self.runtime.presenter.current:
                    # The operation already succeeded, even if the tone failed.
                    ui.message(message)
            accepted = self._play_tone(action, finished)
            if not accepted and speak and not self._closed and generation == self._feedback_generation:
                # No tone can play (e.g. an automatic alert owns audio).
                ui.message(message)

    def toggle(self):
        def action():
            name = self.watch.toggle()
            self.feedback(name, {"start": _("Stopwatch started."), "pause": _("Stopwatch paused."),
                "resume": _("Stopwatch resumed.")}[name])
        self.perform(action)

    def lap_text(self, lap):
        return _("Lap {number}: {duration}. Total: {total}.").format(number=lap.number,
            duration=spoken(lap.duration_ns, _), total=spoken(lap.total_ns, _))

    def lap(self):
        def action():
            lap = self.watch.record_lap()
            self.feedback("lap", _("A new lap has been created. Lap {number} completed in {duration}.").format(
                number=lap_ordinal(lap.number, _), duration=spoken(lap.duration_ns, _)))
        self.perform(action)

    def current_lap(self):
        def action():
            if self.watch.state == "idle":
                ui.message(_("The stopwatch has not started yet."))
            else:
                duration = self.watch.current_lap_ns()
                ui.message(_("Current lap: {duration}.").format(duration=spoken(duration, _)))
        self.perform(action)

    def last_lap(self):
        self.perform(lambda: ui.message(self.lap_text(self.watch.laps[-1]) if self.watch.laps else _("No laps have been recorded.")))

    def total(self):
        self.perform(lambda: ui.message(_("Total elapsed: {time}.").format(time=spoken(self.watch.elapsed_ns(), _))))

    def status(self):
        self.perform(lambda: ui.message(_("{state}. Total elapsed: {time}. Recorded laps: {count}.").format(
            state=_(STATE_LABELS[self.watch.state]), time=spoken(self.watch.elapsed_ns(), _), count=len(self.watch.laps))))

    def count(self):
        self.perform(lambda: ui.message(_("Recorded laps: {count}.").format(count=len(self.watch.laps))))

    def reset(self):
        def action():
            if self.watch.state == "running":
                ui.message(_("Pause the stopwatch before resetting it."))
                return
            if self.watch.state == "idle":
                ui.message(_("The stopwatch has not started."))
                return
            parent = self.dialog or gui.mainFrame
            if wx.MessageBox(_("Reset the stopwatch and delete all recorded laps?"), _("Stopwatch"),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, parent) == wx.YES:
                # Recheck state in the service after the modal confirmation.
                if self.watch.state == "running":
                    ui.message(_("Pause the stopwatch before resetting it."))
                    return
                if self.watch.reset(confirmed=True):
                    self.feedback("reset", _("Stopwatch reset."))
        self.perform(action)

    def copy(self):
        def action():
            if api.copyToClip(results(self.watch, _)):
                ui.message(_("Stopwatch results copied."))
            else:
                ui.message(_("Stopwatch results could not be copied."))
        self.perform(action)

    def open(self):
        self.cancel_feedback()
        if self.watch is None:
            self.perform(lambda: None)
            return
        if self.dialog:
            self.dialog.Raise()
            self.dialog.toggle.SetFocus()
            return
        from .stopwatch_dialog import StopwatchDialog
        gui.mainFrame.prePopup()
        try:
            self.dialog = StopwatchDialog(gui.mainFrame, self)
            self.dialog.ShowModal()
        finally:
            if self.dialog:
                self.dialog.Destroy()
                self.dialog = None
            gui.mainFrame.postPopup()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.cancel_feedback()
        self.audio.close()
        if self.watch:
            try:
                self.watch.checkpoint()
            except (OSError, ValueError):
                ui.message(_("The stopwatch change could not be saved. The previous state was preserved."))
        if self.dialog:
            self.dialog.EndModal(wx.ID_CANCEL)
