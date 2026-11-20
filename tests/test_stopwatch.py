"""Stopwatch timing, persistence, native-repeat selection and audio contracts.

Fake clocks replace waits; no sleep/keyboard/live NVDA acceptance is implied.
"""
import ast
from copy import deepcopy
import gettext
import io
import marshal
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import CodeType, FunctionType, SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import weakref
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
sys.path.insert(0, str(ROOT))
from awqati.application.stopwatch import Stopwatch, MAX_LAPS
from awqati.infrastructure.stopwatch import StopwatchRepository, InterruptClock
from awqati.nvda_adapter.stopwatch_formatter import numeric, spoken, results
from legacy_stopwatch_gestures import StopwatchGestures
from tools.build_stopwatch_sounds import PATTERNS, RATE, pcm


class MemoryRepository:
    def __init__(self, raw=None):
        self.raw, self.writes, self.fail = deepcopy(raw), 0, False

    def load(self):
        return deepcopy(self.raw)

    def save(self, raw):
        if self.fail:
            raise OSError("disk failure")
        self.raw = deepcopy(raw)
        self.writes += 1


class Clock:
    def __init__(self):
        self.ns = 100000000000

    def __call__(self):
        return self.ns

    def advance(self, seconds):
        self.ns += round(seconds * 10**9)


class StopwatchTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.repo = Clock(), MemoryRepository()
        self.watch = Stopwatch(self.clock, self.repo)

    def test_initial_zero(self):
        self.assertEqual(("idle", 0, []), (self.watch.state, self.watch.elapsed_ns(), self.watch.laps))

    def test_start_before_storage_latency(self):
        save = self.repo.save
        def slow_save(raw):
            self.clock.advance(2.2)
            save(raw)
        self.repo.save = slow_save
        self.assertEqual("start", self.watch.toggle())
        self.assertEqual(2200000000, self.watch.elapsed_ns())

    def test_pause(self):
        self.watch.toggle()
        self.clock.advance(5.25)
        self.assertEqual("pause", self.watch.toggle())
        self.clock.advance(100)
        self.assertEqual(5250000000, self.watch.elapsed_ns())

    def test_resume(self):
        self.watch.toggle()
        self.clock.advance(5)
        self.watch.toggle()
        self.clock.advance(90)
        self.assertEqual("resume", self.watch.toggle())
        self.clock.advance(2)
        self.assertEqual(7000000000, self.watch.elapsed_ns())

    def test_running_query_is_current(self):
        self.watch.toggle()
        self.clock.advance(0.123456789)
        self.assertEqual(123456789, self.watch.elapsed_ns())
        self.assertEqual(1, self.repo.writes)

    def test_lap_durations_and_total(self):
        self.watch.toggle()
        self.clock.advance(3)
        a = self.watch.record_lap()
        self.clock.advance(7)
        b = self.watch.record_lap()
        self.assertEqual((1, 3000000000, 3000000000), (a.number, a.duration_ns, a.total_ns))
        self.assertEqual((2, 7000000000, 10000000000), (b.number, b.duration_ns, b.total_ns))
        self.assertEqual("running", self.watch.state)

    def test_lap_captured_before_slow_save(self):
        self.watch.toggle()
        self.clock.advance(1)
        save = self.repo.save
        def slow(raw):
            self.clock.advance(2.2)
            save(raw)
        self.repo.save = slow
        self.assertEqual(1000000000, self.watch.record_lap().total_ns)
        self.assertEqual(3200000000, self.watch.elapsed_ns())

    def test_lap_after_pause_excludes_paused_time(self):
        self.watch.toggle()
        self.clock.advance(3)
        self.watch.record_lap()
        self.watch.toggle()
        self.clock.advance(900)
        self.watch.toggle()
        self.clock.advance(4)
        self.assertEqual(4000000000, self.watch.record_lap().duration_ns)

    def test_lap_in_idle_rejected(self):
        with self.assertRaises(ValueError):
            self.watch.record_lap()
        self.assertEqual(0, self.repo.writes)

    def test_lap_when_paused_rejected(self):
        self.watch.toggle()
        self.watch.toggle()
        with self.assertRaises(ValueError):
            self.watch.record_lap()

    def test_reset_running_rejected_even_if_confirmed(self):
        self.watch.toggle()
        with self.assertRaises(ValueError):
            self.watch.reset(True)
        self.assertEqual("running", self.watch.state)

    def test_reset_cancel_retains_laps_and_time(self):
        self.watch.toggle()
        self.clock.advance(12)
        self.watch.record_lap()
        self.watch.toggle()
        raw = deepcopy(self.repo.raw)
        self.assertFalse(self.watch.reset(False))
        self.assertEqual(raw, self.repo.raw)
        self.assertEqual(1, len(self.watch.laps))

    def test_reset_confirmed(self):
        self.watch.toggle()
        self.clock.advance(12)
        self.watch.record_lap()
        self.watch.toggle()
        self.assertTrue(self.watch.reset(True))
        self.assertEqual(("idle", 0, []), (self.watch.state, self.watch.elapsed_ns(), self.watch.laps))

    def test_idle_reset_is_noop(self):
        self.assertFalse(self.watch.reset(True))

    def test_paused_restore(self):
        self.watch.toggle()
        self.clock.advance(9)
        self.watch.record_lap()
        self.watch.toggle()
        self.clock.advance(100)
        restored = Stopwatch(self.clock, self.repo)
        self.assertEqual(("paused", 9000000000, 1), (restored.state, restored.elapsed_ns(), len(restored.laps)))
        self.assertFalse(restored.restored_running)

    def test_running_restore_is_paused_not_guessed(self):
        self.watch.toggle()
        self.clock.advance(9)
        self.watch.record_lap()
        self.clock.advance(1000)
        restored = Stopwatch(self.clock, self.repo)
        self.assertTrue(restored.restored_running)
        self.assertEqual(("paused", 9000000000), (restored.state, restored.elapsed_ns()))
        restored.toggle()
        self.clock.advance(2)
        self.assertEqual(11000000000, restored.elapsed_ns())

    def test_checkpoint_at_clean_shutdown(self):
        self.watch.toggle()
        self.clock.advance(8)
        self.watch.checkpoint()
        self.assertEqual(8000000000, Stopwatch(self.clock, self.repo).elapsed_ns())

    def test_wall_clock_changes_irrelevant(self):
        self.watch.toggle()
        with patch("time.time", return_value=-99999999999):
            self.clock.advance(15)
            self.assertEqual(15000000000, self.watch.elapsed_ns())

    def test_sleep_inclusive_source_jump(self):
        self.watch.toggle()
        self.clock.advance(8 * 3600)  # Simulated source advancing during sleep.
        self.assertEqual(28800000000000, self.watch.elapsed_ns())

    def test_long_measurement_and_repeated_pause_no_drift(self):
        self.watch.toggle()
        self.clock.advance(3600 * 24 * 365)
        for index in range(100):
            self.clock.ns += 123456789
            self.watch.toggle()
            self.clock.advance(100)
            self.watch.toggle()
        self.assertEqual(31536000000000000 + 100 * 123456789, self.watch.elapsed_ns())

    def test_many_laps(self):
        self.watch.toggle()
        for index in range(1200):
            self.clock.advance(0.001)
            self.watch.record_lap()
        self.assertEqual(1200, len(self.watch.laps))
        self.assertEqual(1200000000, self.watch.laps[-1].total_ns)

    def test_safety_limit(self):
        self.watch.toggle()
        with patch("awqati.application.stopwatch.MAX_LAPS", 2):
            self.watch.record_lap()
            self.watch.record_lap()
            with self.assertRaises(ValueError):
                self.watch.record_lap()

    def test_negative_duration_prevented(self):
        self.watch.toggle()
        self.clock.advance(-5)
        self.assertEqual(0, self.watch.elapsed_ns())

    def test_corrupt_durations_rejected(self):
        self.watch.toggle()
        for invalid in (-1, True, float("nan"), 1.5, "2", 10**25):
            raw = deepcopy(self.repo.raw)
            raw["measurement"]["elapsed_ns"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Stopwatch(self.clock, MemoryRepository(raw))

    def test_inconsistent_lap_rejected(self):
        self.watch.toggle()
        self.clock.advance(1)
        self.watch.record_lap()
        raw = deepcopy(self.repo.raw)
        raw["laps"][0]["duration_ns"] = 500
        with self.assertRaises(ValueError):
            Stopwatch(self.clock, MemoryRepository(raw))

    def test_failed_start_preserves_state(self):
        self.repo.fail = True
        with self.assertRaises(OSError):
            self.watch.toggle()
        self.assertEqual("idle", self.watch.state)

    def test_failed_lap_preserves_results(self):
        self.watch.toggle()
        self.repo.fail = True
        with self.assertRaises(OSError):
            self.watch.record_lap()
        self.assertEqual([], self.watch.laps)

    def test_failed_reset_preserves_results(self):
        self.watch.toggle()
        self.clock.advance(1)
        self.watch.record_lap()
        self.watch.toggle()
        self.repo.fail = True
        with self.assertRaises(OSError):
            self.watch.reset(True)
        self.assertEqual(("paused", 1), (self.watch.state, len(self.watch.laps)))

    def test_numeric_format(self):
        self.assertEqual("00:05:40.250", numeric(340250000000))
        self.assertEqual("123:00:00.000", numeric(123 * 3600 * 10**9))

    def test_english_spoken(self):
        self.assertEqual("5 minutes, 40 seconds, 250 milliseconds", spoken(340250000000, lambda s: s))

    def test_arabic_spoken(self):
        from tests.test_corrective_followup import Translator
        ar = Translator("ar")
        self.assertEqual("خمس دقائق و40 ثانية و250 مللي ثانية", spoken(340250000000, ar))
        self.assertEqual("ثانيتان", spoken(2 * 10**9, ar))

    def test_export_contains_all_results(self):
        self.watch.toggle()
        self.clock.advance(1.25)
        self.watch.record_lap()
        self.clock.advance(2)
        text = results(self.watch, lambda s: s)
        self.assertIn("Total elapsed: 00:00:03.250", text)
        self.assertIn("Lap 1: 00:00:01.250. Total: 00:00:01.250", text)


class PersistenceTests(unittest.TestCase):
    def test_atomic_round_trip_and_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "settings.json").write_text("existing settings")
            repo = StopwatchRepository(path / "stopwatch_state.json")
            watch = Stopwatch(Clock(), repo)
            watch.toggle()
            self.assertEqual("paused", Stopwatch(Clock(), repo).state)
            self.assertEqual("existing settings", (path / "settings.json").read_text())
            self.assertEqual([], list(path.glob("*.tmp")))

    def test_invalid_json_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            path.write_bytes(b"{broken")
            repo = StopwatchRepository(path)
            with self.assertRaises(ValueError):
                repo.load()
            with self.assertRaises(OSError):
                repo.save({})
            self.assertEqual(b"{broken", path.read_bytes())

    def test_failed_replace_preserves_original_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            repo = StopwatchRepository(path)
            repo.save({"a": 1})
            original = path.read_bytes()
            with patch("awqati.infrastructure.stopwatch.os.replace", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    repo.save({"a": 2})
            self.assertEqual(original, path.read_bytes())
            self.assertEqual([path], list(path.parent.iterdir()))

    @unittest.skipUnless(sys.platform == "win32", "Windows API")
    def test_real_windows_source_advances(self):
        clock = InterruptClock()
        values = [clock() for _ in range(100)]
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[0])
        self.assertTrue(all(value % 100 == 0 for value in values))


