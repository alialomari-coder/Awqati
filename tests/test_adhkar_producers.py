"""Task 4.3 temporal, resource and activation acceptance."""

import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addon/globalPlugins'))
from awqati.application import AdhkarAlertProducer, DailyWirdProducer, RecurringDhikrProducer
from awqati.application.alert_formatters import format_adhkar_alert
from awqati.domain import Instant, Location, StoredLocation, LocationKind, default_settings
from awqati.domain.alerts import AlertTiming, utc
from awqati.domain.settings import (MorningReference, EveningReference, FridayReference,
    RecurringDhikrId as D, DayPeriod, AlertAction, SoundReference, validate_settings)
from awqati.domain.prayer_timeline import PrayerEvent, PrayerEventName as N
from awqati.infrastructure import BundledTimezoneProvider


ORDER = ('subhanAllah', 'alhamduLillah', 'laIlahaIllaAllah', 'allahuAkbar',
    'laHawlaWaLaQuwwata', 'astaghfiruAllah', 'salatAlaAlNabi', 'udhkurAllah', 'laTansaDhikrAllah')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.settings = default_settings()
        self.settings.location = StoredLocation(LocationKind.CUSTOM, Location('test', 'Test', 24, 46, 'Etc/UTC'))
        self.zones = BundledTimezoneProvider()
        self.zone = self.zones.get_timezone('Etc/UTC')
        self.start = self.at(16)
        self.end = self.at(17)
        self.references = [PrayerEvent(n, self.at(16, h).value) for n, h in
            ((N.FAJR, 5), (N.SUNRISE, 6), (N.ASR, 15), (N.MAGHRIB, 18))]
        self.timed = AdhkarAlertProducer(lambda: self.settings, lambda *_: self.references, lambda _: self.zone)
        self.wird = DailyWirdProducer(lambda: self.settings, lambda _: self.zone)
        self.recurring = RecurringDhikrProducer(lambda: self.settings)

    @staticmethod
    def at(day=16, hour=0, minute=0):
        return Instant(datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc))

    def enable(self):
        for key in ('morning', 'evening', 'friday_hour', 'daily_wird', 'recurring'):
            getattr(self.settings.adhkar, key).enabled = True


class DefaultsTests(Fixture):
    def test_defaults_and_order(self):
        a = self.settings.adhkar
        self.assertEqual((a.morning.minutes, a.evening.minutes, a.friday_hour.minutes), (15, 15, 60))
        self.assertIs(a.morning.reference, MorningReference.BEFORE_SUNRISE)
        self.assertIs(a.evening.reference, EveningReference.BEFORE_MAGHRIB)
        self.assertIs(a.friday_hour.reference, FridayReference.BEFORE_MAGHRIB)
        self.assertEqual((a.daily_wird.hour, a.daily_wird.minute, a.daily_wird.period), (10, 0, DayPeriod.PM))
        self.assertEqual(a.daily_wird.text, 'Do not forget your daily Wird.')
        self.assertEqual(a.recurring.interval_minutes, 60)
        self.assertEqual(tuple(d.value for d in D), ORDER)
        for item in a.recurring.items.values():
            self.assertTrue(item.enabled)
            self.assertIs(item.alert.action, AlertAction.SPEECH)
        for key in ('morning', 'evening', 'friday_hour', 'daily_wird', 'recurring'):
            self.assertFalse(getattr(a, key).enabled)
        self.assertEqual(self.timed.produce(self.start, self.end), ())
        self.assertEqual(self.wird.produce(self.start, self.end), ())
        self.assertEqual(self.recurring.produce(self.start, self.end), ())

    def test_all_action_constraints(self):
        for attr in ('morning', 'evening', 'friday_hour', 'daily_wird'):
            for action in AlertAction:
                with self.subTest(attr=attr, action=action):
                    s = default_settings()
                    getattr(s.adhkar, attr).alert.action = action
                    if action is AlertAction.SILENT:
                        with self.assertRaises(ValueError): validate_settings(s)
                    else: validate_settings(s)
        for identity in D:
            for action in AlertAction:
                with self.subTest(identity=identity, action=action):
                    s = default_settings()
                    s.adhkar.recurring.items[identity].alert.action = action
                    if action in (AlertAction.SILENT, AlertAction.SOUND_AND_SPEECH):
                        with self.assertRaises(ValueError): validate_settings(s)
                    else: validate_settings(s)


