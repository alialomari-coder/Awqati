from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))

from awqati.domain import AlertAction, AlertEvent, AlertEventType, Instant, SoundReference  # noqa: E402
from awqati.infrastructure.audio_files import (  # noqa: E402
	InvalidWaveFile, SoundFileService, safe_reference_path, validate_wav,
)
from awqati.nvda_adapter.sound_staging import SoundStagingSession  # noqa: E402
from datetime import datetime, timezone  # noqa: E402


def make_wav(path: Path, *, seconds: float = 0.02, rate: int = 8000, value: int = 128) -> None:
	with wave.open(str(path), "wb") as target:
		target.setnchannels(1)
		target.setsampwidth(1)
		target.setframerate(rate)
		target.writeframes(bytes([value]) * int(rate * seconds))


def event(kind=AlertEventType.CLOCK, sound_ref=None):
	return AlertEvent("e", kind, Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)),
		action=AlertAction.SOUND, sound_ref=sound_ref)


class WavValidationTests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.root = Path(self.temp.name)

	def tearDown(self):
		self.temp.cleanup()

	def test_valid_pcm_wav(self):
		path = self.root / "ok.wav"
		make_wav(path)
		info = validate_wav(path)
		self.assertEqual((info.channels, info.sample_width, info.frame_rate), (1, 1, 8000))

	def test_non_wav_renamed_empty_bad_header_and_wrong_extension(self):
		for name, data in (("renamed.wav", b"not audio"), ("empty.wav", b""),
				("header.wav", b"RIFF" + b"\0" * 40), ("audio.mp3", b"RIFF")):
			with self.subTest(name=name):
				path = self.root / name
				path.write_bytes(data)
				with self.assertRaises(InvalidWaveFile):
					validate_wav(path)

	def test_truncated_declared_data_is_rejected(self):
		path = self.root / "cut.wav"
		make_wav(path, seconds=1)
		data = path.read_bytes()
		path.write_bytes(data[:-100])
		with self.assertRaises(InvalidWaveFile):
			validate_wav(path)

	def test_large_declared_payload_is_checked_without_loading_it(self):
		path = self.root / "large.wav"
		frames = 8 * 1024 * 1024
		header = (b"RIFF" + struct.pack("<I", 36 + frames) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1,
			8000, 8000, 1, 8) + b"data" + struct.pack("<I", frames))
		with path.open("wb") as target:
			target.write(header)
			target.seek(len(header) + frames - 1)
			target.write(b"\x80")
		started = time.monotonic()
		self.assertEqual(validate_wav(path).frame_count, frames)
		self.assertLess(time.monotonic() - started, 1.0)


class SoundFileServiceTests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.root = Path(self.temp.name)
		self.user = self.root / "config" / "awqati"
		self.addon = self.root / "addon" / "awqati"
		self.files = SoundFileService(self.user, self.addon)

	def tearDown(self):
		self.temp.cleanup()

	def test_creates_exact_final_directories(self):
		root = self.files.ensure_sound_directories()
		self.assertEqual({p.name for p in root.iterdir()}, {"alerts", "clock", "adhkar"})

	def test_safe_reference_blocks_absolute_traversal_and_escape(self):
		for value in ("C:/bad.wav", "/sounds/clock/a.wav", "sounds/../a.wav",
				"sounds/clock/../../a.wav", "sounds\\clock\\a.wav"):
			with self.subTest(value=value), self.assertRaises(ValueError):
				safe_reference_path(self.user, value)

	def test_only_clock_has_a_bundled_default(self):
		path = self.addon / "sounds" / "clock" / "clock.wav"
		path.parent.mkdir(parents=True)
		make_wav(path)
		self.assertEqual(self.files.default_path(AlertEventType.CLOCK), path)
		for kind in AlertEventType:
			if kind is not AlertEventType.CLOCK:
				self.assertIsNone(self.files.default_path(kind))

	def test_custom_then_default_then_none_fallback_matrix(self):
		default = self.addon / "sounds" / "clock" / "clock.wav"
		default.parent.mkdir(parents=True)
		make_wav(default, value=100)
		custom = self.user / "sounds" / "clock" / "mine.wav"
		custom.parent.mkdir(parents=True)
		make_wav(custom, value=200)
		resolved = self.files.resolve(event(sound_ref="sounds/clock/mine.wav"))
		self.assertEqual((resolved.path, resolved.source), (custom, "custom"))
		custom.unlink()
		self.assertEqual(self.files.resolve(event(sound_ref="sounds/clock/mine.wav")).source, "default")
		default.write_bytes(b"corrupt")
		self.assertIsNone(self.files.resolve(event(sound_ref="sounds/clock/mine.wav")))
		self.assertIsNone(self.files.resolve(event(AlertEventType.MORNING_ADHKAR)))

	def test_legacy_adhan_reference_is_readable(self):
		path = self.user / "sounds" / "adhan" / "old.wav"
		path.parent.mkdir(parents=True)
		make_wav(path)
		self.assertEqual(self.files.custom_path("sounds/adhan/old.wav"), path)


