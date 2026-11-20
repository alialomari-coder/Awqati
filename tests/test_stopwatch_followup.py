"""Current-lap definitions, ordered confirmations and dev7 preference preservation."""
import ast
from copy import deepcopy
import hashlib
import json
import marshal
from pathlib import Path
import sys
import tempfile
import threading
from types import CodeType, FunctionType, SimpleNamespace
import unittest
import weakref

from tests.test_stopwatch import ROOT, Clock, MemoryRepository, Stopwatch, controller_driver
from awqati.application.alert_presenter import OutputResult
from awqati.infrastructure.stopwatch import StopwatchRepository
from legacy_stopwatch_gestures import StopwatchGestures


class CurrentLapTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.repo = Clock(), MemoryRepository()
        self.watch = Stopwatch(self.clock, self.repo)

    def test_before_start(self):
        self.assertEqual(0, self.watch.current_lap_ns())

    def test_before_first_lap_is_elapsed(self):
        self.watch.toggle()
        self.clock.advance(25)
        self.assertEqual(25 * 10**9, self.watch.current_lap_ns())

    def test_after_first_saved_lap(self):
        self.watch.toggle()
        self.clock.advance(120)
        self.watch.record_lap()
        self.assertEqual(0, self.watch.current_lap_ns())
        self.clock.advance(25)
        self.assertEqual(25 * 10**9, self.watch.current_lap_ns())

    def test_after_several_laps_and_queries_do_not_write(self):
        self.watch.toggle()
        for duration in (12, 31, 85):
            self.clock.advance(duration)
            self.watch.record_lap()
        previous, writes, laps = deepcopy(self.repo.raw), self.repo.writes, tuple(self.watch.laps)
        self.clock.advance(25)
        for _ in range(10):
            self.assertEqual(25 * 10**9, self.watch.current_lap_ns())
        self.assertEqual((previous, writes, laps), (self.repo.raw, self.repo.writes, tuple(self.watch.laps)))

    def test_paused_current_lap_frozen(self):
        self.watch.toggle()
        self.clock.advance(70)
        self.watch.toggle()
        self.clock.advance(180)
        self.assertEqual(70 * 10**9, self.watch.current_lap_ns())

    def test_resume_continues_current_lap(self):
        self.watch.toggle()
        self.clock.advance(120)
        self.watch.record_lap()
        self.clock.advance(30)
        self.watch.toggle()
        self.clock.advance(180)
        self.watch.toggle()
        self.clock.advance(40)
        self.assertEqual(70 * 10**9, self.watch.current_lap_ns())

    def test_reset_clears_current_lap(self):
        self.watch.toggle()
        self.clock.advance(12)
        self.watch.record_lap()
        self.clock.advance(7)
        self.watch.toggle()
        self.watch.reset(True)
        self.assertEqual(0, self.watch.current_lap_ns())

    def test_two_minutes_pause_three_resume_two_equals_four(self):
        self.watch.toggle()
        self.clock.advance(120)
        self.watch.toggle()
        self.clock.advance(180)
        self.watch.toggle()
        self.clock.advance(120)
        self.assertEqual((240 * 10**9, 240 * 10**9), (self.watch.elapsed_ns(), self.watch.current_lap_ns()))

    def test_sum_of_saved_laps_and_current_equals_elapsed_exactly(self):
        self.watch.toggle()
        for index in range(100):
            self.clock.ns += 123456789
            if index % 3 == 0:
                self.watch.record_lap()
            if index % 5 == 0:
                self.watch.toggle()
                self.clock.advance(180)
                self.watch.toggle()
            self.assertEqual(self.watch.elapsed_ns(), sum(lap.duration_ns for lap in self.watch.laps) + self.watch.current_lap_ns())

    def test_current_lap_after_restore_is_saved_unfinished_part(self):
        self.watch.toggle()
        self.clock.advance(120)
        self.watch.record_lap()
        self.clock.advance(70)
        self.watch.checkpoint()
        self.clock.advance(999)
        restored = Stopwatch(self.clock, self.repo)
        self.assertEqual(("paused", 70 * 10**9), (restored.state, restored.current_lap_ns()))


class OrderedFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.control, self.clock, self.repo, self.ns, self.messages, self.clipboard, self.tones, self.confirms = controller_driver()
        self.control.mode = 2
        self.callbacks = []
        def deferred_tone(action, callback):
            self.tones.append(action)
            self.callbacks.append(callback)
            return True
        self.control._play_tone = deferred_tone

    def finish(self, index=-1, result=None):
        self.callbacks[index](result or OutputResult(True, True))

    def test_start_measures_immediately_but_speaks_only_after_tone(self):
        self.control.toggle()
        self.assertEqual("running", self.control.watch.state)
        self.assertIn("start", self.tones)
        self.assertEqual([], self.messages)
        self.clock.advance(2.2)
        self.finish()
        self.assertEqual(["Stopwatch started."], self.messages)
        self.assertEqual(2200000000, self.control.watch.elapsed_ns())

    def test_new_operation_suppresses_old_queued_speech(self):
        self.control.toggle()
        self.clock.advance(1)
        self.control.toggle()
        self.finish(0)
        self.assertEqual([], self.messages)
        self.finish(1)
        self.assertEqual(["Stopwatch paused."], self.messages)

    def test_query_invalidates_success_and_remains_spoken(self):
        self.control.toggle()
        self.clock.advance(25)
        self.control.current_lap()
        self.finish()
        self.assertEqual(["Current lap: 25 seconds."], self.messages)

    def test_failed_new_operation_also_invalidates_old_success(self):
        self.control.toggle()
        self.repo.fail = True
        self.control.lap()
        self.finish()
        self.assertEqual(["The stopwatch change could not be saved. The previous state was preserved."], self.messages)
        self.assertEqual([], self.control.watch.laps)

    def test_preview_or_stop_invalidates_pending_success(self):
        self.control.toggle()
        self.control.cancel_feedback()
        self.finish()
        self.assertEqual([], self.messages)

    def test_close_invalidates_even_previously_completed_queued_callback(self):
        self.control.toggle()
        self.control.close()
        self.finish()
        self.assertEqual([], self.messages)
        before = self.control.watch.state
        self.control.toggle()
        self.assertEqual(before, self.control.watch.state)

    def test_automatic_audio_cancellation_suppresses_late_speech(self):
        self.control.toggle()
        self.finish(result=OutputResult(True, False, cancelled=True))
        self.assertEqual([], self.messages)

    def test_alert_claim_before_queued_completion_suppresses_speech(self):
        self.control.toggle()
        self.control.runtime.presenter.current = object()
        self.finish()
        self.assertEqual([], self.messages)

    def test_duplicate_completion_does_not_repeat_success(self):
        self.control.toggle()
        self.finish()
        self.finish()
        self.assertEqual(["Stopwatch started."], self.messages)

    def test_runtime_cancel_invalidates_completion_even_after_alert_has_ended(self):
        self.control.toggle()
        self.control.cancel()  # Existing runtime preview hook on any alert claim.
        self.control.runtime.presenter.current = None
        self.finish()  # Completion was queued before the cancellation.
        self.assertEqual([], self.messages)
        self.assertEqual("running", self.control.watch.state)

    def test_lifecycle_close_only_checkpoints_once(self):
        self.control.toggle()
        self.control.close()
        writes = self.repo.writes
        self.control.close()  # Plugin close followed by runtime preview close.
        self.assertEqual(writes, self.repo.writes)

    def test_audio_failure_falls_back_to_truthful_saved_success(self):
        self.control.toggle()
        self.finish(result=OutputResult(False, False, error=OSError("no output device")))
        self.assertEqual(["Stopwatch started."], self.messages)
        self.assertEqual("running", self.control.watch.state)

    def test_cancelled_reset_has_no_success_output(self):
        self.control.toggle()
        self.control.toggle()
        self.messages.clear(); self.tones.clear()
        self.control.reset()
        for callback in self.callbacks:
            callback(OutputResult(True, True))
        self.assertEqual(([], ["cancel"], "paused"), (self.messages, self.tones, self.control.watch.state))

    def test_lap_confirmation_uses_captured_lap_not_following_lap(self):
        self.control.toggle()
        self.clock.advance(120)
        self.control.lap()
        self.clock.advance(180)
        self.finish()
        self.assertEqual("A new lap has been created. Lap 1 completed in 2 minutes.", self.messages[-1])
        self.assertNotIn("Total", self.messages[-1])
        self.assertEqual(180 * 10**9, self.control.watch.current_lap_ns())

    def test_real_shared_audio_pipeline_finishes_before_queued_speech_without_blocking_caller(self):
        from awqati.infrastructure import SoundFileService
        from awqati.nvda_adapter.audio_service import AudioService
        root = ROOT / "addon/globalPlugins/awqati"
        idle_entered, release, completion_queued = threading.Event(), threading.Event(), threading.Event()
        queued, workers = [], []
        class Player:
            def feed(self, data): workers.append(threading.get_ident())
            def idle(self):
                idle_entered.set()
                release.wait(3)
            def stop(self): release.set()
            def close(self): pass
        def dispatch(callback, *args):
            queued.append((callback, args))
            if args and isinstance(args[0], OutputResult):
                completion_queued.set()
        audio = AudioService(SoundFileService(root, root), player_factory=lambda *args: Player(), dispatch=dispatch)
        self.control.audio, self.control.addon_root = audio, root
        self.ns["AudioService"] = AudioService
        self.control._play_tone = type(self.control)._play_tone.__get__(self.control)
        try:
            self.control.toggle()
            self.assertEqual("running", self.control.watch.state)
            self.assertTrue(idle_entered.wait(3))
            self.assertFalse(release.is_set())
            self.assertNotIn(threading.get_ident(), workers)
            self.assertEqual([], self.messages)
            self.clock.advance(2.2)
            self.assertEqual(2200000000, self.control.watch.elapsed_ns())
            release.set()
            self.assertTrue(completion_queued.wait(3))
            self.assertEqual([], self.messages)  # Speech still belongs to NVDA's main thread.
            for callback, args in queued:
                callback(*args)
            self.assertEqual(["Stopwatch started."], self.messages)
        finally:
            release.set()
            audio.cancel()


