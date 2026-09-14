"""Task 4.2 acceptance with explicit test windows, never a production horizon."""

import ast
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.application import AlertCoordinator, AlertScheduler, SettingsService
from awqati.application.alert_formatters import format_clock_alert, format_prayer_alert
from awqati.application.clock_alert_producer import ClockAlertProducer
from awqati.application.prayer_alert_producer import PrayerAlertProducer
from awqati.application.prayer_clock_rebuild_source import PrayerClockRebuildSource
from awqati.application.prayer_state import EventPreAlertSettings, IqamaSettings, IqamaRule, PrayerStateService
from awqati.domain import (AlertAction, AlertEventType as T, AlertTiming, ClockReading,
	ClockType, Instant, Location, LocationKind, SoundReference, StoredLocation, default_settings)
from awqati.domain.alerts import GRACE_PERIODS, priority_for, utc
from awqati.domain.prayer_timeline import PRAYER_EVENT_NAMES, PrayerEvent, PrayerEventName as N
from awqati.infrastructure import BundledTimezoneProvider


def instant(hour=0, minute=0, day=15):
	return Instant(datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc))


class Clock:
	def __init__(self, value): self.value = value
	def now(self): return self.value


class Repository:
	def __init__(self, value): self.value = deepcopy(value)
	def load(self): return deepcopy(self.value)
	def save(self, value): self.value = deepcopy(value)


class Fixture:
	def setUp(self):
		self.settings = default_settings()
		self.settings.location = StoredLocation(LocationKind.SELECTED,
			Location("test", "Test", 24.7, 46.7, "Asia/Riyadh"), "SA")
		self.references = tuple(PrayerEvent(name, instant(hour).value) for name, hour in
			zip(N, (5, 6, 12, 15, 18, 20, 22, 23)))
		self.start, self.end = instant(), instant(day=16)
		self.prayer = PrayerAlertProducer(lambda: self.settings, lambda *_: self.references)
		self.zones = BundledTimezoneProvider()
		self.readings = Mock(side_effect=self.reading)
		self.clock_producer = ClockAlertProducer(lambda: self.settings, self.zones.get_timezone, self.readings)

	def reading(self, at):
		zone = self.zones.get_timezone(self.settings.location.location.timezone_id)
		return ClockReading(at.value.astimezone(zone), timedelta(hours=1), at.value - timedelta(hours=1))

	def prayer_events(self): return self.prayer.produce(self.start, self.end)
	def clock_events(self): return self.clock_producer.produce(self.start, self.end)
	def of_type(self, kind): return [event for event in self.prayer_events() if event.event_type is kind]
	def select_intervals(self, *minutes):
		self.settings.clock.automatic_alert_enabled = True
		for minute, name in ((0, "on_hour"), (15, "on_quarter"), (30, "on_half"), (45, "on_three_quarters")):
			setattr(self.settings.clock.intervals, name, minute in minutes)


