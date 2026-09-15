from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
import unittest
import wave


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))

from awqati.domain import AlertAction, SoundReference, default_settings  # noqa: E402
from awqati.nvda_adapter.sound_staging import (  # noqa: E402
	SoundStagingSession, collect_sound_reference_values,
)


class SoundStagingSessionTests(unittest.TestCase):
	def setUp(self) -> None:
		self.temporary = tempfile.TemporaryDirectory()
		self.base = Path(self.temporary.name)
		self.root = self.base / "awqati"
		self.source = self.base / "sample.wav"
		with wave.open(str(self.source), "wb") as target:
			target.setnchannels(1)
			target.setsampwidth(1)
			target.setframerate(8000)
			target.writeframes(b"\x80" * 800)

	def tearDown(self) -> None:
		self.temporary.cleanup()

	def prepare(self, session: SoundStagingSession) -> SoundReference:
		self.assertTrue(session.begin_preparation())
		try:
			return session.prepare(self.source, "alerts")
		finally:
			session.finish_preparation()

	def wait_until_removed(self, path: Path) -> None:
		for _ in range(100):
			if not path.exists():
				return
			time.sleep(0.01)
		self.fail(f"temporary staging was not removed: {path}")

	def test_prepare_streams_only_to_staging(self) -> None:
		session = SoundStagingSession(self.root)
		reference = self.prepare(session)
		self.assertTrue(reference.value.startswith("sounds/alerts/"))
		self.assertFalse((self.root / reference.value).exists())
		self.assertEqual(session.resolve(reference).read_bytes(), self.source.read_bytes())
		session.discard()
		self.wait_until_removed(self.root / ".settings-staging")

	def test_commit_is_rejected_while_a_worker_result_is_pending(self) -> None:
		session = SoundStagingSession(self.root)
		self.assertTrue(session.begin_preparation())
		with self.assertRaisesRegex(RuntimeError, "still running"):
			session.begin_commit(set())
		session.finish_preparation()
		session.discard()

	def test_commit_moves_only_referenced_sound_to_final_location(self) -> None:
		session = SoundStagingSession(self.root)
		reference = self.prepare(session)
		commit = session.begin_commit({reference.value})
		self.assertEqual((self.root / reference.value).read_bytes(), self.source.read_bytes())
		session.complete(commit)
		self.wait_until_removed(self.root / ".settings-staging")
		self.assertTrue((self.root / reference.value).is_file())

	def test_failed_settings_save_can_roll_back_final_file_and_directories(self) -> None:
		session = SoundStagingSession(self.root)
		reference = self.prepare(session)
		commit = session.begin_commit({reference.value})
		session.rollback(commit)
		self.assertFalse((self.root / reference.value).exists())
		self.assertTrue(session.resolve(reference).is_file())
		session.discard()
		self.wait_until_removed(self.root / ".settings-staging")
		self.assertFalse((self.root / "sounds").exists())

	def test_unused_staged_sound_is_removed_after_apply(self) -> None:
		session = SoundStagingSession(self.root)
		reference = self.prepare(session)
		staged = session.resolve(reference)
		commit = session.begin_commit(set())
		session.complete(commit)
		self.wait_until_removed(self.root / ".settings-staging")
		self.assertFalse(staged.exists())
		self.assertFalse((self.root / reference.value).exists())

	def test_collect_references_follows_complete_settings_graph(self) -> None:
		settings = default_settings()
		settings.clock.alert.action = AlertAction.SOUND
		settings.clock.alert.sound = SoundReference("sounds/alerts/clock.wav")
		settings.adhkar.morning.alert.sound = SoundReference("sounds/adhkar/morning.wav")
		self.assertEqual(collect_sound_reference_values(settings), {
			"sounds/alerts/clock.wav", "sounds/adhkar/morning.wav",
		})


if __name__ == "__main__":
	unittest.main()