class MessagesAndPreferencesTests(unittest.TestCase):
    def test_short_success_messages_in_arabic_and_english(self):
        expected = {
            "en": ["Stopwatch started.", "A new lap has been created. Lap 1 completed in 2 minutes.", "Stopwatch paused.", "Stopwatch resumed.", "Stopwatch reset."],
            "ar": ["بدأت ساعة الإيقاف.", "تم إنشاء جولة جديدة. مدة الجولة الأولى المنتهية: دقيقتان.", "تم إيقاف الساعة مؤقتا.", "تم الاستئناف.", "تم تصفير ساعة الإيقاف."],
        }
        for language in ("ar", "en"):
            with self.subTest(language=language):
                control, clock, repo, ns, messages, copied, tones, confirms = controller_driver(language)
                control.mode = 1
                control.toggle()
                clock.advance(120)
                control.lap()
                control.toggle()
                control.toggle()
                control.toggle()
                messages.pop()  # Second pause is a separate, already checked action.
                ns["wx"].MessageBox = lambda *args: ns["wx"].YES
                control.reset()
                self.assertEqual(expected[language], messages)

    def test_current_lap_query_idle_running_paused_reset_all_modes_both_languages(self):
        for language in ("ar", "en"):
            for mode in range(4):
                with self.subTest(language=language, mode=mode):
                    control, clock, repo, ns, messages, copied, tones, confirms = controller_driver(language)
                    control.mode = mode
                    control.current_lap()
                    self.assertEqual("ساعة الإيقاف لم تبدأ بعد." if language == "ar" else "The stopwatch has not started yet.", messages[-1])
                    control.toggle()
                    clock.advance(25)
                    control.current_lap()
                    self.assertEqual("الجولة الجارية: 25 ثانية." if language == "ar" else "Current lap: 25 seconds.", messages[-1])
                    control.lap()
                    clock.advance(70)
                    control.toggle()
                    clock.advance(180)
                    control.current_lap()
                    self.assertEqual("الجولة الجارية: دقيقة واحدة و10 ثوانٍ." if language == "ar" else "Current lap: 1 minute, 10 seconds.", messages[-1])
                    before = deepcopy(repo.raw)
                    control.current_lap()
                    self.assertEqual(before, repo.raw)
                    ns["wx"].MessageBox = lambda *args: ns["wx"].YES
                    control.reset()
                    control.current_lap()
                    self.assertEqual("ساعة الإيقاف لم تبدأ بعد." if language == "ar" else "The stopwatch has not started yet.", messages[-1])

    def test_errors_remain_audible_in_all_modes_and_both_languages(self):
        for language in ("ar", "en"):
            for mode in range(4):
                with self.subTest(language=language, mode=mode):
                    control, clock, repo, ns, messages, copied, tones, confirms = controller_driver(language)
                    control.mode = mode
                    control.lap()
                    self.assertIn("جولة" if language == "ar" else "lap", messages[-1])
                    control.toggle()
                    control.reset()
                    self.assertIn("أوقف" if language == "ar" else "Pause", messages[-1])
                    messages.clear()
                    repo.fail = True
                    control.toggle()
                    self.assertEqual(1, len(messages))
                    self.assertNotIn("Stopwatch paused.", messages)

    def test_new_default_and_saved_modes_preserved_without_writes(self):
        # Exercise the real production constructor in a temporary NVDA-like
        # data directory. No personal NVDA configuration is opened or modified.
        for saved in (None, 0, 1, 2, 3):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                path = root / "stopwatch_preferences.json"
                original = None
                if saved is not None:
                    path.write_text(json.dumps({"version": 1, "mode": saved}), encoding="utf-8")
                    original = path.read_bytes()
                driver = controller_driver()
                ns, cls = driver[3], type(driver[0])
                ns.update(Path=Path, InterruptClock=Clock, Stopwatch=Stopwatch, StopwatchRepository=StopwatchRepository,
                    AudioService=lambda files: type("Audio", (), {})(), wx=SimpleNamespace(CallAfter=lambda callback, *args: callback(*args)))
                runtime = SimpleNamespace(audio=SimpleNamespace(files=object()), previews=set())
                control = cls(root, runtime, ROOT / "addon/globalPlugins/awqati")
                self.assertEqual(2 if saved is None else saved, control.mode)
                self.assertIn(control, runtime.previews)
                self.assertEqual(original, path.read_bytes() if path.exists() else None)

    def test_approved_sounds_and_repeat_mechanism_are_byte_identical_to_dev7(self):
        import subprocess
        relatives = ["addon/globalPlugins/awqati/nvda_adapter/stopwatch_gestures.py",
            "tools/build_stopwatch_sounds.py"]
        relatives += [str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "addon/globalPlugins/awqati/sounds/stopwatch").glob("*.wav")]
        for relative in relatives:
            with self.subTest(relative=relative):
                original = subprocess.check_output(["git", "show", "320be27:" + relative], cwd=ROOT)
                path = ROOT / relative
                if path.suffix == ".wav":
                    from sound_history import assert_updated_stopwatch_sound
                    assert_updated_stopwatch_sound(self, original, path)
                elif relative == "tools/build_stopwatch_sounds.py":
                    def patterns(source):
                        tree = ast.parse(source)
                        return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Name) and t.id == "PATTERNS" for t in n.targets))
                    self.assertEqual(patterns(original), patterns(path.read_bytes()))
                else:
                    self.assertEqual(hashlib.sha256(original).digest(), hashlib.sha256(__import__('multipress_history').legacy_gestures_bytes() if relative.endswith('stopwatch_gestures.py') else path.read_bytes()).digest())