class PrayerProducerTests(Fixture, unittest.TestCase):
	def test_all_eight_prealerts(self):
		events = self.of_type(T.PRAYER_PRE_ALERT)
		self.assertEqual({event.metadata["event_name"] for event in events}, {name.value for name in N})
		for event in events:
			self.assertEqual(utc(event.reference_at) - utc(event.scheduled_at), timedelta(minutes=10))
			self.assertIs(event.timing, AlertTiming.BEFORE)

	def test_pre_zero_disables_only_prealert(self):
		for config in self.settings.prayer.events.values(): config.pre_alert_minutes = 0
		self.assertEqual(self.of_type(T.PRAYER_PRE_ALERT), [])
		self.assertEqual(len(self.of_type(T.PRAYER_TIME)), 5)

	def test_pre_reference_is_exclusive_even_after_default_grace(self):
		for config in self.settings.prayer.events.values(): config.pre_alert_minutes = 30
		for event in self.of_type(T.PRAYER_PRE_ALERT):
			self.assertTrue(event.is_valid_at(Instant(utc(event.reference_at) - timedelta(microseconds=1))))
			self.assertFalse(event.is_valid_at(event.reference_at))
			self.assertFalse(event.is_valid_at(Instant(utc(event.reference_at) + timedelta(seconds=1))))

	def test_five_prayer_entries_and_three_point_entries(self):
		for kind, count in ((T.PRAYER_TIME, 5), (T.SUNRISE, 1), (T.MIDNIGHT, 1), (T.LAST_THIRD, 1)):
			with self.subTest(kind=kind):
				events = self.of_type(kind)
				self.assertEqual(len(events), count)
				self.assertTrue(all(event.scheduled_at == event.reference_at for event in events))

	def test_iqama_defaults_and_estimated_reference(self):
		expected = {"fajr": 25, "dhuhr": 20, "asr": 20, "maghrib": 10, "isha": 20}
		events = self.of_type(T.IQAMA_PRE_ALERT)
		self.assertEqual(len(events), 5)
		for event in events:
			self.assertEqual(utc(event.reference_at) - utc(event.metadata["prayer_at"]),
				timedelta(minutes=expected[event.metadata["event_name"]]))
			self.assertEqual(utc(event.reference_at) - utc(event.scheduled_at), timedelta(minutes=5))
			self.assertEqual(event.metadata["reference_kind"], "userEstimatedIqama")
			self.assertFalse(event.is_valid_at(event.reference_at))

	def test_iqama_custom_settings(self):
		for name in PRAYER_EVENT_NAMES:
			self.settings.prayer.events[name].iqama.delay_minutes = 42
			self.settings.prayer.events[name].iqama.alert_before_minutes = 7
		for event in self.of_type(T.IQAMA_PRE_ALERT):
			self.assertEqual(utc(event.scheduled_at) - utc(event.metadata["prayer_at"]), timedelta(minutes=35))

	def test_iqama_zero_delay_disables(self):
		for name in PRAYER_EVENT_NAMES: self.settings.prayer.events[name].iqama.delay_minutes = 0
		self.assertEqual(self.of_type(T.IQAMA_PRE_ALERT), [])

	def test_iqama_zero_before_keeps_calculated_time(self):
		for name in PRAYER_EVENT_NAMES: self.settings.prayer.events[name].iqama.alert_before_minutes = 0
		self.assertEqual(self.of_type(T.IQAMA_PRE_ALERT), [])
		state = PrayerStateService(Clock(instant(5, 5))).snapshot(self.references,
			iqama=IqamaSettings({name: IqamaRule(config.iqama.delay_minutes, 0)
				for name, config in self.settings.prayer.events.items() if name in PRAYER_EVENT_NAMES}))
		self.assertEqual(state.iqama_at, instant(5, 25).value)

	def test_no_separate_event_at_iqama(self):
		for iqama in self.of_type(T.IQAMA_PRE_ALERT):
			self.assertFalse(any(event.scheduled_at == iqama.reference_at for event in self.prayer_events()))

	def test_post_defaults(self):
		events = self.of_type(T.PRAYER_POST_ALERT)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].metadata["event_name"], "sunrise")
		self.assertEqual(events[0].scheduled_at, instant(6, 20))

	def test_custom_post_for_all_three_point_events(self):
		for name in set(N) - PRAYER_EVENT_NAMES: self.settings.prayer.events[name].post_alert_minutes = 17
		events = self.of_type(T.PRAYER_POST_ALERT)
		self.assertEqual(len(events), 3)
		for event in events:
			self.assertEqual(utc(event.scheduled_at) - utc(event.reference_at), timedelta(minutes=17))

	def test_post_zero_disables(self):
		self.settings.prayer.events[N.SUNRISE].post_alert_minutes = 0
		self.assertEqual(self.of_type(T.PRAYER_POST_ALERT), [])

	def test_silent_pre_preserves_waiting(self):
		for config in self.settings.prayer.events.values(): config.pre_alert.action = AlertAction.SILENT
		before = deepcopy(self.settings)
		self.assertEqual(self.of_type(T.PRAYER_PRE_ALERT), [])
		self.assertEqual(self.settings, before)
		state = PrayerStateService(Clock(instant(4, 55))).snapshot(self.references,
			pre_alerts=EventPreAlertSettings({name: config.pre_alert_minutes for name, config in self.settings.prayer.events.items()}))
		self.assertEqual(state.waiting_window.event.name, N.FAJR)
		self.assertEqual(state.waiting_window.starts_at, instant(4, 50).value)

	def test_post_does_not_extend_current_state(self):
		service = PrayerStateService(Clock(instant(6, 5)))
		before = service.snapshot(self.references)
		self.settings.prayer.events[N.SUNRISE].post_alert_minutes = 180
		self.prayer_events()
		self.assertEqual(service.snapshot(self.references), before)
		self.assertIsNone(before.current_prayer)

	def test_all_silent_outputs_produce_nothing(self):
		for config in self.settings.prayer.events.values():
			for output in (config.pre_alert, config.at_time_alert,
				config.iqama.alert if config.iqama else config.post_alert): output.action = AlertAction.SILENT
		self.assertEqual(self.prayer_events(), ())

	def test_disabled_does_not_fetch_timeline(self):
		self.settings.prayer.alerts_enabled = False
		provider = Mock(side_effect=AssertionError("disabled calculation"))
		self.assertEqual(PrayerAlertProducer(lambda: self.settings, provider).produce(self.start, self.end), ())
		provider.assert_not_called()

	def test_from_now_filters_by_alert_not_reference(self):
		self.start = instant(5, 10)
		events = self.prayer_events()
		self.assertTrue(all(utc(e.scheduled_at) >= utc(self.start) for e in events))
		self.assertTrue(any(e.event_type is T.IQAMA_PRE_ALERT and e.metadata["event_name"] == "fajr" for e in events))

	def test_reference_beyond_end_can_have_prealert_inside(self):
		self.end = instant(4, 55)
		events = self.prayer_events()
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].scheduled_at, instant(4, 50))

	def test_occurrence_ids_stable_and_next_day_distinct(self):
		first = self.prayer_events()
		second = self.prayer_events()
		self.assertEqual(first, second)
		self.assertTrue(all(a is not b for a, b in zip(first, second)))
		self.assertEqual(len({e.event_id for e in first}), len(first))
		self.references = tuple(PrayerEvent(e.name, e.occurs_at + timedelta(days=1)) for e in self.references)
		self.start, self.end = instant(day=16), instant(day=17)
		self.assertFalse({e.dedup_key for e in first} & {e.dedup_key for e in self.prayer_events()})

	def test_action_and_sound_are_copied_without_output(self):
		config = self.settings.prayer.events[N.FAJR].at_time_alert
		config.action, config.sound = AlertAction.SOUND_AND_SPEECH, SoundReference("sounds/fajr.wav")
		event = next(e for e in self.of_type(T.PRAYER_TIME) if e.metadata["event_name"] == "fajr")
		self.assertEqual((event.action, event.sound_ref), (config.action, "sounds/fajr.wav"))
		config.sound.value = "sounds/changed.wav"
		self.assertEqual(event.sound_ref, "sounds/fajr.wav")

	def test_domain_priority_and_grace_used_for_every_event(self):
		for event in self.prayer_events():
			self.assertEqual(event.grace_period, GRACE_PERIODS[event.event_type])
			self.assertEqual(event.priority, priority_for(event.event_type))

	def test_elapsed_offsets_across_dst_gap_and_fold(self):
		zone = self.zones.get_timezone("Europe/London")
		for day in (datetime(2026, 3, 29, 0, 50, tzinfo=zone), datetime(2026, 10, 25, 1, 50, tzinfo=zone)):
			with self.subTest(day=day):
				self.references = (PrayerEvent(N.FAJR, day),)
				self.start, self.end = Instant(day.astimezone(timezone.utc) - timedelta(hours=1)), Instant(day.astimezone(timezone.utc) + timedelta(hours=2))
				event = self.of_type(T.IQAMA_PRE_ALERT)[0]
				self.assertEqual(utc(event.reference_at) - day.astimezone(timezone.utc), timedelta(minutes=25))
				self.assertEqual(utc(event.reference_at) - utc(event.scheduled_at), timedelta(minutes=5))