class TimedTests(Fixture):
    def test_messages_and_identity_ignore_output(self):
        self.enable()
        first = self.timed.produce(self.start, self.end)
        self.assertEqual([format_adhkar_alert(e) for e in first],
            ['حان وقت أذكار الصباح.', 'لا تنسَ ساعة الجمعة.', 'حان وقت أذكار المساء.'])
        for config in (self.settings.adhkar.morning, self.settings.adhkar.evening, self.settings.adhkar.friday_hour):
            config.alert.action = AlertAction.SOUND
            config.alert.sound = SoundReference('sounds/adhkar/test.wav')
        second = self.timed.produce(self.start, self.end)
        self.assertEqual([e.event_id for e in first], [e.event_id for e in second])
        self.assertTrue(all(e.sound_ref == 'sounds/adhkar/test.wav' for e in second))
        self.assertTrue(all(format_adhkar_alert(e, 'en') for e in second))
        self.assertIsNot(first[0], second[0])

    def test_scope_filter(self):
        self.enable()
        for name in ('morning', 'evening', 'friday'):
            events = self.timed.produce(self.start, self.end, 'adhkar.' + name)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].scope, 'adhkar.' + name)
        self.assertEqual(len(self.timed.produce(self.start, self.end, 'adhkar')), 3)
        self.assertEqual(self.timed.produce(self.start, self.end, 'clock'), ())

    def test_friday_local_reference_day_not_utc(self):
        self.settings.adhkar.friday_hour.enabled = True
        self.settings.adhkar.friday_hour.reference = FridayReference.AFTER_ASR
        self.settings.adhkar.friday_hour.minutes = 0
        for zone_id, ref, expected in (
            ('Pacific/Kiritimati', self.at(15, 12), 1),
            ('America/Los_Angeles', self.at(17, 2), 1),
            ('Pacific/Kiritimati', self.at(16, 12), 0),
            ('America/Los_Angeles', self.at(16, 2), 0)):
            with self.subTest(zone=zone_id, ref=ref):
                self.zone = self.zones.get_timezone(zone_id)
                self.references = [PrayerEvent(N.ASR, ref.value)]
                self.assertEqual(len(self.timed.produce(self.at(15), self.at(18))), expected)

    def test_friday_absent_other_six_days(self):
        self.settings.adhkar.friday_hour.enabled = True
        for day in range(12, 19):
            self.references = [PrayerEvent(N.MAGHRIB, self.at(day, 18).value)]
            self.assertEqual(len(self.timed.produce(self.at(day), self.at(day + 1))), int(day == 16))

    def test_reference_on_next_day_moves_into_window(self):
        self.settings.adhkar.morning.enabled = True
        self.settings.adhkar.morning.minutes = 180
        self.references = [PrayerEvent(N.SUNRISE, self.at(17, 1).value)]
        event, = self.timed.produce(self.start, self.end)
        self.assertEqual(event.scheduled_at, self.at(16, 22))
        self.assertEqual(event.reference_at, self.at(17, 1))

    def test_reference_on_previous_day_moves_into_window(self):
        c = self.settings.adhkar.evening
        c.enabled, c.reference, c.minutes = True, EveningReference.AFTER_MAGHRIB, 180
        self.references = [PrayerEvent(N.MAGHRIB, self.at(15, 23).value)]
        event, = self.timed.produce(self.start, self.end)
        self.assertEqual(event.scheduled_at, self.at(16, 2))

    def test_elapsed_offsets_across_dst(self):
        c = self.settings.adhkar.morning
        c.enabled, c.minutes = True, 180
        self.zone = self.zones.get_timezone('America/New_York')
        for month, day in ((3, 8), (11, 1)):
            ref = Instant(datetime(2026, month, day, 4, tzinfo=self.zone))
            self.references = [PrayerEvent(N.SUNRISE, ref.value)]
            event, = self.timed.produce(Instant(utc(ref) - timedelta(hours=5)), Instant(utc(ref) + timedelta(hours=1)))
            self.assertEqual(utc(ref) - utc(event.scheduled_at), timedelta(hours=3))


