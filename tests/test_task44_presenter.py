from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon" / "globalPlugins"))

from awqati.application import AlertPresenter, AlertScheduler, OutputResult  # noqa: E402
from awqati.domain import AlertAction, AlertEvent, AlertEventType, Instant  # noqa: E402


class Clock:
	def __init__(self):
		self.value = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
	def now(self): return Instant(self.value)


def make_event(identity, action, when, *, kind=AlertEventType.CLOCK, grace=timedelta(minutes=2)):
	return AlertEvent(identity, kind, Instant(when), action=action, message_id="ignored", grace_period=grace)


class FakeOutput:
	def __init__(self, available=True, raises=False):
		self.available, self.raises = available, raises
		self.calls, self.started, self.finished, self.cancelled = [], None, None, 0
	def play(self, event, on_started, on_finished):
		self.calls.append(event.event_id)
		if self.raises: raise RuntimeError("audio failed")
		if not self.available: return False
		self.started, self.finished = on_started, on_finished
		return True
	def speak(self, text, on_started, on_finished):
		self.calls.append(text)
		if self.raises: raise RuntimeError("speech failed")
		if not self.available: return False
		self.started, self.finished = on_started, on_finished
		return True
	def cancel(self): self.cancelled += 1


class PresenterTests(unittest.TestCase):
	def setUp(self):
		self.clock = Clock()
		self.scheduler = AlertScheduler(self.clock)
		self.audio, self.speech = FakeOutput(), FakeOutput()
		self.errors = []
		self.presenter = AlertPresenter(self.scheduler, self.audio, self.speech,
			message_formatter=lambda event, language: f"message:{event.event_id}", on_error=self.errors.append)

	def schedule(self, identity="one", action=AlertAction.SPEECH, offset=0, **kwargs):
		event = make_event(identity, action, self.clock.value + timedelta(seconds=offset), **kwargs)
		self.scheduler.schedule(event)
		return event

	def test_speech_marks_at_start_and_completes_at_callback(self):
		self.schedule()
		self.assertTrue(self.presenter.present_next())
		self.assertEqual(self.speech.calls, ["message:one"])
		self.assertEqual(self.scheduler.current.event_id, "one")
		self.speech.started()
		self.speech.finished(OutputResult(True, True))
		self.assertIsNone(self.scheduler.current)
		self.assertFalse(self.scheduler.schedule(make_event("one", AlertAction.SPEECH, self.clock.value,
			grace=timedelta(minutes=2))))

	def test_sound_only_and_sound_then_speech_are_strictly_serial(self):
		self.schedule(action=AlertAction.SOUND_AND_SPEECH)
		self.presenter.present_next()
		self.assertEqual(self.speech.calls, [])
		self.audio.started()
		self.assertEqual(self.speech.calls, [])
		self.audio.finished(OutputResult(True, True))
		self.assertEqual(self.speech.calls, ["message:one"])
		self.speech.started(); self.speech.finished(OutputResult(True, True))
		self.assertIsNone(self.presenter.current)

	def test_missing_or_failed_sound_falls_back_to_speech_once(self):
		for mode in ("missing", "failure"):
			with self.subTest(mode=mode):
				self.setUp()
				self.audio.available = mode != "missing"
				self.schedule(action=AlertAction.SOUND)
				self.presenter.present_next()
				if mode == "failure":
					self.audio.finished(OutputResult(False, False, error=RuntimeError("bad")))
				self.assertEqual(self.speech.calls, ["message:one"])

	def test_two_events_never_overlap_and_expired_waiter_is_dropped(self):
		self.schedule("first", AlertAction.SOUND, grace=timedelta(minutes=10))
		self.schedule("second", AlertAction.SOUND, grace=timedelta(seconds=1))
		self.presenter.present_next()
		self.assertEqual(self.audio.calls, ["first"])
		self.audio.started()
		self.clock.value += timedelta(seconds=2)
		self.audio.finished(OutputResult(True, True))
		self.assertEqual(self.audio.calls, ["first"])
		self.assertIsNone(self.presenter.current)

	def test_late_or_duplicate_callback_cannot_finish_next_event(self):
		self.schedule("first", AlertAction.SPEECH)
		self.schedule("second", AlertAction.SPEECH)
		self.presenter.present_next()
		old_finish = self.speech.finished
		self.speech.started(); old_finish(OutputResult(True, True))
		self.assertEqual(self.presenter.current.event_id, "second")
		old_finish(OutputResult(True, True))
		self.assertEqual(self.presenter.current.event_id, "second")

	def test_adapter_exceptions_do_not_escape_or_stick_scheduler(self):
		self.audio.raises = True
		self.speech.raises = True
		self.schedule(action=AlertAction.SOUND)
		self.presenter.present_next()
		self.assertIsNone(self.scheduler.current)
		self.assertEqual(len(self.errors), 2)

	def test_close_cancels_without_double_completion(self):
		self.schedule(action=AlertAction.SOUND)
		self.presenter.present_next(); callback = self.audio.finished
		self.presenter.close(); callback(OutputResult(True, True))
		self.assertIsNone(self.scheduler.current)
		self.assertGreaterEqual(self.audio.cancelled, 1)

	def test_silent_is_not_converted_to_speech(self):
		self.schedule(action=AlertAction.SILENT)
		self.presenter.present_next()
		self.assertEqual(self.speech.calls, [])
		self.assertIsNone(self.scheduler.current)


class SpeechServiceTests(unittest.TestCase):
	def test_nvda_callback_commands_report_actual_order(self):
		from awqati.nvda_adapter.speech_service import SpeechService
		sequence = []
		class Command:
			def __init__(self, callback, name=None): self.callback = callback
		service = SpeechService(speak_sequence=sequence.extend, callback_command=Command)
		log = []
		self.assertTrue(service.speak("hello", lambda: log.append("start"), lambda result: log.append("end")))
		self.assertEqual(log, [])
		self.assertEqual(sequence[0], "hello")
		sequence[1].callback(); self.assertEqual(log, ["start"])
		sequence[-1].callback(); self.assertEqual(log, ["start", "end"])

	def test_nvda_speech_cancellation_finishes_the_operation(self):
		from awqati.nvda_adapter.speech_service import SpeechService
		class Command:
			def __init__(self, callback, name=None): self.callback = callback
		class Extension:
			def register(self, callback): self.callback = callback
			def unregister(self, callback): self.callback = None
		extension, results = Extension(), []
		service = SpeechService(speak_sequence=lambda sequence: None, callback_command=Command,
			speech_canceled=extension)
		service.speak("hello", lambda: None, results.append)
		extension.callback()
		self.assertTrue(results[0].cancelled)
		self.assertFalse(service.busy)


if __name__ == "__main__":
	unittest.main()