class ClockProducerTests(Fixture, unittest.TestCase):
	def test_disabled_preserves_settings_and_does_no_reading(self):
		before = deepcopy(self.settings.clock)
		self.assertEqual(self.clock_events(), ())
		self.readings.assert_not_called()
		self.assertEqual(self.settings.clock, before)

	def test_no_intervals(self):
		self.select_intervals()
		self.assertEqual(self.clock_events(), ())
		self.readings.assert_not_called()

	def test_each_individual_interval(self):
		for minute in (0, 15, 30, 45):
			with self.subTest(minute=minute):
				self.select_intervals(minute)
				events = self.clock_events()
				self.assertEqual(len(events), 24)
				self.assertEqual({e.scheduled_at.value.minute for e in events}, {minute})

	def test_multiple_intervals_exclude_unselected(self):
		self.select_intervals(15, 45)
		events = self.clock_events()
		self.assertEqual(len(events), 48)
		self.assertEqual({e.scheduled_at.value.minute for e in events}, {15, 45})

	def test_exact_boundaries_and_exclusive_end(self):
		self.select_intervals(0, 15, 30, 45)
		for minute in (0, 15, 30, 45):
			start = instant(12, minute)
			events = self.clock_producer.produce(start, Instant(utc(start) + timedelta(minutes=15)))
			self.assertEqual(len(events), 1)
			self.assertEqual(utc(events[0].scheduled_at), utc(start))
			after = Instant(utc(start) + timedelta(microseconds=1))
			self.assertEqual(self.clock_producer.produce(after, Instant(utc(start) + timedelta(minutes=15))), ())

	def test_effective_timezone(self):
		self.select_intervals(0)
		event = self.clock_events()[0]
		self.assertEqual(event.scheduled_at.value.hour, 3)
		self.assertEqual(event.metadata["timezone_id"], "Asia/Riyadh")

	def test_missing_location_has_no_events(self):
		self.select_intervals(0)
		self.settings.location = None
		self.assertEqual(self.clock_events(), ())

	def test_actions_and_sound_all_supported(self):
		self.select_intervals(0)
		for action in (AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH):
			self.settings.clock.alert.action = action
			self.settings.clock.alert.sound = SoundReference("sounds/clock.wav")
			event = self.clock_events()[0]
			self.assertEqual((event.action, event.sound_ref), (action, "sounds/clock.wav"))

	def test_neutral_reading_and_formatter_snapshot(self):
		self.select_intervals(0)
		event = self.clock_events()[0]
		self.assertEqual(utc(Instant(event.metadata["reading"].zawali)), utc(event.scheduled_at))
		self.assertTrue(format_clock_alert(event, "ar"))
		self.assertTrue(format_clock_alert(event, "en"))
		self.settings.clock.presentations[ClockType.ZAWALI].speak_seconds = True
		self.assertFalse(event.metadata["presentations"][ClockType.ZAWALI].speak_seconds)

	def test_ids_unique_and_stable(self):
		self.select_intervals(0, 15, 30, 45)
		a, b = self.clock_events(), self.clock_events()
		self.assertEqual([e.dedup_key for e in a], [e.dedup_key for e in b])
		self.assertEqual(len({e.event_id for e in a}), 96)

	def test_gap_resolves_to_first_valid_time_once(self):
		self.select_intervals(0, 15, 30, 45)
		self.settings.location.location = Location("london", "London", 51.5, 0, "Europe/London")
		self.start = Instant(datetime(2026, 3, 29, 0, tzinfo=timezone.utc))
		self.end = Instant(datetime(2026, 3, 29, 3, tzinfo=timezone.utc))
		events = self.clock_events()
		self.assertEqual(len(events), 12)
		self.assertEqual(sum(e.scheduled_at.value.hour == 2 and e.scheduled_at.value.minute == 0 for e in events), 1)
		self.assertFalse(any(e.scheduled_at.value.hour == 1 for e in events))

	def test_fold_fires_only_first_occurrence_and_no_replay(self):
		self.select_intervals(0, 15, 30, 45)
		self.settings.location.location = Location("london", "London", 51.5, 0, "Europe/London")
		self.start = Instant(datetime(2026, 10, 25, 0, tzinfo=timezone.utc))
		self.end = Instant(datetime(2026, 10, 25, 3, tzinfo=timezone.utc))
		events = self.clock_events()
		self.assertEqual(sum(e.scheduled_at.value.hour == 1 for e in events), 4)
		self.assertTrue(all(e.scheduled_at.value.fold == 0 for e in events))
		self.start = Instant(datetime(2026, 10, 25, 1, tzinfo=timezone.utc))
		self.assertFalse(any(e.scheduled_at.value.hour == 1 for e in self.clock_events()))

	def test_clock_domain_policy(self):
		self.select_intervals(0)
		for event in self.clock_events():
			self.assertEqual(event.grace_period, GRACE_PERIODS[T.CLOCK])
			self.assertEqual(event.priority, priority_for(T.CLOCK))

	def test_invalid_windows(self):
		for producer in (self.prayer, self.clock_producer):
			with self.assertRaises(ValueError): producer.produce(self.start, self.start)