class SoundStagingTask44Tests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.base = Path(self.temp.name)
		self.root = self.base / "config" / "awqati"
		self.files = SoundFileService(self.root, self.base / "addon")

	def tearDown(self):
		self.temp.cleanup()

	def prepare(self, session, source, category="clock"):
		self.assertTrue(session.begin_preparation())
		try:
			return session.prepare(source, category)
		finally:
			session.finish_preparation()

	def test_external_file_is_managed_and_committed_to_category(self):
		source = self.base / "outside.wav"
		make_wav(source)
		session = SoundStagingSession(self.root, self.files)
		reference = self.prepare(session, source)
		self.assertTrue(reference.value.startswith("sounds/clock/awqati-managed-"))
		commit = session.begin_commit({reference.value})
		session.complete(commit, {reference.value})
		self.assertTrue((self.root / Path(reference.value)).is_file())

	def test_file_already_in_right_category_is_not_copied_or_managed(self):
		source = self.root / "sounds" / "clock" / "manual.wav"
		source.parent.mkdir(parents=True)
		make_wav(source)
		session = SoundStagingSession(self.root, self.files)
		self.assertEqual(self.prepare(session, source).value, "sounds/clock/manual.wav")

	def test_same_name_different_content_does_not_overwrite(self):
		one, two = self.base / "one" / "same.wav", self.base / "two" / "same.wav"
		one.parent.mkdir(); two.parent.mkdir()
		make_wav(one, value=1); make_wav(two, value=2)
		session = SoundStagingSession(self.root, self.files)
		a = self.prepare(session, one); b = self.prepare(session, two)
		self.assertNotEqual(a, b)
		commit = session.begin_commit({a.value, b.value})
		session.complete(commit, {a.value, b.value})
		self.assertNotEqual((self.root / Path(a.value)).read_bytes(), (self.root / Path(b.value)).read_bytes())

	def test_invalid_wav_never_creates_reference_or_final_file(self):
		source = self.base / "bad.wav"
		source.write_bytes(b"not a wave")
		session = SoundStagingSession(self.root, self.files)
		with self.assertRaises(InvalidWaveFile):
			self.prepare(session, source)
		self.assertFalse((self.root / "sounds").exists())

	def test_cleanup_removes_only_unreferenced_managed_files(self):
		directory = self.files.ensure_sound_directories() / "clock"
		managed = directory / "awqati-managed-deadbeef-old.wav"
		manual = directory / "manual.wav"
		make_wav(managed); make_wav(manual)
		self.files.cleanup_unreferenced_managed(set())
		self.assertFalse(managed.exists())
		self.assertTrue(manual.exists())


if __name__ == "__main__":
	unittest.main()