class GesturesTests(unittest.TestCase):
    def setUp(self):
        self.count, self.jobs, self.calls = 0, [], []
        def schedule(delay, callback):
            job = SimpleNamespace(delay=delay, callback=callback, cancelled=False)
            job.cancel = lambda: setattr(job, "cancelled", True)
            self.jobs.append(job)
            return job
        self.dispatch = StopwatchGestures(schedule, lambda: self.count, lambda: 500)
        self.handlers = tuple(lambda index=index: self.calls.append(index) for index in range(3))

    def send(self, presses):
        for self.count in range(presses):
            self.dispatch.submit(self.handlers)
        self.assertEqual([], self.calls)
        for job in self.jobs:
            job.callback()  # Even a queued cancelled callback must do nothing.

    def test_single(self):
        self.send(1)
        self.assertEqual([0], self.calls)

    def test_double_has_no_first_action(self):
        self.send(2)
        self.assertEqual([1], self.calls)

    def test_triple_has_no_previous_actions(self):
        self.send(3)
        self.assertEqual([2], self.calls)

    def test_fourth_cancels_instead_of_resetting(self):
        self.send(4)
        self.assertEqual([], self.calls)

    def test_shutdown_cancels_even_queued_callback(self):
        self.dispatch.submit(self.handlers)
        self.dispatch.close()
        self.jobs[0].callback()
        self.dispatch.submit(self.handlers)
        self.assertEqual([], self.calls)
        self.assertEqual(1, len(self.jobs))

    def test_callback_cannot_execute_twice(self):
        self.dispatch.submit(self.handlers)
        self.jobs[0].callback()
        self.jobs[0].callback()
        self.assertEqual([0], self.calls)

    def test_uses_configured_timeout(self):
        self.dispatch.timeout = lambda: 817
        self.dispatch.submit(self.handlers)
        self.assertEqual(817, self.jobs[0].delay)

    @unittest.skipUnless(Path(r"C:\Program Files\NVDA\library.zip").exists() and sys.version_info[:2] == (3, 13), "Installed NVDA CPython 3.13 bytecode")
    def test_installed_native_engine_all_three_counts_and_two_maps(self):
        # Production executeScript and getLastScriptRepeatCount code objects,
        # run outside NVDA with minimal dependencies: this is NOT key injection.
        with zipfile.ZipFile(r"C:\Program Files\NVDA\library.zip") as archive:
            code = marshal.loads(archive.read("scriptHandler.pyc")[16:])
        functions = {item.co_name: item for item in code.co_consts if isinstance(item, CodeType)}
        for family in ("info", "laps"):
            for presses in (1, 2, 3):
                with self.subTest(family=family, presses=presses):
                    self.setUp()
                    now = [100.0]
                    errors = []
                    namespace = dict(_lastScriptRef=None, _isScriptRunning=False, _lastScriptTime=0, _lastScriptCount=0,
                        time=SimpleNamespace(time=lambda: now[0]), weakref=weakref,
                        config=SimpleNamespace(conf={"keyboard": {"multiPressTimeout": 500}}),
                        willSayAllResume=lambda gesture: False, log=SimpleNamespace(exception=lambda *args: errors.append(args)))
                    execute = FunctionType(functions["executeScript"], namespace)
                    repeat = FunctionType(functions["getLastScriptRepeatCount"], namespace)
                    self.dispatch.repeat = repeat
                    counts = []
                    def script(gesture):
                        counts.append(repeat())
                        self.dispatch.submit(self.handlers)
                    for index in range(presses):
                        now[0] += 0.1
                        execute(script, SimpleNamespace(displayName=family))
                    self.assertEqual([], errors)
                    self.assertEqual(list(range(presses)), counts)
                    self.assertEqual([], self.calls)
                    for job in self.jobs:
                        job.callback()
                    self.assertEqual([presses - 1], self.calls)