class RebuildIntegrationTests(Fixture, unittest.TestCase):
	def setUp(self):
		super().setUp()
		self.select_intervals(0, 15, 30, 45)
		self.clock = Clock(instant(4, 40))
		self.service = SettingsService(Repository(self.settings), self.clock)
		self.prayer = PrayerAlertProducer(lambda: self.service.runtime_settings, lambda *_: self.references)
		self.clock_producer = ClockAlertProducer(lambda: self.service.runtime_settings, self.zones.get_timezone, self.readings)
		self.source = PrayerClockRebuildSource(self.prayer, self.clock_producer, lambda: self.service.runtime_settings, self.zones.get_timezone)
		self.scheduler = AlertScheduler(self.clock, lambda: self.service.runtime_settings)
		self.coordinator = AlertCoordinator(self.scheduler, self.service.events, self.source)
		self.scheduler.rebuild(self.source(self.clock.now(), "test", None), self.clock.now())

	def apply(self, change):
		draft = self.service.open_draft()
		change(draft.settings)
		return self.service.apply(draft)

	def test_scopes_and_unknown_scope(self):
		for scope in ("prayer", "clock", None):
			events = self.source(self.clock.now(), "test", scope)
			self.assertEqual({e.scope for e in events}, {scope} if scope else {"prayer", "clock"})
		self.assertEqual(self.source(self.clock.now(), "test", "adhkar"), ())

	def test_disable_each_section_cancels_only_its_scope(self):
		for scope, key in (("prayer", "alerts_enabled"), ("clock", "automatic_alert_enabled")):
			with self.subTest(scope=scope):
				before = deepcopy(getattr(self.service.runtime_settings, scope))
				self.apply(lambda settings: setattr(getattr(settings, scope), key, False))
				self.assertFalse(any(e.scope == scope for e in self.scheduler._events.values()))
				setattr(before, key, False)
				self.assertEqual(getattr(self.service.runtime_settings, scope), before)
				self.apply(lambda settings: setattr(getattr(settings, scope), key, True))

	def test_reactivation_has_no_catchup(self):
		self.apply(lambda settings: setattr(settings.general, "all_automatic_alerts_enabled", False))
		self.clock.value = instant(5, 10)
		self.apply(lambda settings: setattr(settings.general, "all_automatic_alerts_enabled", True))
		self.assertTrue(self.scheduler._events)
		self.assertTrue(all(utc(e.scheduled_at) >= utc(self.clock.now()) for e in self.scheduler._events.values()))
		self.assertEqual(self.scheduler.due(), ())

	def test_clock_change_preserves_prayer_objects(self):
		before = {e.event_id: e for e in self.scheduler._events.values() if e.scope == "prayer"}
		self.apply(lambda settings: setattr(settings.clock.intervals, "on_quarter", False))
		self.assertTrue(all(self.scheduler._events[key] is event for key, event in before.items()))
		self.assertFalse(any(e.scope == "clock" and e.metadata["interval_minute"] == 15 for e in self.scheduler._events.values()))

	def test_prayer_change_preserves_clock_objects(self):
		before = {e.event_id: e for e in self.scheduler._events.values() if e.scope == "clock"}
		self.apply(lambda settings: setattr(settings.prayer.events[N.FAJR], "pre_alert_minutes", 7))
		self.assertTrue(all(self.scheduler._events[key] is event for key, event in before.items()))
		self.assertTrue(any(e.event_type is T.PRAYER_PRE_ALERT and e.scheduled_at == instant(4, 53) for e in self.scheduler._events.values()))

	def test_rebuild_dedup_after_presentation(self):
		self.clock.value = instant(5)
		event = self.scheduler.claim_for_presentation()
		self.assertEqual(event.event_type, T.PRAYER_TIME)
		self.scheduler.complete()
		self.scheduler.rebuild(self.source(self.clock.now(), "test", None), self.clock.now())
		self.assertNotIn(event.event_id, self.scheduler._events)

	def test_resume_single_lease_and_future_only(self):
		self.clock.value = instant(5, 1)
		event = self.coordinator.resume()
		self.assertEqual(event.event_type, T.PRAYER_TIME)
		self.assertTrue(all(utc(e.scheduled_at) > utc(self.clock.now()) for e in self.scheduler._events.values()))
		self.assertIsNone(self.coordinator.resume())

	def test_failure_preserves_existing_schedule(self):
		before = dict(self.scheduler._events)
		self.readings.side_effect = RuntimeError("reading failed")
		with self.assertRaisesRegex(RuntimeError, "reading failed"):
			self.coordinator.resume()
		self.assertEqual(self.scheduler._events, before)

	def test_silent_never_takes_lease_from_clock(self):
		self.apply(lambda settings: setattr(settings.prayer.events[N.FAJR].at_time_alert, "action", AlertAction.SILENT))
		self.clock.value = instant(5)
		self.assertEqual(self.scheduler.claim_for_presentation().event_type, T.CLOCK)

	def test_quiet_policy_remains_central(self):
		self.apply(lambda settings: setattr(settings.general.quiet_hours, "enabled", True))
		self.clock.value = instant(5)
		self.assertEqual(self.scheduler.claim_for_presentation().event_type, T.PRAYER_TIME)
		self.scheduler.complete()
		self.assertIsNone(self.scheduler.claim_for_presentation())


