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

from awqati.domain import AlertAction, AlertEvent, AlertEventType, Instant  # noqa: E402
from awqati.infrastructure import SoundFileService  # noqa: E402
from awqati.nvda_adapter.audio_service import AudioService  # noqa: E402


def make_wav(path: Path, frames=16000):
	path.parent.mkdir(parents=True, exist_ok=True)
	with wave.open(str(path), "wb") as target:
		target.setnchannels(1); target.setsampwidth(1); target.setframerate(8000)
		target.writeframes(b"\x80" * frames)


def clock_event():
	return AlertEvent("clock", AlertEventType.CLOCK, Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)),
		action=AlertAction.SOUND)


class FakePlayer:
	def __init__(self, fail=False, gate=None):
		self.fail, self.gate = fail, gate
		self.chunks = []
		self.stopped = self.closed = False
	def feed(self, data):
		if self.fail: raise OSError("device lost")
		self.chunks.append(data)
		if self.gate: self.gate.wait(2)
	def idle(self): pass
	def stop(self): self.stopped = True
	def close(self): self.closed = True


class AudioServiceTests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		base = Path(self.temp.name)
		self.default = base / "addon" / "sounds" / "clock" / "clock.wav"
		make_wav(self.default)
		self.files = SoundFileService(base / "user", base / "addon")

	def tearDown(self): self.temp.cleanup()

	def test_streams_chunks_off_caller_and_reports_start_then_completion(self):
		player = FakePlayer()
		service = AudioService(self.files, player_factory=lambda *args: player,
			dispatch=lambda callback, *args: callback(*args), frames_per_chunk=1000)
		log, done = [], threading.Event()
		self.assertTrue(service.play(clock_event(), lambda: log.append("start"),
			lambda result: (log.append(("end", result.started, result.completed)), done.set())))
		self.assertTrue(done.wait(3))
		self.assertEqual(log[0], "start")
		self.assertEqual(log[-1], ("end", True, True))
		self.assertGreater(len(player.chunks), 1)
		self.assertTrue(player.closed)

	def test_second_wave_is_refused_while_first_is_active(self):
		gate = threading.Event(); player = FakePlayer(gate=gate)
		service = AudioService(self.files, player_factory=lambda *args: player,
			dispatch=lambda callback, *args: callback(*args), frames_per_chunk=1000)
		done = threading.Event()
		self.assertTrue(service.play(clock_event(), lambda: None, lambda result: done.set()))
		self.assertFalse(service.play(clock_event(), lambda: None, lambda result: None))
		gate.set(); self.assertTrue(done.wait(3))

	def test_failure_before_first_chunk_is_reported_without_false_start(self):
		service = AudioService(self.files, player_factory=lambda *args: FakePlayer(fail=True),
			dispatch=lambda callback, *args: callback(*args))
		results, done = [], threading.Event()
		service.play(clock_event(), lambda: self.fail("must not start"),
			lambda result: (results.append(result), done.set()))
		self.assertTrue(done.wait(3))
		self.assertFalse(results[0].started)
		self.assertFalse(results[0].completed)
		self.assertIsInstance(results[0].error, OSError)

	def test_missing_or_corrupt_default_reports_failure_from_worker(self):
		service = AudioService(self.files, player_factory=lambda *args: FakePlayer(),
			dispatch=lambda callback, *args: callback(*args), diagnostic=lambda error: None)
		for state in ("missing", "corrupt"):
			with self.subTest(state=state):
				if state == "missing": self.default.unlink(missing_ok=True)
				else: self.default.write_bytes(b"bad")
				results, done = [], threading.Event()
				self.assertTrue(service.play(clock_event(), lambda: self.fail("must not start"),
					lambda result: (results.append(result), done.set())))
				self.assertTrue(done.wait(3))
				self.assertFalse(results[0].started)
				self.assertFalse(results[0].completed)


if __name__ == "__main__":
	unittest.main()
