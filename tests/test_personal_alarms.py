"""Alarm contracts exercised with real storage and the existing scheduler/presenter."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.domain import AlertAction, AlertEvent, AlertEventType as T, Instant, default_settings
from awqati.domain.alerts import utc
from awqati.domain.personal_alarms import PersonalAlarm, validate_alarm_fields
from awqati.application.personal_alarms import PersonalAlarmService, CombinedAlarmSource
from awqati.application.alert_scheduler import AlertScheduler
from awqati.application.alert_presenter import AlertPresenter, OutputResult
from awqati.infrastructure.alarm_repository import AlarmRepository
from awqati.infrastructure.audio_files import SoundFileService
from awqati.infrastructure.timezone_provider import BundledTimezoneProvider
from awqati.nvda_adapter.audio_service import AudioService


class MemoryRepository:
    def __init__(self):
        self.alarms, self.state, self.writes = {}, {}, 0
    def load(self):
        return dict(self.alarms), deepcopy(self.state)
    def save(self, alarms, state):
        self.alarms, self.state = dict(alarms), deepcopy(state)
        self.writes += 1


class AlarmsTests(unittest.TestCase):
    def setUp(self):
        self.now = Instant(datetime(2026, 11, 1, 8, tzinfo=timezone.utc))  # Sunday
        self.zone = timezone.utc
        self.repo = MemoryRepository()
        self.service = PersonalAlarmService(self.repo, lambda: self.zone, lambda: self.now)

    def alarm(self, **kw):
        values = dict(name="Wake", hour=8, minute=0, weekdays=(6,))
        values.update(kw)
        value = PersonalAlarm.create(**values)
        self.service.put(value)
        return value

    def test_midnight_and_day_selection_validation(self):
        self.assertIsNone(validate_alarm_fields("0", "0", (6,)))
        for h, m in (("", ""), ("24", "0"), ("0", "60"), ("-1", "0"), ("1.5", "2")):
            with self.subTest(h=h, m=m):
                self.assertEqual("time", validate_alarm_fields(h, m, (6,)))
        self.assertEqual("days", validate_alarm_fields("0", "0", ()))
        self.assertEqual("timeAndDays", validate_alarm_fields("", "", ()))

    def test_definition_rejects_invalid_values(self):
        for options in (dict(hour=True), dict(hour=24), dict(minute=-1), dict(weekdays=()), dict(weekdays=(8,)),
                dict(duration=35), dict(snooze_minutes=7), dict(snooze_limit=0), dict(enabled=1),
                dict(sound_ref="sounds/alarms/../bad.wav"), dict(action=AlertAction.SILENT)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.alarm(**options)

    def test_create_edit_delete_and_independent_duplicate_names(self):
        first, second = self.alarm(), self.alarm()
        self.assertNotEqual(first.alarm_id, second.alarm_id)
        self.service.put(replace(first, hour=9, duration=300, snooze_enabled=False))
        self.assertEqual(8, self.service.alarms[second.alarm_id].hour)
        self.assertEqual(60, self.service.alarms[second.alarm_id].duration)
        self.service.delete(first.alarm_id)
        self.assertEqual([second.alarm_id], list(self.service.alarms))

    def test_disable_enable_and_all(self):
        first, second = self.alarm(), self.alarm()
        self.service.put(replace(first, enabled=False))
        self.assertIsNone(self.service.next_occurrence(self.service.alarms[first.alarm_id], self.now))
        self.service.enable_all(False)
        self.assertFalse(self.service.events(self.now))
        self.service.enable_all(True)
        self.assertEqual(2, len(self.service.events(self.now)))

    def test_one_day_next_week(self):
        alarm = self.alarm()
        self.now = Instant(self.now.value + timedelta(minutes=1))
        self.assertEqual(8, self.service.next_occurrence(alarm, self.now).value.day)

    def test_scattered_days(self):
        alarm = self.alarm(weekdays=(0, 2, 5))
        self.assertEqual(2, self.service.next_occurrence(alarm, self.now).value.day)
        self.now = Instant(datetime(2026, 11, 3, 8, tzinfo=timezone.utc))
        self.assertEqual(4, self.service.next_occurrence(alarm, self.now).value.day)

    def test_all_days_and_day_rollover(self):
        alarm = self.alarm(weekdays=tuple(range(7)), hour=0)
        when = self.service.next_occurrence(alarm, self.now)
        self.assertEqual((2, 0, 0), (when.value.day, when.value.hour, when.value.minute))

    def test_claim_reserves_occurrence_before_output_and_restart(self):
        alarm = self.alarm()
        event = self.service.events(self.now)[0]
        self.service.claimed(event)
        restarted = PersonalAlarmService(self.repo, lambda: self.zone, lambda: self.now)
        self.assertEqual(8, restarted.events(self.now, include_recent=True)[0].scheduled_at.value.day)

    def test_backward_clock_does_not_repeat_claimed_alarm(self):
        alarm = self.alarm(weekdays=tuple(range(7)))
        self.service.claimed(self.service.events(self.now)[0])
        self.now = Instant(self.now.value - timedelta(hours=1))
        self.assertEqual(2, self.service.next_occurrence(alarm, self.now).value.day)

    def test_resume_ten_minute_boundary_and_stale(self):
        self.alarm()
        self.now = Instant(self.now.value + timedelta(minutes=10))
        self.assertEqual(1, self.service.events(self.now, include_recent=True)[0].scheduled_at.value.day)
        self.now = Instant(self.now.value + timedelta(microseconds=1))
        self.assertEqual(8, self.service.events(self.now, include_recent=True)[0].scheduled_at.value.day)

    def test_snooze_default_limit_and_exhaustion(self):
        self.alarm(snooze_limit=1)
        self.service.claimed(self.service.events(self.now)[0])
        self.assertTrue(self.service.snooze(self.now))
        self.service.finish(self.service.active, "snoozed")
        event = self.service.events(self.now)[0]
        self.assertEqual(self.now.value + timedelta(minutes=5), event.scheduled_at.value)
        self.service.claimed(event)
        self.assertFalse(self.service.snooze(event.scheduled_at))

    def test_unlimited_snooze_and_changed_duration(self):
        self.alarm(snooze_limit=None, snooze_minutes=30)
        for _ in range(6):
            self.service.claimed(self.service.events(self.now)[0])
            self.assertTrue(self.service.snooze(self.now))
            self.now = Instant(self.now.value + timedelta(minutes=30))

    def test_disabled_snooze(self):
        self.alarm(snooze_enabled=False)
        self.service.claimed(self.service.events(self.now)[0])
        self.assertFalse(self.service.snooze(self.now))

    def test_auto_finish_does_not_create_snooze_or_disable(self):
        alarm = self.alarm()
        self.service.claimed(self.service.events(self.now)[0])
        self.service.finish(self.service.active, "durationElapsed")
        self.assertIsNone(self.service.state[alarm.alarm_id]["snooze"])
        self.assertTrue(self.service.alarms[alarm.alarm_id].enabled)

    def test_delete_disable_edit_cancel_pending_snooze(self):
        for operation in ("delete", "disable", "edit", "disableAll"):
            with self.subTest(operation=operation):
                alarm = self.alarm()
                event = self.service._event(alarm, self.now)
                self.service.claimed(event)
                self.service.snooze(self.now)
                if operation == "delete":
                    self.service.delete(alarm.alarm_id)
                    self.assertNotIn(alarm.alarm_id, self.service.state)
                else:
                    if operation == "disableAll": self.service.enable_all(False)
                    else: self.service.put(replace(alarm, **({"enabled": False} if operation == "disable" else {"hour": 9})))
                    self.assertIsNone(self.service.state[alarm.alarm_id]["snooze"])

    def test_pending_snooze_restored_once_after_restart(self):
        self.alarm()
        self.service.claimed(self.service.events(self.now)[0])
        self.service.snooze(self.now)
        restarted = PersonalAlarmService(self.repo, lambda: self.zone, lambda: self.now)
        event = restarted.events(self.now)[0]
        self.assertTrue(event.metadata["snooze"])
        restarted.claimed(event)
        again = PersonalAlarmService(self.repo, lambda: self.zone, lambda: self.now)
        self.assertFalse(again.events(self.now)[0].metadata["snooze"])

    def test_expired_snooze_is_cleared_and_cannot_revive_on_clock_rollback(self):
        alarm = self.alarm()
        self.service.claimed(self.service.events(self.now)[0])
        self.service.snooze(self.now)
        self.now = Instant(self.now.value + timedelta(minutes=16))
        self.service.events(self.now, include_recent=True)
        self.assertIsNone(self.service.state[alarm.alarm_id]["snooze"])
        self.now = Instant(self.now.value - timedelta(minutes=11))
        self.assertFalse(self.service.events(self.now)[0].metadata["snooze"])

    def test_timezone_change_keeps_computer_wall_time(self):
        alarm = self.alarm(hour=12)
        self.zone = timezone(timedelta(hours=3))
        when = self.service.next_occurrence(alarm, self.now)
        self.assertEqual(12, when.value.hour)
        self.assertEqual(9, utc(when).hour)

    def test_dst_gap_moves_to_first_valid_minute(self):
        self.zone = BundledTimezoneProvider().get_timezone("America/New_York")
        self.now = Instant(datetime(2026, 3, 8, 5, tzinfo=timezone.utc))
        alarm = self.alarm(hour=2, minute=30)
        when = self.service.next_occurrence(alarm, self.now)
        self.assertEqual((3, 0), (when.value.hour, when.value.minute))

    def test_dst_repeated_hour_runs_first_fold_once(self):
        self.zone = BundledTimezoneProvider().get_timezone("America/New_York")
        self.now = Instant(datetime(2026, 11, 1, 4, tzinfo=timezone.utc))
        alarm = self.alarm(hour=1, minute=30)
        when = self.service.next_occurrence(alarm, self.now)
        self.assertEqual(5, utc(when).hour)
        self.service.claimed(self.service._event(alarm, when))
        self.now = Instant(datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(8, self.service.next_occurrence(alarm, self.now).value.day)

    def test_no_writes_for_repeated_schedule_queries(self):
        self.alarm()
        writes = self.repo.writes
        for _ in range(30): self.service.events(self.now)
        self.assertEqual(writes, self.repo.writes)

    def test_corrupt_state_row_fails_closed_without_breaking_other_alarms(self):
        first, second = self.alarm(), self.alarm()
        for broken in (None, [], {"handled": False}, {"snooze": []}):
            self.repo.state = {first.alarm_id: broken}
            restored = PersonalAlarmService(self.repo, lambda: self.zone, lambda: self.now)
            events = restored.events(self.now)
            self.assertEqual([second.alarm_id], [event.metadata["alarm_id"] for event in events])

    def test_disk_failure_at_finish_releases_active_cycle(self):
        self.alarm()
        event = self.service.events(self.now)[0]
        self.service.claimed(event)
        with patch.object(self.repo, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.service.finish(event, "stopped")
        self.assertIsNone(self.service.active)
        self.assertFalse(self.service.events(self.now))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "personal_alarms.json"
    def tearDown(self): self.temp.cleanup()

    def test_upgrade_from_v4_does_not_touch_settings(self):
        settings = self.path.parent / "settings.json"
        original = b'{"schemaVersion":1,"v4":"preserved"}'
        settings.write_bytes(original)
        repo = AlarmRepository(self.path)
        self.assertEqual(({}, {}), repo.load())
        alarm = PersonalAlarm.create("one", 0, 0, (6,))
        repo.save({alarm.alarm_id: alarm}, {})
        restored, state = repo.load()
        self.assertEqual(alarm, restored[alarm.alarm_id])
        self.assertEqual(original, settings.read_bytes())

    def test_partial_corruption_recovers_valid_rows_without_overwriting_original(self):
        repo = AlarmRepository(self.path)
        alarm = PersonalAlarm.create("one", 0, 0, (6,))
        repo.save({alarm.alarm_id: alarm}, {})
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["alarms"].append({"bad": 42})
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        original = self.path.read_bytes()
        alarms, state = repo.load()
        self.assertIn(alarm.alarm_id, alarms)
        with self.assertRaises(OSError): repo.save(alarms, state)
        self.assertEqual(original, self.path.read_bytes())

    def test_invalid_json_and_future_schema_are_preserved(self):
        for raw in ("broken", '{"version":9,"alarms":[],"state":{}}'):
            self.path.write_text(raw)
            repo = AlarmRepository(self.path)
            self.assertEqual(({}, {}), repo.load())
            with self.assertRaises(OSError): repo.save({}, {})
            self.assertEqual(raw, self.path.read_text())

    def test_atomic_failure_preserves_previous_file(self):
        repo = AlarmRepository(self.path)
        repo.save({}, {})
        original = self.path.read_bytes()
        with patch("awqati.infrastructure.alarm_repository.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError): repo.save({}, {"modified": True})
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual([self.path], list(self.path.parent.iterdir()))


class Output:
    def __init__(self, immediate=False):
        self.calls, self.ends, self.cancelled = [], [], 0
        self.immediate = immediate
    def play(self, event, started, finished):
        self.calls.append(event)
        self.ends.append(finished)
        started()
        if self.immediate: finished(OutputResult(True, True))
        return True
    def speak(self, message, started, finished):
        return self.play(message, started, finished)
    def cancel(self): self.cancelled += 1


class IntegrationTests(AlarmsTests):
    def setUp(self):
        super().setUp()
        self.settings = default_settings()
        self.scheduler = AlertScheduler(lambda: self.now, lambda: self.settings,
            personal_local_time_provider=lambda instant: utc(instant).astimezone(self.zone),
            on_discard=self.service.discarded)
        self.audio, self.speech = Output(), Output(immediate=True)
        self.presenter = AlertPresenter(self.scheduler, self.audio, self.speech,
            message_formatter=lambda event, lang: event.metadata.get("name", "prayer"),
            on_claim=self.service.claimed, on_finish=self.service.finish)

    def schedule(self, **kw):
        alarm = self.alarm(**kw)
        self.scheduler.schedule_many(self.service.events(self.now))
        return alarm

    def test_simultaneous_alarms_are_serial_and_both_presented(self):
        first, second = self.schedule(), self.schedule()
        self.presenter.present_next(self.now)
        self.assertEqual(1, len(self.audio.calls))
        self.audio.ends[0](OutputResult(True, True))
        self.assertEqual(2, len(self.audio.calls))
        self.assertNotEqual(self.audio.calls[0].event_id, self.audio.calls[1].event_id)

    def test_prayer_preempts_alarm_and_records_outcome(self):
        alarm = self.schedule(action=AlertAction.SOUND)
        self.presenter.present_next(self.now)
        prayer = AlertEvent("prayer", T.PRAYER_TIME, self.now, action=AlertAction.SPEECH)
        self.scheduler.schedule(prayer)
        self.presenter.present_next(self.now)
        self.assertEqual(1, self.audio.cancelled)
        self.assertEqual("interruptedByPrayer", self.service.state[alarm.alarm_id]["outcome"])

    def test_speech_precedes_loop_without_overlap(self):
        self.schedule()
        order = []
        self.speech = Output()
        self.presenter._speech = self.speech
        self.presenter.present_next(self.now)
        self.assertEqual(1, len(self.speech.calls))
        self.assertEqual(0, len(self.audio.calls))
        self.speech.ends[0](OutputResult(True, True))
        self.assertEqual(1, len(self.audio.calls))

    def test_quiet_default_bypass_and_opt_in(self):
        self.settings.general.quiet_hours.enabled = True
        from awqati.domain import ClockTime
        self.settings.general.quiet_hours.start = ClockTime(0, 0)
        self.settings.general.quiet_hours.end = ClockTime(23, 59)
        alarm = self.schedule(obey_quiet_hours=True)
        self.presenter.present_next(self.now)
        self.assertFalse(self.audio.calls)
        self.assertEqual("quietHours", self.service.state[alarm.alarm_id]["outcome"])
        self.schedule(obey_quiet_hours=False)
        self.assertTrue(self.presenter.present_next(self.now))

    def test_global_switch_suppresses_and_stops_active_alarm(self):
        self.schedule()
        self.presenter.present_next(self.now)
        self.settings.general.all_automatic_alerts_enabled = False
        self.presenter.present_next(self.now)
        self.assertIsNone(self.presenter.current)
        self.assertEqual(1, self.audio.cancelled)

    def test_duration_deadline_stops_and_keeps_recurrence(self):
        alarm = self.schedule(action=AlertAction.SPEECH)
        with patch("awqati.application.alert_presenter.monotonic", return_value=100):
            self.presenter.present_next(self.now)
        self.assertIsNotNone(self.presenter.current)
        with patch("awqati.application.alert_presenter.monotonic", return_value=161):
            self.presenter.present_next(self.now)
        self.assertIsNone(self.presenter.current)
        self.assertEqual("durationElapsed", self.service.state[alarm.alarm_id]["outcome"])
        self.assertTrue(self.service.alarms[alarm.alarm_id].enabled)

    def test_catchup_rebuild_accepts_past_valid_personal_event(self):
        self.alarm()
        self.now = Instant(self.now.value + timedelta(minutes=9))
        events = self.service.events(self.now, include_recent=True)
        self.scheduler.rebuild(events, self.now)
        self.assertTrue(self.presenter.present_next(self.now))

    def test_expired_waiting_alarm_is_recorded(self):
        alarm = self.schedule()
        self.now = Instant(self.now.value + timedelta(minutes=11))
        self.presenter.present_next(self.now)
        self.assertEqual("expiredInQueue", self.service.state[alarm.alarm_id]["outcome"])

    def test_audio_failure_does_not_recurse(self):
        self.schedule()
        self.presenter._audio.play = lambda *args: False
        self.presenter.present_next(self.now)
        self.assertLessEqual(len(self.speech.calls), 2)

    def test_resume_hands_reserved_lease_to_presenter_once(self):
        self.schedule()
        self.now = Instant(self.now.value + timedelta(minutes=2))
        reserved = self.scheduler.resume(self.now, rebuild_source=lambda *args: self.service.events(self.now, include_recent=True))
        self.assertIsNotNone(reserved)
        self.assertTrue(self.presenter.present_next(self.now, reserved=reserved))
        self.assertFalse(self.presenter.present_next(self.now, reserved=reserved))
        self.assertEqual(1, len(self.audio.calls))

    def test_bulk_admission_handles_large_alarm_sets_without_duplicate_keys(self):
        events = [AlertEvent(str(i), T.PERSONAL_ALARM, self.now, action=AlertAction.SPEECH,
            metadata={"name": str(i), "duration": 30}) for i in range(3000)]
        self.assertEqual(3000, self.scheduler.schedule_many(events))
        self.assertEqual(0, self.scheduler.schedule_many(events))
        self.assertEqual(3000, len(self.scheduler.due(self.now)))


class AudioLoopTests(unittest.TestCase):
    def test_same_player_exact_frame_count_repeated_bytes_and_single_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sounds/alarms/alarm.wav"
            path.parent.mkdir(parents=True)
            with wave.open(str(path), "wb") as file:
                file.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
                file.writeframes(bytes(range(256)) * 4)
            class Player:
                def __init__(self): self.data, self.idles, self.stopped = bytearray(), 0, False
                def feed(self, data): self.data.extend(data)
                def idle(self): self.idles += 1
                def stop(self): self.stopped = True
                def close(self): pass
            players = []
            def factory(*args):
                player = Player()
                players.append(player)
                return player
            service = AudioService(SoundFileService(root / "user", root), player_factory=factory,
                dispatch=lambda callback, *args: callback(*args), frames_per_chunk=257)
            event = AlertEvent("alarm", T.PERSONAL_ALARM, Instant(datetime.now(timezone.utc)),
                action=AlertAction.SOUND, metadata={"duration": 1})
            done = threading.Event()
            self.assertTrue(service.play(event, lambda: None, lambda result: done.set()))
            self.assertTrue(done.wait(3))
            self.assertEqual(1, len(players))
            self.assertEqual(bytes(range(256)) * 31 + bytes(range(64)), players[0].data)
            self.assertEqual(1, players[0].idles)

    def test_bundled_sound_is_approved_derivative_with_original_samples_preserved(self):
        with wave.open(str(ROOT / "data_sources/personal_alarm/alarm.original.wav"), "rb") as original:
            original.setpos(44100)
            expected = original.readframes(original.getnframes() - 44100)
        with wave.open(str(ROOT / "addon/globalPlugins/awqati/sounds/alarms/alarm.wav"), "rb") as derived:
            self.assertEqual((2, 2, 44100, 485100), (derived.getnchannels(), derived.getsampwidth(), derived.getframerate(), derived.getnframes()))
            self.assertEqual(expected, derived.readframes(derived.getnframes()))

    def test_custom_sound_fallback_notice_once_and_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sounds/alarms/alarm.wav"
            path.parent.mkdir(parents=True)
            with wave.open(str(path), "wb") as file:
                file.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
                file.writeframes(b"\x80" * 800)
            class Player:
                def feed(self, data): pass
                def idle(self): pass
                def stop(self): pass
                def close(self): pass
            notices = []
            service = AudioService(SoundFileService(root / "user", root), player_factory=lambda *args: Player(),
                dispatch=lambda callback, *args: callback(*args), diagnostic=lambda error: None,
                on_fallback=lambda: notices.append(True))
            event = AlertEvent("alarm", T.PERSONAL_ALARM, Instant(datetime.now(timezone.utc)),
                sound_ref="sounds/alarms/missing.wav", metadata={"duration": .1})
            for _ in range(2):
                done = threading.Event()
                service.play(event, lambda: None, lambda result: done.set())
                self.assertTrue(done.wait(2))
            self.assertEqual([True], notices)
            done = threading.Event()
            service.play_preview(T.PERSONAL_ALARM, path, lambda: None, lambda result: done.set())
            self.assertTrue(done.wait(2))

    def test_cancellation_releases_player_immediately_and_late_worker_is_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "test.wav"
            with wave.open(str(path), "wb") as file:
                file.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
                file.writeframes(b"\x80" * 800)
            gate, entered, stopped = threading.Event(), threading.Event(), threading.Event()
            class Player:
                def feed(self, data):
                    entered.set()
                    gate.wait(2)
                def idle(self): pass
                def stop(self):
                    stopped.set()
                    gate.set()
                def close(self): pass
            service = AudioService(SoundFileService(root, root), player_factory=lambda *args: Player(),
                dispatch=lambda callback, *args: callback(*args))
            done = threading.Event()
            service.play_path(path, lambda: None, lambda result: done.set())
            self.assertTrue(entered.wait(2))
            service.cancel()
            self.assertTrue(stopped.is_set())
            self.assertFalse(service.busy)
            self.assertTrue(done.wait(2))

    def test_existing_settings_preview_cannot_overlap_automatic_alarm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "test.wav"
            with wave.open(str(path), "wb") as file:
                file.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
                file.writeframes(b"\x80" * 800)
            entered, release = threading.Event(), threading.Event()
            class Player:
                def feed(self, data):
                    entered.set()
                    release.wait(2)
                def idle(self): pass
                def stop(self): release.set()
                def close(self): pass
            files = SoundFileService(root, root)
            preview = AudioService(files, player_factory=lambda *args: Player(), dispatch=lambda f, *args: f(*args))
            done = threading.Event()
            preview.play_preview(T.PERSONAL_ALARM, path, lambda: None, lambda result: done.set())
            self.assertTrue(entered.wait(2))
            AudioService.cancel_previews()
            self.assertTrue(done.wait(2))
            self.assertFalse(preview.busy)
            entered.clear(); release.clear(); done.clear()
            automatic = AudioService(files, player_factory=lambda *args: Player(), dispatch=lambda f, *args: f(*args))
            automatic.play_path(path, lambda: None, lambda result: done.set())
            self.assertTrue(entered.wait(2))
            self.assertFalse(preview.play_preview(T.PERSONAL_ALARM, path, lambda: None, lambda result: None))
            automatic.cancel()
            self.assertTrue(done.wait(2))


if __name__ == "__main__": unittest.main()