def reference_case(attr, ref, prayer, before, minutes):
    def test(self):
        c = getattr(self.settings.adhkar, attr)
        c.enabled, c.reference, c.minutes = True, ref, minutes
        event, = self.timed.produce(self.start, self.end)
        reference = next(e for e in self.references if e.name is prayer)
        expected = reference.occurs_at + timedelta(minutes=-minutes if before else minutes)
        self.assertEqual(utc(event.scheduled_at), expected)
        if before and minutes:
            self.assertIs(event.timing, AlertTiming.BEFORE)
            self.assertEqual(event.expires_at, event.reference_at)
            self.assertTrue(event.is_valid_at(Instant(utc(event.reference_at) - timedelta(microseconds=1))))
            self.assertFalse(event.is_valid_at(event.reference_at))
        else:
            self.assertIs(event.timing, AlertTiming.AT_OR_AFTER)
            self.assertEqual(event.grace_period, timedelta(minutes=15))
            self.assertTrue(event.is_valid_at(Instant(utc(event.scheduled_at) + timedelta(minutes=15))))
            self.assertFalse(event.is_valid_at(Instant(utc(event.scheduled_at) + timedelta(minutes=15, microseconds=1))))
    return test


for attr, refs in (
    ('morning', ((MorningReference.AFTER_FAJR, N.FAJR, False), (MorningReference.BEFORE_SUNRISE, N.SUNRISE, True), (MorningReference.AFTER_SUNRISE, N.SUNRISE, False))),
    ('evening', ((EveningReference.AFTER_ASR, N.ASR, False), (EveningReference.BEFORE_MAGHRIB, N.MAGHRIB, True), (EveningReference.AFTER_MAGHRIB, N.MAGHRIB, False))),
    ('friday_hour', ((FridayReference.AFTER_ASR, N.ASR, False), (FridayReference.BEFORE_MAGHRIB, N.MAGHRIB, True)))):
    for ref, prayer, before in refs:
        for minutes in (0, 15, 180):
            setattr(TimedTests, f'test_{attr}_{ref.value}_{minutes}', reference_case(attr, ref, prayer, before, minutes))


class WirdTests(Fixture):
    def test_default_text_and_grace(self):
        self.settings.adhkar.daily_wird.enabled = True
        event, = self.wird.produce(self.start, self.end)
        self.assertEqual(event.scheduled_at, self.at(16, 22))
        self.assertEqual(event.grace_period, timedelta(minutes=15))
        self.assertEqual(format_adhkar_alert(event), 'لا تنس وردك اليومي.')

    def test_civil_am_pm_boundaries(self):
        c = self.settings.adhkar.daily_wird
        c.enabled = True
        for hour in (1, 10, 12):
            for minute in (0, 59):
                for period in DayPeriod:
                    with self.subTest(hour=hour, minute=minute, period=period):
                        c.hour, c.minute, c.period = hour, minute, period
                        event, = self.wird.produce(self.start, self.end)
                        self.assertEqual(event.scheduled_at, self.at(16, hour % 12 + (12 if period is DayPeriod.PM else 0), minute))

    def test_gap_and_fold(self):
        self.zone = self.zones.get_timezone('America/New_York')
        c = self.settings.adhkar.daily_wird
        c.enabled, c.period, c.minute = True, DayPeriod.AM, 30
        for month, day, hour, expected in ((3, 8, 2, 7), (11, 1, 1, 5)):
            with self.subTest(month=month):
                c.hour = hour
                start = Instant(datetime(2026, month, day, tzinfo=self.zone))
                end = Instant(datetime(2026, month, day + 1, tzinfo=self.zone))
                event, = self.wird.produce(start, end)
                self.assertEqual(utc(event.scheduled_at).hour, expected)
                self.assertEqual(utc(event.scheduled_at).minute, 0 if month == 3 else 30)
                self.assertEqual(event.scheduled_at.value.fold, 0)
                self.assertEqual(self.wird.produce(Instant(utc(event.scheduled_at) + timedelta(hours=1)), end), ())

    def test_no_catchup_on_enable_after_time(self):
        self.settings.adhkar.daily_wird.enabled = True
        self.assertEqual(self.wird.produce(self.at(16, 22, 1), self.end), ())

    def test_user_text_is_literal_and_identity_is_output_independent(self):
        c = self.settings.adhkar.daily_wird
        c.enabled = True
        original, = self.wird.produce(self.start, self.end)
        for text in ('', '<b>{name}</b> %s\nنصي', 'My reminder'):
            c.text = text
            event, = self.wird.produce(self.start, self.end)
            self.assertEqual(event.event_id, original.event_id)
            for language in ('ar', 'en'):
                self.assertEqual(format_adhkar_alert(event, language), text)
        self.assertEqual(original.metadata['text'], 'Do not forget your daily Wird.')