class MessageAndArchitectureTests(Fixture, unittest.TestCase):
	def test_arabic_templates_all_available(self):
		for name in set(N) - PRAYER_EVENT_NAMES: self.settings.prayer.events[name].post_alert_minutes = 10
		events = self.prayer_events()
		self.assertEqual(len({e.message_id for e in events}), 12)
		for event in events:
			self.assertTrue(format_prayer_alert(event).endswith("."))
			self.assertTrue(format_prayer_alert(event, "en").endswith("."))
		fajr = next(e for e in events if e.event_type is T.PRAYER_TIME)
		self.assertEqual(format_prayer_alert(fajr), "حان الآن وقت صلاة الفجر.")
		pre = self.of_type(T.PRAYER_PRE_ALERT)[0]
		self.assertEqual(format_prayer_alert(pre), "اقترب دخول وقت صلاة الفجر، وقد بقي عليه 10 دقائق.")

	def test_arabic_duration_singular_dual_plural_hours(self):
		for minutes, text in ((1, "دقيقة واحدة"), (2, "دقيقتان"), (5, "5 دقائق"), (61, "ساعة واحدة ودقيقة واحدة")):
			self.settings.prayer.events[N.FAJR].pre_alert_minutes = minutes
			self.assertIn(text, format_prayer_alert(self.of_type(T.PRAYER_PRE_ALERT)[0]))

	def test_producers_have_no_io_output_or_parallel_scheduler(self):
		for name in ("prayer_alert_producer.py", "clock_alert_producer.py", "prayer_clock_rebuild_source.py"):
			tree = ast.parse((ROOT / "addon/globalPlugins/awqati/application" / name).read_text(encoding="utf-8"))
			imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
			imports += [item.name for node in ast.walk(tree) if isinstance(node, ast.Import) for item in node.names]
			for module in imports:
				self.assertFalse(any(word in module for word in ("wx", "nvwave", "speech", "globalPluginHandler", "socket", "urllib", "pathlib", "threading")), module)
			calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
				for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}
			self.assertFalse(calls & {"open", "Timer", "speak", "message", "playWaveFile", "schedule", "snapshot", "PrayerStateService", "AlertScheduler"})
			keywords = {keyword.arg for node in ast.walk(tree) if isinstance(node, ast.Call) for keyword in node.keywords}
			self.assertFalse(keywords & {"priority", "grace_period"})


if __name__ == "__main__":
	unittest.main()
