from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "globalPlugins"))

from awqati.application import AlertPresenter, OutputResult  # noqa: E402
from awqati.domain import AlertAction, AlertEvent, AlertEventType, Instant  # noqa: E402
from awqati.infrastructure import SoundFileService  # noqa: E402
from awqati.nvda_adapter.audio_service import AudioService  # noqa: E402


def make_wav(path: Path, value: int = 128) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with wave.open(str(path), "wb") as target:
		target.setnchannels(1); target.setsampwidth(1); target.setframerate(8000)
		target.writeframes(bytes([value]) * 800)


def event(kind=AlertEventType.CLOCK, sound_ref=None, action=AlertAction.SOUND):
	return AlertEvent("matrix", kind, Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)),
		action=action, sound_ref=sound_ref)


class ResolverMatrixTests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.base = Path(self.temp.name)
		self.user = self.base / "user"
		self.addon = self.base / "addon"
		self.files = SoundFileService(self.user, self.addon)

	def tearDown(self): self.temp.cleanup()

	def test_custom_and_default_validity_matrix(self):
		custom = self.user / "sounds" / "clock" / "custom.wav"
		default = self.addon / "sounds" / "clock" / "clock.wav"
		make_wav(custom, 100)
		resolved = self.files.resolve(event(sound_ref="sounds/clock/custom.wav"))
		self.assertEqual((resolved.path, resolved.source), (custom, "custom"))

		custom.write_bytes(b"corrupt")
		make_wav(default, 110)
		resolved = self.files.resolve(event(sound_ref="sounds/clock/custom.wav"))
		self.assertEqual((resolved.path, resolved.source), (default, "default"))

		custom.unlink(); default.write_bytes(b"corrupt")
		self.assertIsNone(self.files.resolve(event(sound_ref="sounds/clock/custom.wav")))
		self.assertIsNone(self.files.resolve(event(AlertEventType.MORNING_ADHKAR,
			sound_ref="sounds/adhkar/missing.wav")))

	def test_cleanup_never_touches_bundled_default_or_manual_user_file(self):
		default = self.addon / "sounds" / "clock" / "clock.wav"
		manual = self.user / "sounds" / "clock" / "manual.wav"
		managed = self.user / "sounds" / "clock" / "awqati-managed-deadbeef-old.wav"
		for path in (default, manual, managed): make_wav(path)
		self.files.cleanup_unreferenced_managed(set())
		self.assertTrue(default.is_file())
		self.assertTrue(manual.is_file())
		self.assertFalse(managed.exists())

	def test_preview_corrupt_custom_falls_back_to_valid_default(self):
		custom = self.user / "sounds" / "clock" / "custom.wav"
		default = self.addon / "sounds" / "clock" / "clock.wav"
		custom.parent.mkdir(parents=True); custom.write_bytes(b"corrupt")
		make_wav(default)
		played = []
		class Player:
			def feed(self, data): played.append(data)
			def idle(self): pass
			def close(self): pass
		service = AudioService(self.files, player_factory=lambda *args: Player(),
			dispatch=lambda callback, *args: callback(*args))
		done = threading.Event(); results = []
		self.assertTrue(service.play_preview(AlertEventType.CLOCK, custom, lambda: None,
			lambda result: (results.append(result), done.set())))
		self.assertTrue(done.wait(3))
		self.assertTrue(played)
		self.assertTrue(results[0].completed)


class PresenterStartedFailureTests(unittest.TestCase):
	def test_failure_after_audio_start_falls_back_without_second_mark(self):
		value = event(action=AlertAction.SOUND)
		class Scheduler:
			def __init__(self): self.value = value; self.marked = []; self.completed = []
			def claim_for_presentation(self, now=None): current, self.value = self.value, None; return current
			def mark_presented(self, identity): self.marked.append(identity); return True
			def complete(self, identity, presented=False): self.completed.append((identity, presented)); return True
			def cancel(self, identity): return True
		class Audio:
			def play(self, value, start, finish): self.start, self.finish = start, finish; return True
			def cancel(self): pass
		class Speech:
			def __init__(self): self.calls = 0
			def speak(self, text, start, finish):
				self.calls += 1; start(); finish(OutputResult(True, True)); return True
			def cancel(self): pass
		scheduler, audio, speech = Scheduler(), Audio(), Speech()
		presenter = AlertPresenter(scheduler, audio, speech,
			message_formatter=lambda value, language: "fallback")
		self.assertTrue(presenter.present_next())
		audio.start()
		audio.finish(OutputResult(True, False, error=OSError("device lost")))
		self.assertEqual(speech.calls, 1)
		self.assertEqual(scheduler.marked, ["matrix"])
		self.assertEqual(scheduler.completed, [("matrix", False)])


if __name__ == "__main__":
	unittest.main()
