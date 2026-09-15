"""4.3 producers through real coordinator, policies and service preparation."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from test_adhkar_producers import Fixture, ORDER
from test_alert_daily_renewal import BridgePrayers
from test_alert_producers import Clock, Repository
from awqati.application import AlertScheduler, AlertCoordinator, SettingsService, PrayerClockRebuildSource, PrayerService
from awqati.domain import (AlertEventType as T, SettingsApplied, SystemTimeChanged, AlertAction,
    ClockTime, MorningReference, EveningReference, RecurringDhikrId as D, PrayerEventName as N)
from awqati.domain.alerts import utc
from awqati.infrastructure import BundledCalculationMethodRepository


class CoordinatorFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.enable()
        self.settings.prayer.alerts_enabled = False
        from awqati.domain import CalculationMethod
        self.settings.prayer.calculation_method = CalculationMethod.MWL
        self.clock = Clock(self.start)
        self.service = SettingsService(Repository(self.settings), self.clock)
        self.prayers = BridgePrayers(self.zones)
        self.source = PrayerClockRebuildSource.from_services(lambda: self.service.runtime_settings, self.prayers, self.zones)
        self.scheduler = AlertScheduler(self.clock, lambda: self.service.runtime_settings)
        self.coordinator = AlertCoordinator(self.scheduler, self.service.events, self.source)

    def seed(self):
        events = self.source(self.clock.now(), 'startup', None)
        self.scheduler.rebuild(events, self.clock.now())
        return events

    def apply(self, edit):
        draft = self.service.open_draft()
        edit(draft.settings)
        self.service.apply(draft)

    def next_recurring(self):
        events = self.source(self.clock.now(), 'test', 'adhkar.recurring')
        return events[0] if events else None


class IntegrationTests(CoordinatorFixture):
    def test_source_all_types_and_child_scopes(self):
        all_events = self.seed()
        self.assertEqual({e.event_type for e in all_events}, {T.MORNING_ADHKAR, T.EVENING_ADHKAR, T.FRIDAY_HOUR, T.DAILY_WIRD, T.RECURRING_DHIKR})
        for scope in ('adhkar', 'adhkar.morning', 'adhkar.evening', 'adhkar.friday', 'adhkar.dailyWird', 'adhkar.recurring', 'adhkar.recurring.subhanAllah'):
            events = self.source(self.start, 'test', scope)
            self.assertEqual(events, tuple(e for e in all_events if e.scope == scope or e.scope.startswith(scope + '.')))

    def test_identical_apply_does_not_call_source(self):
        self.seed()
        spy = Mock(wraps=self.source)
        self.coordinator._rebuild = spy
        self.apply(lambda s: None)
        spy.assert_not_called()

    def test_each_parent_reactivation_restarts_first_after_full_wait(self):
        for parent_path, field in (('general', 'all_automatic_alerts_enabled'), ('adhkar', 'alerts_enabled'), ('recurring', 'enabled')):
            with self.subTest(parent=parent_path):
                self.seed()
                self.clock.value = self.at(16, 4, 30)
                def parent(s): return s.adhkar.recurring if parent_path == 'recurring' else getattr(s, parent_path)
                self.apply(lambda s: setattr(parent(s), field, False))
                saved = deepcopy(self.service.runtime_settings.adhkar.recurring.items)
                self.apply(lambda s: setattr(parent(s), field, True))
                event = self.next_recurring()
                self.assertEqual(event.scheduled_at, self.at(16, 5, 30))
                self.assertEqual(event.metadata['dhikr_id'], ORDER[0])
                self.assertEqual(self.service.runtime_settings.adhkar.recurring.items, saved)

    def test_interval_change_at_apply(self):
        self.seed()
        self.clock.value = self.at(16, 4, 30)
        self.apply(lambda s: setattr(s.adhkar.recurring, 'interval_minutes', 5))
        self.assertEqual(self.next_recurring().scheduled_at, self.at(16, 4, 35))

    def test_item_action_only_rebuilds_item_and_keeps_other_events(self):
        self.seed()
        before = dict(self.scheduler._events)
        self.apply(lambda s: setattr(s.adhkar.recurring.items[D.SUBHAN_ALLAH].alert, 'action', AlertAction.SOUND))
        after = self.scheduler._events
        for key, event in before.items():
            if event.scope == 'adhkar.recurring.subhanAllah':
                self.assertIs(after[key].action, AlertAction.SOUND)
            else:
                self.assertIs(after[key], event)

    def test_wird_change_does_not_rebuild_other_scopes_or_calculate_prayers(self):
        self.seed()
        before = dict(self.scheduler._events)
        self.prayers.calls.clear()
        self.apply(lambda s: setattr(s.adhkar.daily_wird, 'text', 'custom'))
        self.assertEqual(self.prayers.calls, [])
        for key, event in before.items():
            if event.event_type is not T.DAILY_WIRD:
                self.assertIs(self.scheduler._events[key], event)

    def test_calculation_change_leaves_wird_and_recurring_objects(self):
        self.seed()
        before = dict(self.scheduler._events)
        self.apply(lambda s: s.prayer.corrections_minutes.__setitem__(N.SUNRISE, 5))
        for key, event in before.items():
            if event.event_type in (T.DAILY_WIRD, T.RECURRING_DHIKR):
                self.assertIs(self.scheduler._events[key], event)

    def test_quiet_change_does_not_restart_cycle(self):
        self.seed()
        self.clock.value = self.at(16, 0, 30)
        self.apply(lambda s: setattr(s.general.quiet_hours, 'enabled', True))
        self.assertEqual(self.next_recurring().scheduled_at, self.at(16, 1))

    def test_resume_does_not_catch_up_recurring(self):
        self.seed()
        self.clock.value = self.at(16, 4, 30)
        self.assertIsNone(self.coordinator.resume())
        self.assertEqual(self.scheduler.wakeup_at, self.at(16, 5))

    def test_day_renewal_twice_does_not_duplicate(self):
        self.seed()
        self.clock.value = self.end
        self.coordinator.renew_day(self.end)
        before = tuple(self.scheduler._events)
        self.coordinator.renew_day(self.end)
        self.assertEqual(tuple(self.scheduler._events), before)
        event = self.scheduler.claim_for_presentation(self.end)
        self.assertIs(event.event_type, T.RECURRING_DHIKR)
        self.scheduler.complete(now=self.end)
        self.coordinator.renew_day(self.end)
        self.assertIsNone(self.scheduler.claim_for_presentation(self.end))

    def test_max_interval_survives_empty_first_day(self):
        self.apply(lambda s: setattr(s.adhkar.recurring, 'interval_minutes', 1440))
        self.clock.value = self.at(16, 12)
        # New session at noon; first day contains no recurring occurrence.
        self.source._recurring.reset()
        self.assertFalse(any(e.event_type is T.RECURRING_DHIKR for e in self.seed()))
        self.clock.value = self.end
        self.coordinator.renew_day(self.end)
        self.assertEqual(self.next_recurring().scheduled_at, self.at(17, 12))

    def test_system_time_forward_and_backward_do_not_create_immediate_event(self):
        self.seed()
        for at in (self.at(16, 4, 30), self.at(16, 2, 30)):
            self.clock.value = at
            self.service.events.publish(SystemTimeChanged(at))
            self.assertEqual(utc(self.next_recurring().scheduled_at), utc(at).replace(minute=0) + timedelta(hours=1))

    def test_location_change_preserves_cycle_anchor(self):
        self.seed()
        self.clock.value = self.at(16, 0, 30)
        def edit(s):
            from awqati.domain import Location
            s.location.location = Location('other', 'Other', 25, 45, 'Asia/Riyadh')
        self.apply(edit)
        self.assertEqual(self.next_recurring().scheduled_at, self.at(16, 1))

    def test_preparation_failure_keeps_old_queue_and_cycle(self):
        self.seed()
        before = dict(self.scheduler._events)
        anchor = self.source._recurring._first
        self.prayers.calculate = Mock(side_effect=RuntimeError('preparation failed'))
        with self.assertRaisesRegex(RuntimeError, 'preparation failed'):
            self.coordinator.renew_day(self.end)
        self.assertEqual(self.scheduler._events, before)
        self.assertEqual(self.source._recurring._first, anchor)

    def test_real_prayer_service_supplies_reference(self):
        prayers = PrayerService(BundledCalculationMethodRepository(), self.zones)
        source = PrayerClockRebuildSource.from_services(lambda: self.service.runtime_settings, prayers, self.zones)
        event, = source(self.start, 'test', 'adhkar.morning')
        self.assertEqual(utc(event.reference_at) - utc(event.scheduled_at), timedelta(minutes=15))
        # Independent current service request uses the same saved configuration.
        from awqati.domain import PrayerCalculationRequest
        s = self.service.runtime_settings
        request = PrayerCalculationRequest(self.start.value.date(), 24, 46, 'Etc/UTC',
            s.prayer.calculation_method, s.prayer.asr_method, s.prayer.high_latitude_rule)
        self.assertEqual(utc(event.reference_at), prayers.calculate(request).sunrise.astimezone(timezone.utc))

    def test_timed_preparation_with_prayer_alerts_disabled(self):
        self.assertFalse(self.service.runtime_settings.prayer.alerts_enabled)
        events = self.seed()
        self.assertTrue(any(e.event_type is T.MORNING_ADHKAR for e in events))
        self.assertTrue(self.prayers.calls)

    def test_offset_lookaround_with_next_day_reference(self):
        original = self.prayers.calculate
        def calculate(request):
            values = original(request)
            values.sunrise = values.sunrise.replace(hour=1)
            return values
        self.prayers.calculate = calculate
        self.apply(lambda s: setattr(s.adhkar.morning, 'minutes', 180))
        events = self.source(self.at(16, 21), 'test', 'adhkar.morning')
        event, = events
        self.assertEqual(event.scheduled_at, self.at(16, 22))
        self.assertEqual(event.reference_at, self.at(17, 1))

    def test_offset_lookaround_with_previous_day_reference(self):
        original = self.prayers.calculate
        def calculate(request):
            values = original(request)
            values.maghrib = values.maghrib.replace(hour=23)
            return values
        self.prayers.calculate = calculate
        def edit(s):
            s.adhkar.evening.reference = EveningReference.AFTER_MAGHRIB
            s.adhkar.evening.minutes = 180
        self.apply(edit)
        event, = self.source(self.start, 'test', 'adhkar.evening')
        self.assertEqual(event.scheduled_at, self.at(16, 2))

    def test_23_and_25_hour_day_horizon_and_elapsed_recurrence(self):
        from awqati.domain import Location, Instant
        for month, day, hours in ((3, 8, 23), (11, 1, 25)):
            def edit(s): s.location.location = Location('ny', 'New York', 40.7, -74, 'America/New_York')
            self.apply(edit)
            zone = self.zones.get_timezone('America/New_York')
            start = Instant(datetime(2026, month, day, tzinfo=zone))
            self.clock.value = start
            self.source._recurring.reset()
            events = self.source(start, 'startup', 'adhkar.recurring')
            self.assertEqual(len(events), hours - 1)
            self.assertEqual(utc(self.source.next_rebuild_at(start)) - utc(start), timedelta(hours=hours))
            self.assertTrue(all(utc(b.scheduled_at)-utc(a.scheduled_at) == timedelta(hours=1) for a,b in zip(events,events[1:])))

    def test_quiet_hours_suppress_timed_wird_recurring_without_catchup(self):
        def quiet(s):
            s.general.quiet_hours.enabled = True
            s.general.quiet_hours.start = ClockTime(17, 0)
            s.general.quiet_hours.end = ClockTime(7, 0)
        self.apply(quiet)
        events = self.seed()
        for event in events:
            if event.event_type in (T.MORNING_ADHKAR, T.EVENING_ADHKAR, T.FRIDAY_HOUR, T.DAILY_WIRD):
                self.clock.value = event.scheduled_at
                self.assertNotIn(event, self.scheduler.due())
        self.clock.value = self.at(17, 7)
        self.assertFalse(any(e in events for e in self.scheduler.due()))

    def test_daytime_quiet_start_inclusive_end_exclusive(self):
        def edit(s):
            q=s.general.quiet_hours
            q.enabled, q.start, q.end = True, ClockTime(1, 0), ClockTime(2, 0)
        self.apply(edit)
        self.seed()
        self.clock.value = self.at(16, 1)
        self.assertEqual(self.scheduler.due(), ())
        self.clock.value = self.at(16, 2)
        self.assertEqual(self.scheduler.claim_for_presentation().metadata['dhikr_id'], ORDER[1])


if __name__ == '__main__': unittest.main()
