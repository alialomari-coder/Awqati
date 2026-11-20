"""Deterministic countdown timing, storage and scheduler integration contracts."""
import ast
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from functools import cmp_to_key
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.application.countdown import CountdownService
from awqati.domain.countdown import Countdown, MAX_DURATION
from awqati.domain import AlertEvent, AlertEventType as T, AlertAction, Instant, AwqatiSettings
from awqati.application.alert_scheduler import AlertScheduler
from awqati.application.alert_presenter import AlertPresenter, OutputResult, format_alert_message
from awqati.infrastructure.stopwatch import StopwatchRepository
from awqati.infrastructure.audio_files import SoundFileService, validate_wav
from test_task44_presenter import FakeOutput


class Memory:
    def __init__(self):
        self.raw, self.writes, self.fail = None, 0, False

    def load(self):
        return deepcopy(self.raw)

    def save(self, raw):
        if self.fail:
            raise OSError("disk full")
        self.raw = deepcopy(raw)
        self.writes += 1


class CountdownTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.wall = 1000 * 10**9, 1800000000
        self.repo = Memory()
        self.service = self.restore()
        self.timer = Countdown.create("Reading", 60)
        self.service.put(self.timer)
        self.identity = self.timer.timer_id

    def restore(self):
        return CountdownService(lambda: self.ns, lambda: self.wall, self.repo)

    def advance(self, seconds):
        self.ns += round(seconds * 10**9)
        self.wall += seconds

    def instant(self):
        return Instant(datetime.fromtimestamp(self.wall, timezone.utc))

    def start(self):
        self.service.transition(self.identity, "start")

    def finish(self):
        self.start()
        self.advance(60)
        return self.service.poll(self.instant())[0]

    def test_quick_saved_duplicate_names_independent_ids(self):
        other = Countdown.create("Reading", 120, saved=True)
        self.service.put(other)
        self.assertNotEqual(other.timer_id, self.identity)
        self.assertFalse(self.timer.saved)
        self.assertTrue(other.saved)

    def test_zero_negative_overflow_and_invalid_fields(self):
        for value in (0, -1, MAX_DURATION + 1, True, 1.2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Countdown.create("Bad", value)
        for options in (dict(count=101), dict(interval=7), dict(sound_ref="sounds/timers/../../bad.wav"), dict(name="")):
            with self.subTest(options=options), self.assertRaises(ValueError):
                replace(self.timer, **options)
        self.service.put(replace(self.timer, duration=MAX_DURATION))

    def test_pause_resume_actual_remaining(self):
        self.start()
        self.advance(12.125)
        self.service.transition(self.identity, "pause")
        self.advance(500)
        self.assertEqual(47875000000, self.service.remaining(self.identity))
        self.service.transition(self.identity, "resume")
        self.advance(47)
        self.assertEqual(875000000, self.service.remaining(self.identity))

    def test_restart_confirmation_and_cancel(self):
        self.start()
        self.advance(30)
        with self.assertRaises(ValueError):
            self.service.transition(self.identity, "restart")
        self.assertEqual(30 * 10**9, self.service.remaining(self.identity))
        self.service.transition(self.identity, "restart", confirmed=True)
        self.assertEqual(60 * 10**9, self.service.remaining(self.identity))
        self.service.transition(self.identity, "cancel")
        self.advance(200)
        self.assertEqual([], self.service.poll(self.instant()))
        self.assertIn(self.identity, self.service.definitions)

    def test_edit_running_rejected_and_delete_other_unaffected(self):
        other = Countdown.create("Other", 20)
        self.service.put(other)
        self.start()
        with self.assertRaises(ValueError):
            self.service.put(replace(self.timer, name="Changed"))
        self.service.delete(other.timer_id)
        self.assertEqual("running", self.service.rows[self.identity]["state"])

    def test_once_reserved_before_output_and_no_replay(self):
        event = self.finish()
        self.service.handled(event)
        self.assertTrue(self.service.rows[self.identity]["ack"])
        self.assertEqual([], self.service.poll(self.instant()))
        self.assertEqual([], self.restore().poll(self.instant()))
        self.assertEqual("finished", self.service.rows[self.identity]["state"])

    def test_repeat_total_and_interval(self):
        self.service.put(replace(self.timer, repeat=True, count=3, interval=10))
        event = self.finish()
        for attempt in range(3):
            self.assertEqual(attempt, event.metadata["attempt"])
            self.service.handled(event)
            self.service.handled(event)  # Duplicate callback cannot advance twice.
            self.assertEqual(attempt + 1, self.service.rows[self.identity]["attempt"])
            self.advance(9)
            self.assertEqual([], self.service.poll(self.instant()))
            self.advance(1)
            pending = self.service.poll(self.instant())
            if attempt < 2:
                event = pending[0]
            else:
                self.assertEqual([], pending)

    def test_ack_stops_repeats_keeps_finished(self):
        self.service.put(replace(self.timer, repeat=True))
        event = self.finish()
        self.service.handled(event)
        self.service.transition(self.identity, "ack")
        self.advance(300)
        self.assertEqual([], self.service.poll(self.instant()))
        self.assertEqual("finished", self.service.rows[self.identity]["state"])

    def test_no_writes_per_poll_or_remaining_query(self):
        self.start()
        count = self.repo.writes
        for _ in range(100):
            self.advance(.1)
            self.service.poll(self.instant())
            self.service.remaining(self.identity)
        self.assertEqual(count, self.repo.writes)

    def test_sleep_catch_up_and_stale_expiry(self):
        self.start()
        self.advance(120)
        self.assertEqual(1, len(self.service.poll(self.instant())))
        self.service.transition(self.identity, "restart")
        self.advance(661)
        self.assertEqual([], self.service.poll(self.instant()))
        self.assertEqual("finished", self.service.rows[self.identity]["state"])

    def test_wall_changes_do_not_change_countdown(self):
        self.start()
        self.wall += 86400
        self.assertEqual(60 * 10**9, self.service.remaining(self.identity))
        self.wall -= 200000
        self.advance(60)
        self.assertEqual(1, len(self.service.poll(self.instant())))

    def test_restore_running_after_time_away(self):
        self.start()
        self.advance(40)
        self.ns = 20 * 10**9  # A new Windows session may reset the source.
        restored = self.restore()
        self.assertEqual(20 * 10**9, restored.remaining(self.identity))
        self.advance(20)
        self.assertEqual(1, len(restored.poll(self.instant())))

    def test_restore_paused_and_restored_expiry(self):
        self.start()
        self.advance(10)
        self.service.transition(self.identity, "pause")
        self.advance(500)
        self.assertEqual(50 * 10**9, self.restore().remaining(self.identity))
        self.service.transition(self.identity, "resume")
        self.advance(100)
        self.assertEqual(1, len(self.restore().poll(self.instant())))

    def test_long_duration_no_accumulated_drift(self):
        self.service.put(replace(self.timer, duration=MAX_DURATION))
        self.start()
        for _ in range(10000):
            self.advance(.1)
            self.service.remaining(self.identity)
        self.assertEqual((MAX_DURATION - 1000) * 10**9, self.service.remaining(self.identity))

    def test_pending_event_does_not_build_repeat_backlog(self):
        event = self.finish()
        self.advance(100)
        self.assertEqual(event.event_id, self.service.poll(self.instant())[0].event_id)
        self.assertEqual(0, self.service.rows[self.identity]["attempt"])

    def test_fail_save_preserves_previous_state(self):
        before = deepcopy(self.service.rows)
        self.repo.fail = True
        with self.assertRaises(OSError):
            self.start()
        self.assertEqual(before, self.service.rows)
        self.assertTrue(self.service.storage_error)

    def test_atomic_repository_and_corruption_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "countdowns.json"
            repo = StopwatchRepository(path)
            service = CountdownService(lambda: self.ns, lambda: self.wall, repo)
            service.put(self.timer)
            self.assertEqual(1, len(CountdownService(lambda: self.ns, lambda: self.wall, repo).definitions))
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                repo.load()
            with self.assertRaises(OSError):
                repo.save({})
            self.assertEqual("{broken", path.read_text(encoding="utf-8"))

    def test_simultaneous_timers_and_priority(self):
        other = Countdown.create("Other", 60)
        self.service.put(other)
        self.service.transition(other.timer_id, "start")
        self.start()
        self.advance(60)
        events = self.service.poll(self.instant())
        self.assertEqual(2, len(events))
        scheduler = AlertScheduler(self.instant)
        scheduler.schedule_many(events)
        personal = AlertEvent("personal", T.PERSONAL_ALARM, self.instant(), scope="personal", action=AlertAction.SPEECH)
        prayer = AlertEvent("prayer", T.PRAYER_TIME, self.instant(), scope="prayer", action=AlertAction.SPEECH)
        scheduler.schedule_many([personal, prayer])
        ordered = []
        for _ in range(4):
            event = scheduler.claim_for_presentation(self.instant())
            ordered.append(event.event_type)
            scheduler.complete()
        self.assertEqual([T.PRAYER_TIME, T.PERSONAL_ALARM, T.COUNTDOWN, T.COUNTDOWN], ordered)

    def test_disabled_alerts_do_not_stop_counting(self):
        settings = AwqatiSettings()
        settings.general.all_automatic_alerts_enabled = False
        scheduler = AlertScheduler(self.instant, lambda: settings)
        event = self.finish()
        self.assertFalse(scheduler.schedule(event))
        self.service.handled(event, "disabled")
        self.assertEqual("finished", self.service.rows[self.identity]["state"])
        self.assertEqual([], self.service.poll(self.instant()))

    def test_default_and_missing_custom_fallback(self):
        event = replace(self.timer, sound_ref="sounds/timers/missing.wav")
        self.service.put(event)
        finished = self.finish()
        with tempfile.TemporaryDirectory() as folder:
            files = SoundFileService(Path(folder), ROOT / "addon/globalPlugins/awqati")
            resolved = files.resolve(finished)
            self.assertEqual("default", resolved.source)
            self.assertIn("timers", str(resolved.path))
            info = validate_wav(resolved.path)
            self.assertLess(info.frame_count / info.frame_rate, 2)

    def test_formatter_names_completion_in_both_languages(self):
        event = self.finish()
        self.assertIn("انتهى", format_alert_message(event, "ar"))
        self.assertIn("Reading", format_alert_message(event, "en"))

    def test_countdown_scripts_keep_legacy_names_and_add_seven_defaults(self):
        tree = ast.parse((ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text(encoding="utf-8"))
        scripts = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("script_countdown")]
        self.assertEqual(9, len(scripts))
        self.assertEqual(7, sum(any(k.arg == "gesture" for d in n.decorator_list for k in d.keywords) for n in scripts))

    def test_all_one_hundred_repetitions_survive_more_than_ten_minutes(self):
        self.service.put(replace(self.timer, repeat=True, count=100, interval=300))
        event = self.finish()
        for attempt in range(100):
            self.assertEqual(attempt, event.metadata["attempt"])
            self.service.handled(event)
            self.advance(300)
            events = self.service.poll(self.instant())
            if attempt < 99:
                self.assertEqual(1, len(events))
                event = events[0]
        self.assertEqual([], events)

    def test_old_callback_cannot_ack_new_cycle(self):
        old = self.finish()
        self.service.transition(self.identity, "restart")
        self.service.handled(old)
        self.assertEqual(0, self.service.rows[self.identity]["attempt"])
        self.assertFalse(self.service.rows[self.identity]["ack"])

    def test_no_negative_remaining_after_expiry(self):
        self.start()
        self.advance(70)
        self.assertEqual(0, self.service.remaining(self.identity))
        self.assertFalse(self.service.transition(self.identity, "pause"))
        self.service.poll(self.instant())
        self.assertEqual(0, self.service.remaining(self.identity))

    def test_late_repeat_after_sleep_is_suppressed_without_catchup_burst(self):
        self.service.put(replace(self.timer, repeat=True))
        self.service.handled(self.finish())
        self.advance(631)
        self.assertEqual([], self.service.poll(self.instant()))

    def test_restore_of_claimed_repeat_never_replays(self):
        self.service.put(replace(self.timer, repeat=True))
        self.service.handled(self.finish())
        self.advance(30)
        self.assertEqual([], self.restore().poll(self.instant()))

    def test_dst_and_zone_conversion_preserve_duration(self):
        self.start()
        utc = self.instant().value
        # Different civil representations of the same instant, including
        # offsets used around daylight-saving changes, cannot alter a duration.
        for hours in (-5, -4, 0, 3, 12):
            local = Instant(utc.astimezone(timezone(timedelta(hours=hours))))
            self.assertEqual([], self.service.poll(local))
            self.assertEqual(60 * 10**9, self.service.remaining(self.identity))

    def outputs(self, settings=None):
        scheduler = AlertScheduler(self.instant, settings, on_discard=self.service.handled)
        audio, speech = FakeOutput(), FakeOutput()
        presenter = AlertPresenter(scheduler, audio, speech, language_provider=lambda: "en", on_claim=self.service.handled)
        return scheduler, presenter, audio, speech

    def test_timer_sound_and_speech_are_serial_and_auto_advance_queue(self):
        first = self.finish()
        second_timer = Countdown.create("Second", 1, action=AlertAction.SPEECH)
        self.service.put(second_timer)
        self.service.transition(second_timer.timer_id, "start")
        self.advance(1)
        second = next(e for e in self.service.poll(self.instant()) if e.metadata["timer_id"] == second_timer.timer_id)
        scheduler, presenter, audio, speech = self.outputs()
        scheduler.schedule_many([first, second])
        presenter.present_next()
        self.assertEqual([], speech.calls)
        audio.started()
        audio.finished(OutputResult(True, True))
        self.assertEqual(1, len(speech.calls))
        speech.started()
        speech.finished(OutputResult(True, True))
        self.assertEqual(2, len(speech.calls))
        speech.started()
        speech.finished(OutputResult(True, True))
        self.assertIsNone(presenter.current)

    def test_prayer_preempts_timer_and_preserves_name_announcement(self):
        timer = self.finish()
        scheduler, presenter, audio, speech = self.outputs()
        scheduler.schedule(timer)
        presenter.present_next()
        audio.started()
        old_finished = audio.finished
        prayer = AlertEvent("urgent", T.PRAYER_TIME, self.instant(), action=AlertAction.SPEECH)
        scheduler.schedule(prayer)
        # Use a deterministic formatter for the unrelated prayer fixture.
        presenter._format = lambda event, language: event.metadata.get("name", "Prayer")
        presenter.present_next()
        self.assertEqual("urgent", presenter.current.event_id)
        self.assertEqual(1, audio.cancelled)
        old_finished(OutputResult(True, False, True))
        self.assertEqual("urgent", presenter.current.event_id)
        speech.started()
        speech.finished(OutputResult(True, True))
        self.assertEqual(T.COUNTDOWN, presenter.current.event_type)
        self.assertEqual("Reading", speech.calls[-1])
        self.assertEqual(1, self.service.rows[self.identity]["attempt"])

    def test_disable_while_timer_audio_is_playing_cancels_output(self):
        settings = AwqatiSettings()
        scheduler, presenter, audio, speech = self.outputs(lambda: settings)
        scheduler.schedule(self.finish())
        presenter.present_next()
        settings.general.all_automatic_alerts_enabled = False
        presenter.present_next()
        self.assertIsNone(presenter.current)
        self.assertEqual(1, audio.cancelled)
        self.assertEqual("finished", self.service.rows[self.identity]["state"])

    def test_quiet_hours_default_bypass_and_individual_opt_in(self):
        settings = AwqatiSettings()
        settings.general.quiet_hours.enabled = True
        settings.general.quiet_hours.start.hour = 0
        settings.general.quiet_hours.end.hour = 23
        event = self.finish()
        scheduler, presenter, audio, speech = self.outputs(settings)
        self.assertFalse(scheduler._quiet(event, self.instant()))
        self.service.put(replace(self.timer, obey_quiet_hours=True))
        self.service.transition(self.identity, "restart")
        self.advance(60)
        event = self.service.poll(self.instant())[0]
        self.assertTrue(scheduler._quiet(event, self.instant()))
        scheduler.schedule(event)
        self.assertIsNone(scheduler.claim_for_presentation())
        self.assertTrue(self.service.rows[self.identity]["ack"])

    def control(self):
        # Run the actual controller methods with platform output replaced.
        path = ROOT / "addon/globalPlugins/awqati/nvda_adapter/countdown_control.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        messages = []
        ns = {"ui": SimpleNamespace(message=messages.append), "_": lambda text: text,
            "wx": SimpleNamespace(MessageBox=lambda *a, **kw: 0, YES=1, YES_NO=2, NO_DEFAULT=4, ICON_QUESTION=8),
            "gui": SimpleNamespace(mainFrame=None)}
        from awqati.nvda_adapter.audio_service import AudioService
        from awqati.application.countdown_ticking import TickPlan
        ns["AudioService"] = AudioService
        from awqati.nvda_adapter.countdown_formatter import STATE_LABELS, spoken
        ns.update(AlertEventType=T, STATE_LABELS=STATE_LABELS, spoken=spoken)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), ns)
        control = ns["CountdownControl"].__new__(ns["CountdownControl"])
        control.service, control.selected, control.closed, control.dialog = self.service, self.identity, False, None
        scheduler, presenter, audio, speech = self.outputs()
        control.runtime = SimpleNamespace(scheduler=scheduler, presenter=presenter)
        control.addon_root = ROOT / "addon/globalPlugins/awqati"
        control._feedback_generation, control._deferred_message = 0, None
        control.tick_audio = SimpleNamespace(cancel=lambda: None)
        control.tick_plan = TickPlan()
        control.feedback_audio = SimpleNamespace(cancel=lambda: None,
            play_preview=lambda kind, path, started, finished: finished(OutputResult(True, True)) or True)
        return control, messages, ns

    def test_controller_stop_sound_acknowledges_only_selected_timer(self):
        event = self.finish()
        control, messages, ns = self.control()
        control.runtime.scheduler.schedule(event)
        control.runtime.presenter.present_next()
        control.stop_alert()
        self.assertIsNone(control.runtime.presenter.current)
        self.assertEqual("finished", self.service.rows[self.identity]["state"])
        self.assertTrue(self.service.rows[self.identity]["ack"])
        self.assertIn("stopped", messages[-1])

    def test_controller_stale_selection_never_targets_another_timer(self):
        control, messages, ns = self.control()
        self.service.delete(self.identity)
        other = Countdown.create("Other", 10)
        self.service.put(other)
        control.toggle()
        self.assertEqual("ready", self.service.rows[other.timer_id]["state"])
        self.assertIn("Select", messages[-1])

    def test_controller_restart_cancelled_confirmation_does_not_change_progress(self):
        self.start()
        self.advance(20)
        control, messages, ns = self.control()
        control.restart()
        self.assertEqual(40 * 10**9, self.service.remaining(self.identity))
        self.assertEqual([], messages)

    def test_controller_storage_failure_never_announces_success(self):
        control, messages, ns = self.control()
        self.repo.fail = True
        control.toggle()
        self.assertNotIn("started", messages[-1])
        self.assertEqual("ready", self.service.rows[self.identity]["state"])

    def test_stop_deferred_timer_does_not_cancel_higher_priority_alert(self):
        event = self.finish()
        control, messages, ns = self.control()
        runtime = control.runtime
        runtime.scheduler.schedule(event)
        runtime.presenter.present_next()
        runtime.scheduler.schedule(AlertEvent("personal", T.PERSONAL_ALARM, self.instant(),
            action=AlertAction.SPEECH, metadata={"name": "Personal", "duration": 60}))
        runtime.presenter.present_next()
        self.assertEqual(T.PERSONAL_ALARM, runtime.presenter.current.event_type)
        self.assertTrue(runtime.scheduler.has_pending("timers." + self.identity))
        control.stop_alert()
        self.assertFalse(runtime.scheduler.has_pending("timers." + self.identity))
        self.assertEqual(T.PERSONAL_ALARM, runtime.presenter.current.event_type)
        self.assertEqual("finished", self.service.rows[self.identity]["state"])

    def manager(self):
        path = ROOT / "addon/globalPlugins/awqati/nvda_adapter/countdown_dialog.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CountdownDialog")
        from awqati.nvda_adapter.countdown_formatter import STATE_LABELS
        ns = {"wx": SimpleNamespace(Dialog=object), "_": lambda text: text,
            "STATE_LABELS": STATE_LABELS, "duration": str}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), ns)
        manager = ns["CountdownDialog"].__new__(ns["CountdownDialog"])

        class List:
            def IsSelected(self, index): return self.GetItemData(index) == getattr(self, "selection", None)
            def Select(self, index, selected=True):
                if selected: self.selection = self.GetItemData(index)
                elif self.IsSelected(index): self.selection = None
            def Focus(self, index): self.focus = self.GetItemData(index)
            def __init__(self):
                self.rows, self.sorts, self.inserts, self.deletes = [], 0, 0, 0
            def GetItemCount(self): return len(self.rows)
            def GetItemData(self, index): return self.rows[index][0]
            def SetItemData(self, index, value): self.rows[index][0] = value
            def GetItemText(self, index, column): return self.rows[index][1][column]
            def SetItem(self, index, column, value): self.rows[index][1][column] = value
            def InsertItem(self, index, value):
                self.inserts += 1
                self.rows.insert(index, [None, [value, "", "", "", ""]])
                return index
            def DeleteItem(self, index):
                self.deletes += 1
                del self.rows[index]
            def SortItems(self, callback):
                self.sorts += 1
                self.rows.sort(key=cmp_to_key(lambda a, b: callback(a[0], b[0])))
        manager.control = SimpleNamespace(service=self.service, selected=self.identity)
        manager.list, manager.tokens, manager.next_token, manager.order = List(), {}, 1, None
        manager.update_buttons = lambda: None
        return manager

    def test_manager_updates_rows_without_rebuilding_or_repeated_sorting(self):
        manager = self.manager()
        self.start()
        manager.refresh()
        for _ in range(10):
            self.advance(1)
            manager.refresh()
        self.assertEqual((1, 1, 0), (manager.list.inserts, manager.list.sorts, manager.list.deletes))
        self.assertEqual(self.identity, manager.control.selected)

    def test_manager_reorder_keeps_selected_identity_and_same_rows(self):
        other = Countdown.create("Other", 120)
        self.service.put(other)
        self.start()
        self.service.transition(other.timer_id, "start")
        manager = self.manager()
        manager.refresh()
        self.assertEqual(manager.tokens[self.identity], manager.list.GetItemData(0))
        self.service.transition(self.identity, "pause")
        manager.refresh()
        self.assertEqual(manager.tokens[other.timer_id], manager.list.GetItemData(0))
        self.assertEqual(self.identity, manager.control.selected)
        self.assertEqual((2, 0), (manager.list.inserts, manager.list.deletes))

    def test_countdown_query_has_no_milliseconds(self):
        from awqati.nvda_adapter.countdown_formatter import spoken
        self.assertEqual("1 second", spoken(123456789, lambda text: text))

    def test_invalid_state_file_is_not_silently_replaced(self):
        before = deepcopy(self.repo.raw)
        self.repo.raw["timers"][0]["runtime"]["state"] = "invalid"
        with self.assertRaises(ValueError):
            self.restore()
        self.assertEqual("invalid", self.repo.raw["timers"][0]["runtime"]["state"])
        self.assertEqual(before["timers"][0]["definition"], self.repo.raw["timers"][0]["definition"])

    def test_timer_discard_storage_failure_cannot_block_unrelated_alerts(self):
        event = self.finish()
        self.repo.fail = True
        path = ROOT / "addon/globalPlugins/awqati/nvda_adapter/runtime.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_discard")
        ns = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), ns)
        runtime = SimpleNamespace(countdowns=self.service, alarms=SimpleNamespace(discarded=lambda *args: None))
        scheduler = AlertScheduler(self.instant, on_discard=lambda event, reason: ns["_discard"](runtime, event, reason))
        scheduler.schedule(event)
        self.advance(601)
        prayer = AlertEvent("prayer", T.PRAYER_TIME, self.instant())
        self.assertTrue(scheduler.schedule(prayer))
        self.assertEqual("prayer", scheduler.claim_for_presentation().event_id)
        self.assertTrue(self.service.storage_error)


if __name__ == "__main__":
    unittest.main()