class SoundTests(unittest.TestCase):
    def test_start_exact_durations_frequencies_and_gaps(self):
        self.assertEqual(((440, 500), (None, 100), (550, 500), (None, 100), (660, 1000)), PATTERNS["start"])
        with wave.open(str(ROOT / "addon/globalPlugins/awqati/sounds/stopwatch/start.wav")) as source:
            self.assertEqual((1, 2, RATE), (source.getnchannels(), source.getsampwidth(), source.getframerate()))
            self.assertAlmostEqual(2.2, source.getnframes() / RATE, places=4)

    def test_packaged_pcm_reproducible_bounded_and_click_free(self):
        for name, pattern in PATTERNS.items():
            with self.subTest(name=name), wave.open(str(ROOT / "addon/globalPlugins/awqati/sounds/stopwatch" / (name + ".wav"))) as source:
                data = source.readframes(source.getnframes())
                self.assertEqual(pcm(pattern), data)
                values = struct.unpack("<" + "h" * (len(data) // 2), data)
                self.assertLessEqual(max(map(abs, values)), 21000)
                self.assertGreater(max(map(abs, values)), 20000)
                self.assertEqual((0, 0), (values[0], values[-1]))

    def test_all_actions_have_distinct_pcm(self):
        self.assertEqual(5, len({pcm(pattern) for pattern in PATTERNS.values()}))

    def test_shared_streamer_is_background_cancellable_and_alert_has_priority(self):
        from awqati.infrastructure import SoundFileService
        from awqati.nvda_adapter.audio_service import AudioService
        root = ROOT / "addon/globalPlugins/awqati"
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        workers = []
        class Player:
            def feed(self, data):
                workers.append(threading.get_ident())
                entered.set()
                release.wait(2)
            def idle(self): pass
            def stop(self): release.set()
            def close(self): pass
        service = AudioService(SoundFileService(root, root), player_factory=lambda *args: Player(),
            dispatch=lambda callback, *args: callback(*args))
        try:
            self.assertTrue(service.play_preview(None, root / "sounds/stopwatch/start.wav",
                lambda: None, lambda result: finished.set()))
            self.assertTrue(entered.wait(2))
            self.assertFalse(release.is_set())
            self.assertNotIn(threading.get_ident(), workers)
            AudioService.cancel_previews()
            self.assertTrue(release.is_set())
            self.assertFalse(service.busy)
            self.assertTrue(finished.wait(2))
            entered.clear(); release.clear(); finished.clear()
            self.assertTrue(service.play_path(root / "sounds/alarms/alarm.wav", lambda: None, lambda result: finished.set()))
            self.assertTrue(entered.wait(2))
            other = AudioService(SoundFileService(root, root))
            self.assertFalse(other.play_preview(None, root / "sounds/stopwatch/start.wav", lambda: None, lambda result: None))
        finally:
            release.set()
            service.cancel()
            finished.wait(2)


def controller_driver(language="en"):
    """Run production controller methods without pretending to provide a GUI."""
    from tests.test_corrective_followup import Translator
    from awqati.nvda_adapter.stopwatch_formatter import STATE_LABELS, lap_ordinal
    from awqati.application.alert_presenter import OutputResult
    path = ROOT / "addon/globalPlugins/awqati/nvda_adapter/stopwatch_control.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    definition = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    messages, clipboard, tones, confirms = [], [], [], []
    wx = SimpleNamespace(YES=1, YES_NO=2, NO_DEFAULT=4, ICON_QUESTION=8)
    wx.MessageBox = lambda *args: (confirms.append(args) or 0)
    namespace = dict(_=Translator(language), spoken=spoken, results=results, lap_ordinal=lap_ordinal, STATE_LABELS=STATE_LABELS,
        ui=SimpleNamespace(message=messages.append), wx=wx, gui=SimpleNamespace(mainFrame=object()),
        api=SimpleNamespace(copyToClip=lambda text: (clipboard.append(text) or True)))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[definition], type_ignores=[])), str(path), "exec"), namespace)
    control = namespace["StopwatchControl"].__new__(namespace["StopwatchControl"])
    clock, repo = Clock(), MemoryRepository()
    control.watch = Stopwatch(clock, repo)
    control.mode, control.dialog = 0, None
    control._closed, control._feedback_generation = False, 0
    control.preferences = MemoryRepository()
    control.audio = SimpleNamespace(cancel=lambda: tones.append("cancel"), close=lambda: tones.append("close"))
    control.runtime = SimpleNamespace(presenter=SimpleNamespace(current=None))
    control.preview = tones.append
    def play_tone(action, on_finished):
        if control.runtime.presenter.current:
            return False
        tones.append(action)
        on_finished(OutputResult(True, True))
        return True
    control._play_tone = play_tone
    return control, clock, repo, namespace, messages, clipboard, tones, confirms