class NativeFollowupDispatchTests(unittest.TestCase):
    @unittest.skipUnless(Path(r"C:\Program Files\NVDA\library.zip").exists() and sys.version_info[:2] == (3, 13), "Installed native CPython 3.13 NVDA engine")
    def test_production_scripts_with_native_engine_no_unintended_operations(self):
        import zipfile
        with zipfile.ZipFile(r"C:\Program Files\NVDA\library.zip") as archive:
            code = marshal.loads(archive.read("scriptHandler.pyc")[16:])
        native = {item.co_name: item for item in code.co_consts if isinstance(item, CodeType)}
        source = ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        original = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        original.body = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in ("_press", "script_stopwatchInfo", "script_stopwatchLaps")]
        original.bases = []
        for method in original.body:
            method.decorator_list = []
        space = {"compat": __import__("awqati.nvda_adapter.compat", fromlist=["script_repeat_count"])}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])), str(source), "exec"), space)
        for language in ("ar", "en"):
            for script_name in ("script_stopwatchInfo", "script_stopwatchLaps"):
                for presses in (1, 2, 3):
                    with self.subTest(language=language, script=script_name, presses=presses):
                        control, clock, repo, ns, messages, copied, tones, confirms = controller_driver(language)
                        control.mode = 3
                        control.toggle()
                        clock.advance(25)
                        now, jobs, errors = [100.0], [], []
                        namespace = dict(_lastScriptRef=None, _isScriptRunning=False, _lastScriptTime=0, _lastScriptCount=0,
                            time=SimpleNamespace(time=lambda: now[0]), weakref=weakref,
                            config=SimpleNamespace(conf={"keyboard": {"multiPressTimeout": 500}}),
                            willSayAllResume=lambda gesture: False, log=SimpleNamespace(exception=lambda *args: errors.append(args)))
                        execute = FunctionType(native["executeScript"], namespace)
                        repeat = FunctionType(native["getLastScriptRepeatCount"], namespace)
                        def schedule(delay, callback):
                            self.assertEqual(500, delay)
                            jobs.append(callback)
                            return SimpleNamespace(cancel=lambda: None)
                        plugin = space["GlobalPlugin"]()
                        plugin._stopwatch = control
                        original_repeat = space["compat"].script_repeat_count
                        self.addCleanup(setattr, space["compat"], "script_repeat_count", original_repeat)
                        space["compat"].script_repeat_count = repeat
                        for _ in range(presses):
                            now[0] += 0.1
                            execute(getattr(plugin, script_name), SimpleNamespace(displayName=script_name))
                        self.assertEqual("paused" if script_name == "script_stopwatchInfo" else "running", control.watch.state)
                        self.assertEqual(0 if script_name == "script_stopwatchInfo" else 1, len(control.watch.laps))
                        for job in jobs:
                            job()
                        self.assertEqual([], errors)
                        if script_name == "script_stopwatchInfo":
                            self.assertEqual("paused", control.watch.state)
                            self.assertEqual(0, len(control.watch.laps))
                        else:
                            self.assertEqual("running", control.watch.state)
                            self.assertEqual(1, len(control.watch.laps))
                            self.assertEqual([], jobs)


if __name__ == "__main__":
    unittest.main()
