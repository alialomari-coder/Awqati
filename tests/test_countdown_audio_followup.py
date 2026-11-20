"""Fake-clock/real-worker regressions; no claim of live NVDA or listening tests."""
import ast
from dataclasses import replace
import hashlib
import io
import math
from pathlib import Path
import struct
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
sys.path.insert(0, str(ROOT / "tools"))
from tools.build_stopwatch_sounds import RATE, PEAK, PITCH, PATTERNS, pcm
from tools.build_countdown_sound import PATTERN, CONFIRMATIONS, tick_pcm
from awqati.application.countdown_ticking import TickPlan
from awqati.application.countdown import CountdownService
from awqati.domain.countdown import Countdown
from awqati.application.alert_presenter import OutputResult, format_alert_message
from awqati.nvda_adapter.ticking_audio import TickingAudio
import test_countdown as countdown_tests


def samples(data):
    return struct.unpack("<" + "h" * (len(data) // 2), data)


class ToneQualityTests(unittest.TestCase):
    def test_stopwatch_actual_pitch_gain_duration_and_silence(self):
        for name, pattern in PATTERNS.items():
            with self.subTest(name=name), wave.open(str(ROOT / "addon/globalPlugins/awqati/sounds/stopwatch" / (name + ".wav"))) as source:
                data = source.readframes(source.getnframes())
                self.assertEqual(pcm(pattern), data)
                self.assertEqual(sum(RATE * ms // 1000 for _, ms in pattern), source.getnframes())
                values = samples(data)
                self.assertLessEqual(max(map(abs, values)), PEAK)
                self.assertGreater(max(map(abs, values)), 20000)
                self.assertEqual((0, 0), (values[0], values[-1]))
                offset = 0
                for frequency, ms in pattern:
                    count = RATE * ms // 1000
                    segment = values[offset:offset + count]
                    if frequency is None:
                        self.assertTrue(all(value == 0 for value in segment))
                    else:
                        # Measure zero crossings in the actual generated WAV,
                        # independently of the generator's PCM reconstruction.
                        interior = segment[RATE // 100:-RATE // 100]
                        crossings = [i for i in range(1, len(interior)) if interior[i - 1] < 0 <= interior[i]]
                        actual = RATE * (len(crossings) - 1) / (crossings[-1] - crossings[0])
                        self.assertAlmostEqual(frequency * 1.5, actual, delta=2)
                    offset += count

    def test_gain_increase_is_bounded_and_not_clipped(self):
        old = samples(pcm(PATTERNS["start"], amplitude=6500, pitch=1))
        new = samples(pcm(PATTERNS["start"]))
        rms = lambda x: math.sqrt(sum(v * v for v in x) / len(x))
        self.assertAlmostEqual(21000 / 6500, rms(new) / rms(old), delta=.02)
        self.assertTrue(all(-32768 < value < 32767 for value in new))
        self.assertEqual((21000, 1.5), (PEAK, PITCH))

    def test_expiry_rhythm_and_duration_preserved(self):
        path = ROOT / "addon/globalPlugins/awqati/sounds/timers/finished.wav"
        with wave.open(str(path)) as source:
            self.assertEqual(pcm(PATTERN), source.readframes(source.getnframes()))
            original = subprocess.check_output(["git", "show", "b52c0ae:" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
            with wave.open(io.BytesIO(original)) as old:
                self.assertEqual(old.getparams(), source.getparams())
        self.assertEqual([160, 90, 160, 90, 300], [duration for _, duration in PATTERN])

    def test_confirmation_files_and_compatible_pause_resume_patterns(self):
        self.assertEqual(PATTERNS["pause"], CONFIRMATIONS["pause"])
        self.assertEqual(PATTERNS["resume"], CONFIRMATIONS["resume"])
        self.assertEqual(CONFIRMATIONS["start"], CONFIRMATIONS["resume"])
        expected = {"start": .24, "pause": .24, "resume": .24, "restart": .25, "cancel": .28}
        for name, pattern in CONFIRMATIONS.items():
            with self.subTest(name=name), wave.open(str(ROOT / "addon/globalPlugins/awqati/sounds/timers" / (name + ".wav"))) as source:
                values = samples(source.readframes(source.getnframes()))
                self.assertAlmostEqual(expected[name], source.getnframes() / RATE, delta=.0001)
                self.assertEqual(samples(pcm(pattern)), values)
                self.assertEqual((0, 0), (values[0], values[-1]))
                self.assertLessEqual(max(map(abs, values)), 21000)

    def test_tick_tock_short_different_quieter_and_clean_endpoints(self):
        sounds = []
        for index, name in enumerate(("tick", "tock")):
            with wave.open(str(ROOT / "addon/globalPlugins/awqati/sounds/timers" / (name + ".wav"))) as source:
                data = source.readframes(source.getnframes())
                self.assertEqual(tick_pcm(bool(index)), data)
                self.assertLess(source.getnframes() / RATE, .04)
                values = samples(data)
                self.assertGreater(max(map(abs, values)), 1000)
                self.assertLess(max(map(abs, values)), 6000)
                self.assertEqual((0, 0), (values[0], values[-1]))
                sounds.append(data)
        self.assertNotEqual(*sounds)

    def test_personal_alarm_clock_and_prayer_assets_unchanged(self):
        paths = ["addon/globalPlugins/awqati/sounds/alarms/alarm.wav", "addon/globalPlugins/awqati/sounds/clock/clock.wav"]
        for relative in paths:
            original = subprocess.check_output(["git", "show", "b52c0ae:" + relative], cwd=ROOT)
            self.assertEqual(hashlib.sha256(original).digest(), hashlib.sha256((ROOT / relative).read_bytes()).digest())
        for relative in ("application/stopwatch.py", "application/personal_alarms.py", "nvda_adapter/stopwatch_control.py", "nvda_adapter/audio_service.py"):
            path = ROOT / "addon/globalPlugins/awqati" / relative
            old = subprocess.check_output(["git", "show", "b52c0ae:" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
            self.assertEqual(ast.dump(ast.parse(old)), ast.dump(ast.parse(__import__('multipress_history').legacy_control_bytes(path.read_bytes()) if relative.endswith('stopwatch_control.py') else path.read_bytes())))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.key = TickPlan(), ("selected", "cycle")

    def poll(self, second, **options):
        return self.plan.poll(round(second * 10**9), self.key, eligible=True, **options)

    def test_one_click_each_second_and_alternation(self):
        self.assertIsNone(self.poll(0))
        self.assertIsNone(self.poll(.99))
        self.assertEqual(0, self.poll(1))
        self.assertIsNone(self.poll(1.25))
        self.assertEqual(1, self.poll(2))
        self.assertEqual(0, self.poll(3))

    def test_late_calls_skip_missed_clicks(self):
        self.poll(0)
        self.assertEqual(0, self.poll(9))
        self.assertIsNone(self.poll(9.1))
        self.assertEqual(1, self.poll(10))

    def test_blocked_alert_consumes_slots_without_a_burst(self):
        self.poll(0)
        self.assertIsNone(self.poll(5, blocked=True))
        self.assertIsNone(self.poll(5.5))
        self.assertEqual(1, self.poll(6))

    def test_selection_and_new_cycle_start_a_new_reference(self):
        self.poll(0)
        self.poll(1)
        self.key = ("other", "cycle")
        self.assertIsNone(self.poll(1.1))
        self.assertEqual(0, self.poll(2.1))
        self.key = ("other", "new cycle")
        self.assertIsNone(self.poll(2.2))

    def test_ineligible_pause_and_resume_reset_phase(self):
        self.poll(0)
        self.plan.poll(2 * 10**9, self.key, eligible=False)
        self.assertIsNone(self.poll(20))
        self.assertEqual(0, self.poll(21))

    def test_long_polling_has_no_accumulated_drift(self):
        self.poll(0)
        counts = 0
        for i in range(1, 40001):
            counts += self.poll(i / 4) is not None
        self.assertEqual(10000, counts)


class ControllerAudioTests(unittest.TestCase):
    def setUp(self):
        self.model = countdown_tests.CountdownTests()
        self.model.setUp()
        self.control, self.messages, self.ns = self.model.control()
        self.service, self.identity = self.model.service, self.model.identity
        self.clicks, self.cancels = [], []
        self.control.tick_audio = SimpleNamespace(play=self.clicks.append, cancel=lambda: self.cancels.append(True))
        self.audio = SimpleNamespace(busy=False, callback=None, paths=[])
        def preview(kind, path, started, finished):
            self.audio.busy, self.audio.callback = True, finished
            self.audio.paths.append(path)
            return True
        self.audio.play_preview = preview
        self.audio.cancel = lambda: setattr(self.audio, "busy", False)
        self.control.feedback_audio = self.audio
        self.ns["AudioService"] = SimpleNamespace(_instances=[self.audio], cancel_previews=lambda: None)

    def enable_start(self):
        self.service.put(replace(self.model.timer, ticking=True))
        self.service.transition(self.identity, "start")
        self.control.update_ticking()

    def complete(self, result=OutputResult(True, True)):
        self.audio.busy = False
        self.audio.callback(result)

    def test_success_tone_then_name_once(self):
        self.control.change("start")
        self.assertEqual("running", self.service.rows[self.identity]["state"])
        self.assertEqual([], self.messages)
        self.assertEqual("start.wav", self.audio.paths[-1].name)
        self.complete()
        self.assertEqual(["Timer Reading started."], self.messages)
        self.complete()
        self.assertEqual(1, len(self.messages))

    def test_pause_resume_restart_cancel_use_own_tones(self):
        self.control.change("start")
        for action, state in (("pause", "paused"), ("resume", "running"), ("restart", "running"), ("cancel", "cancelled")):
            with self.subTest(action=action):
                self.control.change(action)
                self.assertEqual(action + ".wav", self.audio.paths[-1].name)
                self.assertEqual(state, self.service.rows[self.identity]["state"])
                self.complete()

    def test_failure_has_no_tone_or_success_message(self):
        self.model.repo.fail = True
        self.control.change("start")
        self.assertEqual([], self.audio.paths)
        self.assertNotIn("started", self.messages[-1])

    def test_start_timestamp_precedes_tone_latency(self):
        self.control.change("start")
        self.model.advance(2)
        self.assertEqual(58 * 10**9, self.service.remaining(self.identity))
        self.assertEqual([], self.messages)
        self.complete()

    def test_new_command_and_alert_cancel_stale_speech(self):
        self.control.change("start")
        old = self.audio.callback
        self.control.change("pause")
        old(OutputResult(True, True))
        self.assertEqual([], self.messages)
        self.control.audio = SimpleNamespace(cancel=lambda: None)
        self.control.cancel()
        self.complete()
        self.assertEqual([], self.messages)

    def test_feedback_waits_for_active_alert_and_speaks_once(self):
        presenter = SimpleNamespace(current=object(), present_next=lambda *args: None)
        self.control.runtime.presenter = presenter
        self.control.runtime.now = SimpleNamespace(now=self.model.instant)
        self.control.error_reported = False
        self.ns["wx"].CallLater = lambda *args: SimpleNamespace(Stop=lambda: None)
        self.control.change("start")
        self.assertEqual([], self.audio.paths)
        self.assertEqual([], self.messages)
        self.control.tick()
        self.assertEqual([], self.messages)
        presenter.current = None
        self.control.tick()
        self.control.tick()
        self.assertEqual(["Timer Reading started."], self.messages)

    def test_expiry_method_and_custom_sound_are_not_changed(self):
        from awqati.domain import AlertAction
        timer = replace(self.model.timer, action=AlertAction.SPEECH, sound_ref="sounds/timers/custom.wav")
        self.service.put(timer)
        self.control.change("start")
        self.assertEqual(timer, self.service.definitions[self.identity])
        self.model.advance(60)
        event = self.service.poll(self.model.instant())[0]
        self.assertEqual(AlertAction.SPEECH, event.action)
        self.assertEqual(timer.sound_ref, event.sound_ref)
        self.assertEqual("انتهى مؤقت Reading", format_alert_message(event, "ar"))

    def test_only_selected_enabled_running_timer_ticks(self):
        self.enable_start()
        other = Countdown.create("Other", 120, ticking=True)
        self.service.put(other)
        self.service.transition(other.timer_id, "start")
        self.model.advance(1)
        self.control.update_ticking()
        self.assertEqual([0], self.clicks)
        self.control.selected = other.timer_id
        self.assertTrue(self.cancels)
        self.control.update_ticking()
        self.model.advance(1)
        self.control.update_ticking()
        self.assertEqual([0, 0], self.clicks)
        self.assertEqual("running", self.service.rows[self.identity]["state"])

    def test_selection_of_disabled_or_ready_timer_stops_ticking(self):
        self.enable_start()
        other = Countdown.create("Silent", 60)
        self.service.put(other)
        self.control.selected = other.timer_id
        self.control.update_ticking()
        self.model.advance(2)
        self.control.update_ticking()
        self.assertEqual([], self.clicks)

    def test_pause_resume_and_cancel_stop_immediately(self):
        self.enable_start()
        self.model.advance(1)
        self.control.update_ticking()
        self.control.change("pause")
        self.assertTrue(self.cancels)
        self.audio.busy = False
        self.control.update_ticking()
        self.model.advance(3)
        self.control.update_ticking()
        self.assertEqual([0], self.clicks)
        self.control.change("resume")
        self.complete()
        self.control.update_ticking()
        self.model.advance(1)
        self.control.update_ticking()
        self.assertEqual([0, 0], self.clicks)
        self.control.change("cancel")
        self.audio.busy = False
        self.control.update_ticking()
        self.model.advance(2)
        self.control.update_ticking()
        self.assertEqual([0, 0], self.clicks)

    def test_expiry_delete_and_alert_suppress_clicks(self):
        self.enable_start()
        self.control.runtime.presenter._event = SimpleNamespace(event_type="higher alert")
        self.model.advance(1)
        self.control.update_ticking()
        self.assertEqual([], self.clicks)
        self.control.runtime.presenter._event = None
        self.model.advance(1)
        self.control.update_ticking()
        self.assertEqual([1], self.clicks)
        self.model.advance(58)
        self.service.poll(self.model.instant())
        self.control.update_ticking()
        self.assertEqual([1], self.clicks)
        self.service.delete(self.identity)
        self.control.update_ticking()
        self.assertEqual([1], self.clicks)

    def test_ticking_does_not_write_speak_or_change_measurement(self):
        self.enable_start()
        writes = self.model.repo.writes
        for _ in range(39):
            self.model.advance(.25)
            self.control.update_ticking()
        self.assertEqual(writes, self.model.repo.writes)
        self.assertEqual([], self.messages)
        self.assertEqual(50250000000, self.service.remaining(self.identity))

    def test_old_files_default_off_and_saved_quick_preferences_restore(self):
        row = self.model.repo.raw["timers"][0]["definition"]
        row.pop("ticking", None)
        restored = self.model.restore()
        self.assertFalse(restored.definitions[self.identity].ticking)
        for saved in (False, True):
            restored.put(replace(self.model.timer, ticking=True, saved=saved))
            restored = self.model.restore()
            self.assertTrue(restored.definitions[self.identity].ticking)
            self.assertEqual(saved, restored.definitions[self.identity].saved)
        with self.assertRaises(ValueError):
            replace(self.model.timer, ticking="yes")

    def test_ui_checkbox_label_and_own_saved_value(self):
        source = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/countdown_dialog.py").read_text(encoding="utf-8")
        self.assertIn('label=_("Play clock ticking")', source)
        self.assertIn('timer.ticking if timer else False', source)
        self.assertIn('ticking=self.ticking.GetValue()', source)
        from test_corrective_followup import Translator
        self.assertEqual("تشغيل تكتكة الساعة", Translator("ar")("Play clock ticking"))


class PersistentWorkerTests(unittest.TestCase):
    def setUp(self):
        self.changed = threading.Condition()
        self.data, self.workers, self.factory_calls, self.idles = [], [], 0, 0
        self.entered, self.release = threading.Event(), threading.Event()
        self.release.set()
        outer = self
        class Player:
            def feed(self, data):
                outer.entered.set()
                outer.release.wait(2)
                outer.data.append(data)
                outer.workers.append(threading.get_ident())
            def idle(self):
                with outer.changed:
                    outer.idles += 1
                    outer.changed.notify_all()
            def stop(self): outer.release.set()
            def close(self): pass
        def factory(source):
            self.factory_calls += 1
            return Player()
        self.audio = TickingAudio(ROOT / "addon/globalPlugins/awqati/sounds/timers", factory)

    def tearDown(self):
        self.release.set()
        self.audio.close()
        if self.audio.thread:
            self.audio.thread.join(2)
            self.assertFalse(self.audio.thread.is_alive())

    def wait(self, count):
        with self.changed:
            self.assertTrue(self.changed.wait_for(lambda: self.idles >= count, 2))

    def test_one_worker_one_player_cached_wavs_and_background_output(self):
        with patch("awqati.nvda_adapter.ticking_audio.wave.open", wraps=wave.open) as opened:
            for index in range(6):
                self.audio.play(index % 2)
                self.wait(index + 1)
            self.assertEqual(2, opened.call_count)
        self.assertEqual(1, self.factory_calls)
        self.assertEqual(1, len(set(self.workers)))
        self.assertNotIn(threading.get_ident(), self.workers)
        self.assertEqual([tick_pcm(bool(i % 2)) for i in range(6)], self.data)

    def test_latest_slot_replaces_a_backlog_without_creating_workers(self):
        self.release.clear()
        self.audio.play(0)
        self.assertTrue(self.entered.wait(2))
        worker = self.audio.thread
        for _ in range(100):
            self.audio.play(1)
        self.release.set()
        self.wait(2)
        self.assertIs(worker, self.audio.thread)
        self.assertEqual(2, len(self.data))
        self.assertEqual(tick_pcm(True), self.data[-1])

    def test_cancel_and_close_unblock_worker_and_ignore_later_requests(self):
        self.release.clear()
        self.audio.play(0)
        self.assertTrue(self.entered.wait(2))
        self.audio.play(1)
        self.audio.close()
        self.assertTrue(self.release.is_set())
        self.audio.thread.join(2)
        self.audio.play(1)
        self.assertIsNone(self.audio.request)
        self.assertLessEqual(len(self.data), 1)


if __name__ == "__main__":
    unittest.main()