class RecurringTests(Fixture):
    def setUp(self):
        super().setUp()
        self.settings.adhkar.recurring.enabled = True

    def test_interval_limits_start_after_full_interval(self):
        for minutes in (5, 60, 1440):
            with self.subTest(minutes=minutes):
                self.settings.adhkar.recurring.interval_minutes = minutes
                self.recurring.reset()
                events = self.recurring.produce(self.start, self.at(19))
                self.assertEqual(utc(events[0].scheduled_at) - utc(self.start), timedelta(minutes=minutes))
                self.assertEqual(events[0].metadata['dhikr_id'], ORDER[0])

    def test_enabled_order_only(self):
        c = self.settings.adhkar.recurring
        c.items[D.SUBHAN_ALLAH].enabled = False
        c.items[D.ALLAHU_AKBAR].enabled = False
        events = self.recurring.produce(self.start, self.end)
        expected = tuple(x for x in ORDER if x not in ('subhanAllah', 'allahuAkbar'))
        self.assertEqual(tuple(e.metadata['dhikr_id'] for e in events[:len(expected)]), expected)
        self.assertTrue(all(utc(b.scheduled_at) - utc(a.scheduled_at) == timedelta(hours=1) for a,b in zip(events, events[1:])))

    def test_empty_cycle_no_events(self):
        for item in self.settings.adhkar.recurring.items.values(): item.enabled = False
        self.assertEqual(self.recurring.produce(self.start, self.end), ())

    def test_rebuild_identity_and_fresh_objects(self):
        a = self.recurring.produce(self.start, self.end)
        b = self.recurring.produce(self.start, self.end)
        self.assertEqual(a, b)
        self.assertIsNot(a[0], b[0])
        self.assertNotEqual(a[0].dedup_key, a[9].dedup_key)

    def test_technical_rebuild_preserves_anchor(self):
        original = self.recurring.produce(self.start, self.end)
        new = self.recurring.produce(self.at(16, 0, 30), self.end)
        self.assertEqual(new, original)

    def test_midnight_renewal_preserves_order(self):
        self.recurring.produce(self.start, self.end)
        events = self.recurring.produce(self.end, self.at(18), reason='localDayChanged')
        self.assertEqual(events[0].scheduled_at, self.end)
        self.assertEqual(events[0].metadata['dhikr_id'], ORDER[23 % 9])

    def test_midnight_does_not_invent_immediate_occurrence(self):
        self.recurring.produce(self.at(16, 23, 30), self.end)
        events = self.recurring.produce(self.end, self.at(18), reason='localDayChanged')
        self.assertEqual(events[0].scheduled_at, self.at(17, 0, 30))
        self.assertEqual(events[0].metadata['dhikr_id'], ORDER[0])

    def test_resume_skips_expired_slots(self):
        self.recurring.produce(self.start, self.end)
        events = self.recurring.produce(self.at(16, 4, 30), self.end, reason='resume')
        self.assertEqual(events[0].scheduled_at, self.at(16, 5))
        self.assertEqual(events[0].metadata['dhikr_id'], ORDER[4])

    def test_resume_exact_slot_is_strictly_future(self):
        self.recurring.produce(self.start, self.end)
        events = self.recurring.produce(self.at(16, 4), self.end, reason='resume')
        self.assertEqual(events[0].scheduled_at, self.at(16, 5))

    def test_zero_grace(self):
        event = self.recurring.produce(self.start, self.end)[0]
        self.assertEqual(event.grace_period, timedelta(0))
        self.assertTrue(event.is_valid_at(event.scheduled_at))
        self.assertFalse(event.is_valid_at(Instant(utc(event.scheduled_at) + timedelta(microseconds=1))))

    def test_new_session_starts_first(self):
        self.recurring.produce(self.start, self.end)
        new = RecurringDhikrProducer(lambda: self.settings)
        event = new.produce(self.at(16, 12), self.end)[0]
        self.assertEqual(event.scheduled_at, self.at(16, 13))
        self.assertEqual(event.metadata['dhikr_id'], ORDER[0])

    def test_interval_change_full_wait(self):
        self.recurring.produce(self.start, self.end)
        old = deepcopy(self.settings)
        self.settings.adhkar.recurring.interval_minutes = 5
        self.recurring.settings_changed(old, self.settings, self.at(16, 4, 30))
        event = self.recurring.produce(self.at(16, 4, 30), self.end)[0]
        self.assertEqual(event.scheduled_at, self.at(16, 4, 35))

    def test_system_time_change_no_retroactive_event(self):
        self.recurring.produce(self.start, self.end)
        event = self.recurring.produce(self.at(16, 3), self.end, reason='systemTimeChanged')[0]
        self.assertEqual(event.scheduled_at, self.at(16, 4))

    def test_all_messages_and_item_scope(self):
        events = self.recurring.produce(self.start, self.end)
        self.assertEqual(format_adhkar_alert(events[0]), 'سبحان الله.')
        for event in events:
            self.assertTrue(format_adhkar_alert(event, 'en'))
            self.assertTrue(format_adhkar_alert(event, 'ar'))
        selected = self.recurring.produce(self.start, self.end, scope='adhkar.recurring.subhanAllah')
        self.assertEqual(selected, tuple(e for e in events if e.metadata['dhikr_id'] == 'subhanAllah'))


