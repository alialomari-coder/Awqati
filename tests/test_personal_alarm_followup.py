"""Corrective command/message tests, including real scheduler and persistence paths."""
import ast
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.domain import AlertAction, AlertEvent, AlertEventType, Instant, default_settings
from awqati.domain.personal_alarms import PersonalAlarm, validate_alarm_fields
from awqati.application.events import EventDispatcher
from awqati.application.personal_alarms import PersonalAlarmService
from awqati.application.alert_scheduler import AlertScheduler
from awqati.application.alert_presenter import AlertPresenter
from awqati.nvda_adapter import compat
from awqati.nvda_adapter.duration_formatter import format_minutes
from awqati.nvda_adapter.runtime import AwqatiRuntime
from tests.test_corrective_followup import Translator
from tests import test_personal_alarms as base

PLUGIN = ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py"


def command_driver(runtime, language, messages):
    """Execute the production methods without importing the NVDA GUI composition."""
    tree = ast.parse(PLUGIN.read_text(encoding="utf-8"))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GlobalPlugin")
    names = {"_press", "script_personalAlarmInfo", "script_stopPersonalAlarm", "script_snoozePersonalAlarm",
        "_stopPersonalAlarm", "_snoozePersonalAlarm"}
    functions = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in functions:
        node.decorator_list = []
    original.body, original.bases, original.decorator_list = functions, [], []
    namespace = dict(compat=compat, ui=SimpleNamespace(message=messages.append),
        _=Translator(language), AlertEventType=AlertEventType, format_minutes=format_minutes,
        next_alarm_text=lambda runtime: "next alarm")
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])), str(PLUGIN), "exec"), namespace)
    driver = namespace["GlobalPlugin"]()
    driver._runtime = runtime
    return driver


def editor_validation_driver(hour, minute, days, limit, language="ar"):
    """Exercise production validation; no Windows input or dialogs are simulated."""
    source = ROOT / "addon/globalPlugins/awqati/nvda_adapter/alarm_dialogs.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AlarmEditor")
    original.body = [node for node in original.body if isinstance(node, ast.FunctionDef) and node.name == "save"]
    original.bases, original.decorator_list = [], []
    namespace = {"_": Translator(language), "DAY_ORDER": (6, 0, 1, 2, 3, 4, 5), "validate_alarm_fields": validate_alarm_fields}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])), str(source), "exec"), namespace)
    editor = namespace["AlarmEditor"]()
    editor.hour = SimpleNamespace(GetValue=lambda: hour)
    editor.minute = SimpleNamespace(GetValue=lambda: minute)
    editor.days = SimpleNamespace(GetSelections=lambda: days)
    editor.limit = SimpleNamespace(GetValue=lambda: limit)
    editor.unlimited = SimpleNamespace(GetValue=lambda: False)
    editor._busy = False
    editor.errors = []
    editor.error = lambda message, field: editor.errors.append((message, field))
    return editor