class ControllerTests(unittest.TestCase):
    def test_confirmation_modes_and_always_spoken_queries(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
                control.mode = mode
                control.toggle()
                self.assertEqual(mode in (0, 2), "start" in tones)
                self.assertEqual(mode in (1, 2), bool(messages))
                messages.clear()
                clock.advance(3)
                control.total()
                control.status()
                control.count()
                self.assertEqual(3, len(messages))
                self.assertIn("3 seconds", messages[0])

    def test_lap_capture_precedes_audio_and_speech(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        control.mode = 2
        control.toggle()
        clock.advance(3)
        def slow_tone(action, on_finished):
            clock.advance(2.2)
            from awqati.application.alert_presenter import OutputResult
            on_finished(OutputResult(True, True))
            return True
        control._play_tone = slow_tone
        control.lap()
        self.assertEqual(3000000000, control.watch.laps[0].total_ns)
        self.assertIn("3 seconds", messages[-1])
        self.assertEqual(5200000000, control.watch.elapsed_ns())

    def test_active_alert_suppresses_tone_without_stopping_measurement(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        control.runtime.presenter.current = object()
        control.toggle()
        clock.advance(10)
        self.assertNotIn("start", tones)
        self.assertEqual(10000000000, control.watch.elapsed_ns())

    def test_reset_confirmation_cancel_and_accept(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        control.toggle()
        clock.advance(1)
        control.lap()
        control.toggle()
        control.reset()
        self.assertEqual(1, len(confirmations))
        self.assertEqual(("paused", 1), (control.watch.state, len(control.watch.laps)))
        ns["wx"].MessageBox = lambda *args: ns["wx"].YES
        control.reset()
        self.assertEqual(("idle", 0), (control.watch.state, len(control.watch.laps)))

    def test_running_reset_does_not_open_confirmation(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        control.toggle()
        control.reset()
        self.assertEqual([], confirmations)
        self.assertIn("Pause", messages[-1])

    def test_copy_calls_clipboard_with_complete_results(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        control.toggle()
        clock.advance(1.5)
        control.lap()
        control.copy()
        self.assertIn("Lap 1: 00:00:01.500", copied[0])
        self.assertEqual("Stopwatch results copied.", messages[-1])

    def test_missing_last_lap_and_clipboard_failure(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        control.last_lap()
        self.assertEqual("No laps have been recorded.", messages[-1])
        ns["api"].copyToClip = lambda text: False
        control.copy()
        self.assertEqual("Stopwatch results could not be copied.", messages[-1])

    def test_preferences_saved_separately_and_failure_retains_mode(self):
        control, clock, repo, ns, messages, copied, tones, confirmations = controller_driver()
        self.assertTrue(control.set_mode(2))
        self.assertEqual({"version": 1, "mode": 2}, control.preferences.raw)
        self.assertEqual(0, repo.writes)
        control.preferences.fail = True
        self.assertFalse(control.set_mode(3))
        self.assertEqual(2, control.mode)

    def test_exactly_three_default_gestures_and_standalone_commands(self):
        tree = ast.parse((ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text(encoding="utf-8"))
        definition = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        methods = [node for node in definition.body if isinstance(node, ast.FunctionDef) and node.name.startswith("script_stopwatch")]
        gestures = [keyword.value.value for method in methods for decorator in method.decorator_list
            for keyword in decorator.keywords if keyword.arg == "gesture"]
        self.assertEqual({"kb:NVDA+j", "kb:NVDA+shift+j", "kb:NVDA+control+j", "kb:NVDA+control+shift+j", "kb:NVDA+windows+j", "kb:NVDA+windows+shift+j"}, set(gestures))
        self.assertEqual(12, len(methods))
        mappings = {node.name: ast.unparse(node) for node in methods}
        self.assertIn("(self._stopwatch.toggle,)", mappings["script_stopwatchInfo"])
        self.assertIn("(self._stopwatch.lap,)", mappings["script_stopwatchLaps"])


if __name__ == "__main__":
    unittest.main()