class HierarchyTests(Fixture):
    def test_parent_switches_suppress_all_and_keep_settings(self):
        self.enable()
        for parent, attr in ((self.settings.general, 'all_automatic_alerts_enabled'), (self.settings.adhkar, 'alerts_enabled')):
            setattr(parent, attr, False)
            before = deepcopy(self.settings)
            for producer in (self.timed, self.wird, self.recurring):
                self.assertEqual(producer.produce(self.start, self.end), ())
            self.assertEqual(before, self.settings)
            setattr(parent, attr, True)

    def test_each_feature_disabled_independently(self):
        self.enable()
        for name, scope in (('morning', 'morning'), ('evening', 'evening'), ('friday_hour', 'friday')):
            getattr(self.settings.adhkar, name).enabled = False
            self.assertFalse(any(e.scope == 'adhkar.' + scope for e in self.timed.produce(self.start, self.end)))
            getattr(self.settings.adhkar, name).enabled = True

    def test_architecture_producers_have_no_platform_io_or_timers(self):
        base = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/awqati/application'
        forbidden = {'wx', 'speech', 'nvwave', 'ui', 'ctypes', 'socket', 'urllib', 'threading', 'requests', 'os', 'pathlib'}
        for name in ('adhkar_alert_producer.py', 'daily_wird_producer.py', 'recurring_dhikr_producer.py'):
            tree = ast.parse((base / name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden.isdisjoint(a.name.split('.')[0] for a in node.names))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {'open', 'PrayerCalculator', 'AlertScheduler', 'Timer'})


if __name__ == '__main__': unittest.main()