class AlarmCommandFollowupTests(unittest.TestCase):
    def setUp(self):
        native = patch.dict(sys.modules, {"scriptHandler": SimpleNamespace(getLastScriptRepeatCount=lambda: 0)})
        native.start()
        self.addCleanup(native.stop)
        self.now = Instant(datetime(2026, 11, 1, 8, tzinfo=timezone.utc))
        self.repo = base.MemoryRepository()
        alarms = PersonalAlarmService(self.repo, lambda: timezone.utc, lambda: self.now)
        runtime = self.runtime = AwqatiRuntime.__new__(AwqatiRuntime)
        runtime.alarms = alarms
        runtime.now = SimpleNamespace(now=lambda: self.now)
        runtime.settings = SimpleNamespace(runtime_settings=default_settings())
        runtime.scheduler = AlertScheduler(lambda: self.now, lambda: runtime.settings.runtime_settings)
        runtime.audio, runtime.speech, runtime.previews = base.Output(), base.Output(immediate=True), set()
        runtime._alarm_error = lambda error: None
        runtime.presenter = AlertPresenter(runtime.scheduler, runtime.audio, runtime.speech,
            on_claim=runtime._claim, on_finish=alarms.finish)
        runtime._last_snooze = None
        runtime.last_snooze_minutes = None
        runtime._reschedule = lambda: None
        self.messages = []

    def start(self, **options):
        alarm = PersonalAlarm.create("Alarm", 8, 0, (6,), action=AlertAction.SOUND, **options)
        self.runtime.alarms.put(alarm)
        self.runtime.scheduler.schedule_many(self.runtime.alarms.events(self.now))
        self.runtime.presenter.present_next(self.now)
        return alarm

    def test_each_native_repeat_count_chooses_one_branch(self):
        driver = command_driver(self.runtime, "en", self.messages)
        for count in range(4):
            with self.subTest(count=count), patch.object(compat, "script_repeat_count", return_value=count), \
                    patch.object(driver, "_snoozePersonalAlarm") as snooze, patch.object(driver, "_stopPersonalAlarm") as stop:
                self.messages.clear()
                driver.script_personalAlarmInfo(None)
                self.assertFalse(snooze.called)
                self.assertEqual(count == 2, stop.called)
                self.assertEqual(1 if count < 2 else 0, len(self.messages))

    def test_owner_approved_triple_stop_never_creates_snooze(self):
        alarm = self.start(snooze_minutes=5)
        driver = command_driver(self.runtime, "ar", self.messages)
        for count in range(4):
            with patch.object(compat, "script_repeat_count", return_value=count):
                driver.script_personalAlarmInfo(None)
        self.assertEqual("next alarm", self.messages[0])
        self.assertEqual("عدد المنبهات الشخصية المفعلة: 1.", self.messages[1])
        self.assertEqual("تم إيقاف المنبه الجاري", self.messages[2])
        self.assertEqual(3, len(self.messages))
        self.assertIsNone(self.runtime._last_snooze)
        self.assertIsNone(self.runtime.alarms.state[alarm.alarm_id]["snooze"])
        self.assertTrue(self.runtime.alarms.alarms[alarm.alarm_id].enabled)
        self.assertFalse(any(event.metadata["snooze"] for event in self.runtime.scheduler._events.values()))

    def test_no_current_alarm_has_its_own_message(self):
        command_driver(self.runtime, "ar", self.messages).script_snoozePersonalAlarm(None)
        self.assertEqual(["لا يوجد منبه جارٍ لتأجيله"], self.messages)

    def test_disabled_and_exhausted_snooze_use_unavailable_message(self):
        for options in (dict(snooze_enabled=False), dict(snooze_limit=1)):
            with self.subTest(options=options):
                self.setUp()
                alarm = self.start(**options)
                if options.get("snooze_limit"):
                    self.runtime.alarms.state[alarm.alarm_id]["count"] = 1
                command_driver(self.runtime, "ar", self.messages).script_snoozePersonalAlarm(None)
                self.assertEqual(["الغفوة غير متاحة. قد تكون معطلة أو استُنفد عددها"], self.messages)
                self.assertIsNotNone(self.runtime.presenter.current)

    def test_all_actual_snooze_durations_in_both_languages(self):
        words = {1: "دقيقة واحدة", 2: "دقيقتين", 5: "خمس دقائق", 10: "عشر دقائق", 15: "خمس عشرة دقيقة", 30: "ثلاثين دقيقة"}
        for language in ("ar", "en"):
            for minutes, word in words.items():
                with self.subTest(language=language, minutes=minutes):
                    self.setUp()
                    alarm = self.start(snooze_minutes=minutes)
                    before = self.repo.writes
                    command_driver(self.runtime, language, self.messages).script_snoozePersonalAlarm(None)
                    pending = datetime.fromisoformat(self.runtime.alarms.state[alarm.alarm_id]["snooze"])
                    self.assertEqual(minutes * 60, (pending - self.now.value).total_seconds())
                    self.assertEqual(before + 1, self.repo.writes)  # No redundant save at cancellation.
                    expected = "تم تفعيل وضع الغفوة. سيعود المنبه بعد " + word if language == "ar" else f"Personal alarm snoozed. The alarm will ring again in {minutes} minute{'s' if minutes != 1 else ''}."
                    self.assertEqual([expected], self.messages)
                    self.assertTrue(any(event.metadata["snooze"] for event in self.runtime.scheduler._events.values()))

    def test_failure_to_save_never_announces_or_schedules_success(self):
        alarm = self.start()
        original = dict(self.runtime.alarms.state[alarm.alarm_id])
        with patch.object(self.repo, "save", side_effect=OSError("disk full")):
            command_driver(self.runtime, "ar", self.messages).script_snoozePersonalAlarm(None)
        self.assertEqual(["تعذر حفظ الغفوة. لن يتم تأجيل المنبه"], self.messages)
        self.assertEqual(original, self.runtime.alarms.state[alarm.alarm_id])
        self.assertIsNotNone(self.runtime.presenter.current)
        self.assertFalse(any(event.metadata["snooze"] for event in self.runtime.scheduler._events.values()))

    def test_success_requires_admission_to_scheduler(self):
        alarm = self.start()
        self.runtime.alarms_changed = lambda: None
        command_driver(self.runtime, "ar", self.messages).script_snoozePersonalAlarm(None)
        self.assertEqual(["الغفوة غير متاحة. قد تكون معطلة أو استُنفد عددها"], self.messages)
        self.assertIsNone(self.runtime.alarms.state[alarm.alarm_id]["snooze"])
        self.assertIsNone(self.runtime.last_snooze_minutes)

    def test_independent_commands_delegate_to_same_helpers(self):
        driver = command_driver(self.runtime, "en", self.messages)
        with patch.object(driver, "_stopPersonalAlarm") as stop, patch.object(driver, "_snoozePersonalAlarm") as snooze:
            driver.script_stopPersonalAlarm(None)
            driver.script_snoozePersonalAlarm(None)
            stop.assert_called_once_with()
            snooze.assert_called_once_with()

    def test_stop_is_executed_before_success_and_keeps_definition(self):
        alarm = self.start()
        command_driver(self.runtime, "ar", self.messages).script_stopPersonalAlarm(None)
        self.assertIsNone(self.runtime.presenter.current)
        self.assertEqual(1, self.runtime.audio.cancelled)
        self.assertTrue(self.runtime.alarms.alarms[alarm.alarm_id].enabled)
        self.assertEqual(["تم إيقاف المنبه الجاري"], self.messages)

    def test_failure_to_cancel_pending_snooze_never_announces_stop_success(self):
        alarm = self.start()
        self.runtime.snooze_alarm()
        pending = self.runtime.alarms.state[alarm.alarm_id]["snooze"]
        with patch.object(self.repo, "save", side_effect=OSError("disk full")):
            command_driver(self.runtime, "en", self.messages).script_stopPersonalAlarm(None)
        self.assertEqual(["The pending snooze could not be cancelled. No successful stop was recorded."], self.messages)
        self.assertEqual(pending, self.runtime.alarms.state[alarm.alarm_id]["snooze"])

    def test_non_prayer_high_priority_alert_does_not_claim_prayer_interruption(self):
        alarm = self.start()
        self.runtime.scheduler.schedule(AlertEvent("sunrise", AlertEventType.SUNRISE, self.now, action=AlertAction.SPEECH))
        self.runtime.presenter.present_next(self.now)
        self.assertEqual("interruptedByTimeAlert", self.runtime.alarms.state[alarm.alarm_id]["outcome"])


class MessageAndDataFollowupTests(unittest.TestCase):
    def test_post_save_schedule_failure_is_not_reported_as_preserved_previous_data(self):
        source = ROOT / "addon/globalPlugins/awqati/nvda_adapter/alarm_dialogs.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "reschedule_saved_changes")
        messages = []
        namespace = {"_": Translator("en"), "wx": SimpleNamespace(OK=1, ICON_ERROR=2, MessageBox=lambda message, *args: messages.append(message))}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(source), "exec"), namespace)
        def failed(): raise OSError("schedule unavailable")
        namespace["reschedule_saved_changes"](None, SimpleNamespace(alarms_changed=failed))
        self.assertEqual(["The changes were saved, but the alarm schedule could not be updated. Restart NVDA before relying on the changed alarms."], messages)

    def test_editor_retains_time_fields_and_targets_first_invalid_field(self):
        cases = (("", "", (), "hour"), ("0", "", (), "minute"), ("0", "0", (), "days"))
        for hour, minute, days, target in cases:
            with self.subTest(hour=hour, minute=minute):
                editor = editor_validation_driver(hour, minute, days, "3")
                editor.save()
                self.assertEqual(1, len(editor.errors))
                self.assertIs(getattr(editor, target), editor.errors[0][1])
                self.assertEqual(hour, editor.hour.GetValue())
                self.assertEqual(minute, editor.minute.GetValue())

    def test_editor_rejects_invalid_snooze_count_without_disclosing_internal_limit(self):
        for language in ("ar", "en"):
            for value in ("", "0", "-1", "1.5", "invalid", "1000001"):
                with self.subTest(language=language, value=value):
                    editor = editor_validation_driver("0", "0", (0,), value, language)
                    editor.save()
                    self.assertEqual(1, len(editor.errors))
                    message, field = editor.errors[0]
                    self.assertIs(editor.limit, field)
                    self.assertNotIn("1000000", message)
                    self.assertEqual(value, editor.limit.GetValue())

    def test_exact_arabic_messages_and_unchanged_valid_english_sources(self):
        pairs = {
            "Specify an alarm time and at least one day of the week.": "يجب تحديد وقت المنبه واختيار يوم واحد على الأقل من أيام الأسبوع",
            "The alarm could not be saved. Existing data has been preserved.": "تعذر حفظ المنبه. تم الاحتفاظ بالبيانات السابقة",
            "Enter a positive whole number of snoozes, or choose unlimited.": "أدخل عددًا صحيحًا موجبًا للغفوات، أو اختر دون حد",
            "Some personal alarm data could not be read. Existing data has been preserved unchanged.": "تعذر قراءة بعض بيانات المنبهات الشخصية. تم الاحتفاظ بالبيانات السابقة دون تغيير",
            "Last cycle interrupted by a prayer alert.": "توقف رنين المنبه السابق بسبب تنبيه الصلاة",
            "Personal alarm stopped.": "تم إيقاف المنبه الجاري",
            "Snooze is unavailable. It may be disabled or exhausted.": "الغفوة غير متاحة. قد تكون معطلة أو استُنفد عددها",
            "The snooze could not be saved. The alarm has not been postponed.": "تعذر حفظ الغفوة. لن يتم تأجيل المنبه",
        }
        for source, arabic in pairs.items():
            with self.subTest(source=source):
                self.assertEqual(arabic, Translator("ar")(source))
                self.assertEqual(source, Translator("en")(source))

    def test_day_requirement_and_numeric_snooze_limits_unchanged(self):
        self.assertEqual("timeAndDays", validate_alarm_fields("", "", ()))
        self.assertEqual("days", validate_alarm_fields("0", "0", ()))
        self.assertIsNone(validate_alarm_fields("0", "0", (6,)))
        for invalid in (0, -1, True, 1.5, 1000001):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                PersonalAlarm.create("test", 0, 0, (6,), snooze_limit=invalid)
        self.assertEqual(1000000, PersonalAlarm.create("test", 0, 0, (6,), snooze_limit=1000000).snooze_limit)

    def test_cancel_pending_snooze_does_not_touch_a_different_cycle(self):
        repo = base.MemoryRepository()
        service = PersonalAlarmService(repo, lambda: timezone.utc, lambda: None)
        alarm = PersonalAlarm.create("test", 0, 0, (6,))
        service.put(alarm)
        self.assertFalse(service.cancel_snooze(alarm.alarm_id, "old-cycle"))

    def test_read_error_notice_preserves_invalid_file_without_write_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "personal_alarms.json"
            path.write_bytes(b"invalid JSON")
            notices = []
            settings = SimpleNamespace(runtime_settings=default_settings(), events=EventDispatcher())
            now = SimpleNamespace(now=lambda: Instant(datetime(2026, 11, 1, tzinfo=timezone.utc)))
            source = SimpleNamespace(next_rebuild_at=lambda now: None, settings_changed=lambda *args: None)
            class Source:
                def __call__(self, *args): return ()
                def next_rebuild_at(self, now): return None
                def settings_changed(self, *args): pass
            with patch("awqati.nvda_adapter.runtime.ComputerTimezone", return_value=lambda: timezone.utc), \
                    patch("awqati.nvda_adapter.runtime.PrayerClockRebuildSource.from_services", return_value=Source()), \
                    patch.object(compat, "call_after", side_effect=lambda f, *args: f(*args)), \
                    patch.object(compat, "schedule", return_value=SimpleNamespace(cancel=lambda: None)):
                runtime = AwqatiRuntime(settings, now, None, None, user_data_root=root, addon_root=root,
                    language_provider=lambda: "en", on_error=lambda error: None,
                    on_alarm_read_error=lambda: notices.append("read"), on_alarm_data_error=lambda: notices.append("write"))
                self.assertEqual(["read"], notices)
                self.assertEqual(b"invalid JSON", path.read_bytes())
                runtime._alarm_error(OSError("disk full"))
                self.assertEqual(["read", "write"], notices)
                runtime.close()


if __name__ == "__main__": unittest.main()
