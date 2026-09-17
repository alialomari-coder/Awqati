"""Synthetic acceptance coverage for 4.1; no producers or presenter."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import ast
import sys
import unittest
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addon/globalPlugins'))
from awqati.domain import (AlertEvent, AlertEventType as T, AlertPriority as P, AlertTiming,
    Instant, default_settings, SettingsApplied, LocationChanged, SystemTimeChanged,
    CalculationMethod, ClockTime)
from awqati.domain.alerts import GRACE_PERIODS
from awqati.infrastructure import BundledTimezoneProvider
from awqati.application import (AlertScheduler, AlertCoordinator, EventDispatcher,
    SettingsService, priority_for, resolve_civil_time, manual_commands_allowed,
    timer_delivery_instant)


class Repository:
    def __init__(self, settings): self.value = deepcopy(settings)
    def load(self): return deepcopy(self.value)
    def save(self, settings): self.value = deepcopy(settings)


class Clock:
    def __init__(self, instant): self.value = instant
    def now(self): return self.value


class AlertFixture:

    def setUp(self):
        self.now = Instant(datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
        self.clock = Clock(self.now)
        self.scheduler = AlertScheduler(self.clock)

    def at(self, seconds): return Instant(self.now.value + timedelta(seconds=seconds))
    def ev(self, eid, kind=T.PRAYER_TIME, at=None, **kw):
        return AlertEvent(eid, kind, at or self.now, **kw)
    def ids(self, events): return [e.event_id for e in events]


class AlertSchedulerTests(AlertFixture, unittest.TestCase):
    def test_timer_jitter_delivers_exact_recurring_event_without_catch_up(self):
        event = self.ev('recurring', T.RECURRING_DHIKR, self.at(60), scope='adhkar.recurring')
        self.scheduler.schedule(event)
        actual = self.at(60.250)
        delivery = timer_delivery_instant(actual, event.scheduled_at)
        self.assertEqual(delivery, event.scheduled_at)
        self.assertIs(self.scheduler.claim_for_presentation(delivery), event)

    def test_timer_jitter_does_not_revive_stale_recurring_event(self):
        event = self.ev('recurring', T.RECURRING_DHIKR, self.at(60), scope='adhkar.recurring')
        self.scheduler.schedule(event)
        actual = self.at(65.000001)
        self.assertEqual(timer_delivery_instant(actual, event.scheduled_at), actual)
        self.assertIsNone(self.scheduler.claim_for_presentation(actual))

    def test_aware_and_naive_times(self):
        self.assertEqual(self.ev('x').scheduled_at, self.now)
        for field in ('scheduled_at', 'expires_at', 'reference_at'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'aware'):
                args = dict(event_id='x', event_type=T.CLOCK, scheduled_at=self.now)
                args[field] = datetime(2026, 1, 1)
                AlertEvent(**args)

    def test_priority_cannot_be_forged(self):
        with self.assertRaisesRegex(ValueError, 'priority'):
            self.ev('x', T.CLOCK, priority=P.PRAYER_TIME)
        self.assertEqual(self.ev('x', T.CLOCK).priority, P.CLOCK)

    def test_ids_keys_scopes_validated(self):
        for kwargs in ({'event_id': ''}, {'dedup_key': ''}, {'dedup_key': ' '}, {'scope': ''}, {'scope': 'adhkar..morning'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AlertEvent(**(dict(event_id='x', event_type=T.CLOCK, scheduled_at=self.now) | kwargs))
        event = self.ev('x', dedup_key='clock:day:hour', scope='clock.hour')
        self.assertEqual((event.dedup_key, event.scope), ('clock:day:hour', 'clock.hour'))

    def test_all_six_priorities(self):
        kinds = [T.PRAYER_TIME, T.SUNRISE, T.PRAYER_POST_ALERT, T.CLOCK, T.DAILY_WIRD, T.RECURRING_DHIKR]
        self.scheduler.schedule_many(self.ev(str(i), kind) for i, kind in reversed(list(enumerate(kinds))))
        self.assertEqual([e.priority for e in self.scheduler.due()], list(P))

    def test_tie_scheduled_type_then_id(self):
        events = [self.ev('z', T.EVENING_ADHKAR), self.ev('b', T.MORNING_ADHKAR),
            self.ev('a', T.MORNING_ADHKAR), self.ev('older', T.DAILY_WIRD, self.at(-1))]
        self.scheduler.schedule_many(events)
        self.assertEqual(self.ids(self.scheduler.due()), ['older', 'a', 'b', 'z'])

    def test_every_grace_boundary(self):
        expected = {T.CLOCK: 2, T.MORNING_ADHKAR: 15, T.EVENING_ADHKAR: 15,
            T.FRIDAY_HOUR: 15, T.DAILY_WIRD: 15, T.RECURRING_DHIKR: 0}
        for kind in T:
            if kind in (T.PRAYER_PRE_ALERT, T.IQAMA_PRE_ALERT): continue
            with self.subTest(kind=kind):
                e = self.ev('x', kind)
                seconds = expected.get(kind, 10) * 60
                self.assertEqual(e.grace_period, timedelta(seconds=seconds))
                self.assertEqual(e.grace_period, GRACE_PERIODS[kind])
                if seconds: self.assertTrue(e.is_valid_at(self.at(seconds - .000001)))
                self.assertTrue(e.is_valid_at(self.at(seconds)))
                self.assertFalse(e.is_valid_at(self.at(seconds + .000001)))
        with self.assertRaises(TypeError): GRACE_PERIODS[T.CLOCK] = timedelta(0)

    def test_explicit_expiry_is_exclusive(self):
        e = self.ev('x', expires_at=self.at(30))
        self.assertTrue(e.is_valid_at(self.at(29.999999)))
        self.assertFalse(e.is_valid_at(self.at(30)))
        self.assertFalse(e.is_valid_at(self.at(31)))

    def test_before_all_five_types_use_reference(self):
        for kind in (T.PRAYER_PRE_ALERT, T.IQAMA_PRE_ALERT, T.MORNING_ADHKAR, T.EVENING_ADHKAR, T.FRIDAY_HOUR):
            with self.subTest(kind=kind):
                e = self.ev('x', kind, reference_at=self.at(3600), timing=AlertTiming.BEFORE,
                    expires_at=self.at(4000))
                self.assertTrue(e.is_valid_at(self.at(3599.999999)))
                self.assertFalse(e.is_valid_at(self.at(3600)))
                self.assertFalse(e.is_valid_at(self.at(3601)))
                self.assertEqual(e.expires_at, self.at(3600))

    def test_reference_required_and_zero_offset_contract(self):
        for kind in (T.PRAYER_PRE_ALERT, T.IQAMA_PRE_ALERT, T.MORNING_ADHKAR):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'reference'):
                self.ev('x', kind, timing=AlertTiming.BEFORE)
        with self.assertRaises(ValueError):
            self.ev('x', T.MORNING_ADHKAR, timing=AlertTiming.BEFORE, reference_at=self.now)
        self.assertTrue(self.ev('x', T.MORNING_ADHKAR, reference_at=self.now).is_valid_at(self.now))
        self.assertIs(T.IQAMA, T.IQAMA_PRE_ALERT)

    def test_dedup_before_any_claim(self):
        self.assertTrue(self.scheduler.schedule(self.ev('a', at=self.at(60), dedup_key='shared')))
        self.assertFalse(self.scheduler.schedule(self.ev('b', at=self.at(120), dedup_key='shared')))
        self.assertEqual(self.scheduler.wakeup_at, self.at(60))

    def test_duplicate_event_id_does_not_overwrite(self):
        self.scheduler.schedule(self.ev('a', dedup_key='one'))
        self.assertFalse(self.scheduler.schedule(self.ev('a', dedup_key='two')))
        self.assertEqual(self.scheduler.next_due().dedup_key, 'one')

    def test_dedup_current_and_claim_handoff_once(self):
        self.scheduler.schedule(self.ev('a', dedup_key='key'))
        self.assertEqual(self.scheduler.claim_for_presentation().event_id, 'a')
        self.assertFalse(self.scheduler.schedule(self.ev('b', dedup_key='key')))
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.scheduler.current.event_id, 'a')

    def test_dedup_waiting(self):
        self.scheduler.schedule_many([self.ev('a'), self.ev('b', T.CLOCK, dedup_key='key')])
        self.scheduler.claim_for_presentation()
        self.assertEqual(self.ids(self.scheduler.waiting), ['b'])
        self.assertFalse(self.scheduler.schedule(self.ev('c', dedup_key='key')))

    def test_dedup_success_survives_rebuild(self):
        self.scheduler.schedule(self.ev('a', dedup_key='key'))
        self.scheduler.claim_for_presentation()
        self.scheduler.complete()
        self.assertEqual(self.scheduler.rebuild([self.ev('b', dedup_key='key')], self.now), 0)

    def test_dedup_rechecked_before_delivery(self):
        self.scheduler.schedule(self.ev('a', dedup_key='key'))
        # Simulate a restored execution record after event admission.
        self.scheduler._dedup['key'] = self.now
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.scheduler.waiting, ())

    def test_retention_cleanup_allows_new_occurrence(self):
        self.scheduler.schedule(self.ev('a', dedup_key='key'))
        self.scheduler.claim_for_presentation()
        self.scheduler.complete()
        self.clock.value = self.at(172799)
        self.assertFalse(self.scheduler.schedule(self.ev('b', at=self.clock.value, dedup_key='key')))
        self.clock.value = self.at(172800)
        self.assertTrue(self.scheduler.schedule(self.ev('b', at=self.clock.value, dedup_key='key')))
        self.assertEqual(self.scheduler._dedup, {})

    def test_unshown_cancellation_is_not_success(self):
        self.scheduler.schedule(self.ev('a', scope='clock', dedup_key='key'))
        self.scheduler.claim_for_presentation()
        self.scheduler.cancel_scope('clock')
        self.assertTrue(self.scheduler.schedule(self.ev('b', dedup_key='key')))
        self.assertEqual(self.scheduler._dedup, {})

    def test_cancel_after_output_keeps_dedup(self):
        self.scheduler.schedule(self.ev('a', dedup_key='key'))
        self.scheduler.claim_for_presentation()
        self.scheduler.mark_presented('a')
        self.scheduler.cancel('a')
        self.assertFalse(self.scheduler.schedule(self.ev('b', dedup_key='key')))

    def test_waiting_survives_then_released(self):
        self.scheduler.schedule_many([self.ev('a'), self.ev('b', T.CLOCK)])
        self.scheduler.claim_for_presentation()
        self.clock.value = self.at(60)
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.ids(self.scheduler.waiting), ['b'])
        self.scheduler.complete()
        self.assertEqual(self.scheduler.claim_for_presentation().event_id, 'b')

    def test_new_due_event_joins_waiting_while_current(self):
        self.scheduler.schedule(self.ev('a'))
        self.scheduler.claim_for_presentation()
        self.scheduler.schedule(self.ev('b', T.CLOCK))
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.ids(self.scheduler.waiting), ['b'])

    def test_waiting_expires(self):
        self.scheduler.schedule_many([self.ev('a'), self.ev('b', T.CLOCK)])
        self.scheduler.claim_for_presentation()
        self.clock.value = self.at(121)
        self.scheduler.complete()
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.scheduler.waiting, ())

    def test_waiting_priority_and_deterministic_order(self):
        self.scheduler.schedule(self.ev('current', T.CLOCK))
        self.scheduler.claim_for_presentation()
        self.scheduler.schedule_many([self.ev('low', T.DAILY_WIRD), self.ev('b', T.SUNRISE),
            self.ev('a', T.SUNRISE), self.ev('high')])
        self.scheduler.claim_for_presentation()
        self.assertEqual(self.ids(self.scheduler.waiting), ['high', 'a', 'b', 'low'])
        self.scheduler.complete()
        self.assertEqual(self.scheduler.claim_for_presentation().event_id, 'high')

    def test_scope_cancellation_releases_other_waiting(self):
        self.scheduler.schedule_many([self.ev('p', scope='prayer.fajr'),
            self.ev('p2', scope='prayer.sunrise'), self.ev('c', T.CLOCK, scope='clock')])
        self.scheduler.claim_for_presentation()
        self.assertEqual(self.scheduler.cancel_scope('prayer'), 2)
        self.assertEqual(self.ids(self.scheduler.waiting), ['c'])
        self.assertEqual(self.scheduler.claim_for_presentation().event_id, 'c')

    def test_scope_match_uses_path_boundary(self):
        self.scheduler.schedule(self.ev('x', scope='adhkar.morningExtra'))
        self.assertEqual(self.scheduler.cancel_scope('adhkar.morning'), 0)

    def test_rebuild_filters_past_and_preserves_other_scope(self):
        self.scheduler.schedule_many([self.ev('p', scope='prayer'), self.ev('old', T.CLOCK, scope='clock')])
        self.scheduler.claim_for_presentation()
        self.assertEqual(self.scheduler.rebuild([self.ev('past', T.CLOCK, self.at(-1), scope='clock'),
            self.ev('new', T.CLOCK, self.at(20), scope='clock'), self.ev('wrong', scope='prayer')], self.now, scope='clock'), 1)
        self.assertEqual(self.scheduler.current.event_id, 'p')
        self.assertEqual(self.scheduler.wakeup_at, self.at(20))

    def test_resume_requires_source_without_erasing(self):
        self.scheduler.schedule(self.ev('x'))
        with self.assertRaisesRegex(ValueError, 'source'): self.scheduler.resume()
        self.assertEqual(self.scheduler.next_due().event_id, 'x')

    def test_resume_no_due_rebuilds_future(self):
        source = Mock(return_value=[self.ev('future', at=self.at(60))])
        self.assertIsNone(self.scheduler.resume(rebuild_source=source))
        source.assert_called_once_with(self.now, 'resume', None)
        self.assertEqual(self.scheduler.wakeup_at, self.at(60))

    def test_resume_one_valid_and_no_second_handoff(self):
        self.scheduler.schedule(self.ev('one', at=self.at(-60)))
        source = Mock(return_value=[self.ev('future', at=self.at(60))])
        self.assertEqual(self.scheduler.resume(rebuild_source=source).event_id, 'one')
        self.assertIsNone(self.scheduler.resume(rebuild_source=source))
        self.scheduler.complete()
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.clock.value = self.at(60)
        self.assertEqual(self.scheduler.claim_for_presentation().event_id, 'future')

    def test_resume_many_selects_one_discards_catchup(self):
        missed = [self.ev('clock', T.CLOCK, self.at(-30)), self.ev('prayer', at=self.at(-60)),
            self.ev('sunrise', T.SUNRISE, self.at(-30))]
        self.scheduler.schedule_many(missed)
        source = lambda *_: missed + [self.ev('atNow'), self.ev('future', at=self.at(120))]
        self.assertEqual(self.scheduler.resume(rebuild_source=source).event_id, 'prayer')
        self.scheduler.complete()
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.scheduler.wakeup_at, self.at(120))

    def test_resume_equal_priority_order(self):
        self.scheduler.schedule_many([self.ev('evening', T.EVENING_ADHKAR, self.at(-30)),
            self.ev('morning', T.MORNING_ADHKAR, self.at(-30)), self.ev('older', T.DAILY_WIRD, self.at(-60))])
        self.assertEqual(self.scheduler.resume(rebuild_source=lambda *_: []).event_id, 'older')

    def test_resume_rejects_expired_recurring_and_references(self):
        events = [self.ev('expired', at=self.at(-601)), self.ev('recurring', T.RECURRING_DHIKR, self.at(-1))]
        for kind in (T.PRAYER_PRE_ALERT, T.IQAMA_PRE_ALERT, T.MORNING_ADHKAR, T.EVENING_ADHKAR, T.FRIDAY_HOUR):
            events.append(self.ev(kind.value, kind, self.at(-60), reference_at=self.now, timing=AlertTiming.BEFORE))
        self.scheduler.schedule_many(events)
        self.assertIsNone(self.scheduler.resume(rebuild_source=lambda *_: []))
        self.assertEqual(self.scheduler.waiting, ())

    def test_resume_skips_previously_presented(self):
        self.scheduler.schedule(self.ev('x', dedup_key='shared'))
        self.scheduler.claim_for_presentation()
        self.scheduler.complete()
        self.assertFalse(self.scheduler.schedule(self.ev('y', dedup_key='shared')))
        self.assertIsNone(self.scheduler.resume(rebuild_source=lambda *_: [self.ev('z', at=self.at(1), dedup_key='shared')]))
        self.assertIsNone(self.scheduler.wakeup_at)

    def test_resume_source_failure_preserves_queue(self):
        self.scheduler.schedule(self.ev('x'))
        with self.assertRaisesRegex(RuntimeError, 'source'):
            self.scheduler.resume(rebuild_source=Mock(side_effect=RuntimeError('source')))
        self.assertEqual(self.scheduler.next_due().event_id, 'x')

    def test_dst_gap_first_valid_instant(self):
        tz = BundledTimezoneProvider().get_timezone('America/New_York')
        value = resolve_civil_time(datetime(2026, 3, 8, 2, 30, 45), tz)
        self.assertEqual((value.hour, value.minute, value.second), (3, 0, 0))

    def test_dst_fold_elapsed_time_and_dedup(self):
        tz = BundledTimezoneProvider().get_timezone('America/New_York')
        wall = datetime(2026, 11, 1, 1, 30)
        first = Instant(wall.replace(tzinfo=tz, fold=0))
        second = Instant(wall.replace(tzinfo=tz, fold=1))
        self.assertEqual(resolve_civil_time(wall, tz).fold, 0)
        e = self.ev('first', T.DAILY_WIRD, first, dedup_key='wird:2026-11-01')
        self.assertFalse(e.is_valid_at(second))
        self.clock.value = first
        self.scheduler.schedule(e)
        self.scheduler.claim_for_presentation()
        self.scheduler.complete()
        self.clock.value = second
        self.assertFalse(self.scheduler.schedule(self.ev('second', T.DAILY_WIRD, second, dedup_key=e.dedup_key)))

    def test_quiet_hours_suppression_no_catchup_manual_unaffected(self):
        settings = default_settings()
        settings.clock.automatic_alert_enabled = True
        settings.general.quiet_hours.enabled = True
        settings.general.quiet_hours.start = ClockTime(11, 0)
        settings.general.quiet_hours.end = ClockTime(12, 1)
        scheduler = AlertScheduler(self.clock, settings)
        scheduler.schedule(self.ev('quiet', T.CLOCK, scope='clock'))
        self.assertIsNone(scheduler.claim_for_presentation())
        self.clock.value = self.at(60)
        self.assertIsNone(scheduler.claim_for_presentation())
        self.assertFalse(scheduler.schedule(self.ev('replay', T.CLOCK, self.clock.value, dedup_key='quiet')))
        self.assertTrue(manual_commands_allowed())
        self.assertEqual(scheduler._dedup, {})
        self.clock.value = self.at(172800)
        scheduler.due()
        self.assertEqual(scheduler._suppressed, {})

    def test_quiet_at_scheduled_time_suppresses_late_first_poll(self):
        s = default_settings(); s.clock.automatic_alert_enabled = True
        s.general.quiet_hours.enabled = True
        s.general.quiet_hours.start = ClockTime(11, 0); s.general.quiet_hours.end = ClockTime(12, 1)
        scheduler = AlertScheduler(self.clock, s)
        scheduler.schedule(self.ev('x', T.CLOCK, scope='clock'))
        self.clock.value = self.at(61)
        self.assertIsNone(scheduler.claim_for_presentation())

    def test_quiet_local_conversion_and_prayer_exemption(self):
        s = default_settings(); s.general.quiet_hours.enabled = True
        s.clock.automatic_alert_enabled = True
        scheduler = AlertScheduler(self.clock, s, local_time_provider=lambda i: i.value.astimezone(timezone(timedelta(hours=11))))
        scheduler.schedule_many([self.ev('p', scope='prayer'), self.ev('c', T.CLOCK, scope='clock')])
        self.assertEqual(scheduler.claim_for_presentation().event_id, 'p')
        self.assertEqual(scheduler.waiting, ())
        scheduler.complete(); s.general.quiet_hours.apply_to_prayer_alerts = True
        scheduler.schedule(self.ev('p2', scope='prayer'))
        self.assertIsNone(scheduler.claim_for_presentation())

    def test_waiting_rechecks_live_hierarchy_without_coordinator(self):
        state = default_settings(); state.clock.automatic_alert_enabled = True
        scheduler = AlertScheduler(self.clock, lambda: state)
        scheduler.schedule_many([self.ev('p', scope='prayer'), self.ev('c', T.CLOCK, scope='clock')])
        scheduler.claim_for_presentation()
        self.assertEqual(self.ids(scheduler.waiting), ['c'])
        state = deepcopy(state); state.clock.automatic_alert_enabled = False
        scheduler.complete()
        self.assertIsNone(scheduler.claim_for_presentation())
        self.assertEqual(scheduler.waiting, ())

    def test_waiting_reference_is_rechecked(self):
        self.scheduler.schedule_many([self.ev('p'), self.ev('pre', T.IQAMA_PRE_ALERT, reference_at=self.at(10))])
        self.scheduler.claim_for_presentation()
        self.assertEqual(self.ids(self.scheduler.waiting), ['pre'])
        self.clock.value = self.at(10)
        self.scheduler.complete()
        self.assertIsNone(self.scheduler.claim_for_presentation())

    def test_resume_same_time_type_and_id_tie(self):
        self.scheduler.schedule_many([self.ev('z', T.EVENING_ADHKAR, self.at(-1)),
            self.ev('b', T.MORNING_ADHKAR, self.at(-1)), self.ev('a', T.MORNING_ADHKAR, self.at(-1))])
        self.assertEqual(self.scheduler.resume(rebuild_source=lambda *_: []).event_id, 'a')
        self.scheduler.complete()
        self.assertIsNone(self.scheduler.resume(rebuild_source=lambda *_: []))

    def test_scope_rebuild_generator_failure_is_atomic(self):
        self.scheduler.schedule(self.ev('old', scope='clock'))
        def failing():
            yield self.ev('new', scope='clock')
            raise RuntimeError('failed build')
        with self.assertRaisesRegex(RuntimeError, 'failed build'):
            self.scheduler.rebuild(failing(), self.now, scope='clock')
        self.assertEqual(self.scheduler.next_due().event_id, 'old')

    def test_early_time_and_negative_grace(self):
        self.assertFalse(self.ev('future', at=self.at(1)).is_valid_at(self.now))
        with self.assertRaisesRegex(ValueError, 'negative'):
            self.ev('bad', grace_period=timedelta(seconds=-1))

    def test_shutdown_clears_and_rejects_operations(self):
        self.scheduler.schedule_many([self.ev('a'), self.ev('b')])
        self.scheduler.claim_for_presentation()
        self.scheduler.shutdown(); self.scheduler.shutdown()
        self.assertIsNone(self.scheduler.current)
        self.assertEqual(self.scheduler.waiting, ())
        self.assertIsNone(self.scheduler.wakeup_at)
        for operation in (lambda: self.scheduler.schedule(self.ev('x')), self.scheduler.due,
                self.scheduler.claim_for_presentation, self.scheduler.resume, self.scheduler.complete):
            with self.assertRaises(RuntimeError): operation()


class AlertCoordinatorTests(AlertFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        settings = default_settings()
        settings.clock.automatic_alert_enabled = True
        for key in ('morning', 'evening', 'friday_hour', 'daily_wird', 'recurring'):
            getattr(settings.adhkar, key).enabled = True
        self.service = SettingsService(Repository(settings), self.clock)
        self.scheduler = AlertScheduler(self.clock, lambda: self.service.runtime_settings)
        self.source = Mock(return_value=[])
        self.coordinator = AlertCoordinator(self.scheduler, self.service.events, self.source)

    def test_apply_all_hierarchy_levels_without_recreating_scheduler(self):
        item = next(iter(self.service.runtime_settings.adhkar.recurring.items))
        cases = [('general.all_automatic_alerts_enabled', None), ('prayer.alerts_enabled', 'prayer'),
            ('clock.automatic_alert_enabled', 'clock'), ('adhkar.alerts_enabled', 'adhkar'),
            ('adhkar.morning.enabled', 'adhkar.morning'), ('adhkar.evening.enabled', 'adhkar.evening'),
            ('adhkar.friday_hour.enabled', 'adhkar.friday'), ('adhkar.daily_wird.enabled', 'adhkar.dailyWird'),
            ('adhkar.recurring.enabled', 'adhkar.recurring')]
        original_scheduler = self.scheduler
        for index, (path, scope) in enumerate(cases):
            with self.subTest(scope=scope):
                self.source.reset_mock()
                event_scope = scope or 'prayer'
                before = self.service.runtime_settings
                self.scheduler.schedule(self.ev(f'current{index}', scope=event_scope))
                self.scheduler.schedule(self.ev(f'waiting{index}', scope=event_scope))
                self.scheduler.schedule(self.ev(f'future{index}', at=self.at(60), scope=event_scope))
                self.scheduler.claim_for_presentation()
                draft = self.service.open_draft()
                target = draft.settings
                if path == 'item': target = target.adhkar.recurring.items[item]; name = 'enabled'
                else:
                    *parents, name = path.split('.')
                    for parent in parents: target = getattr(target, parent)
                setattr(target, name, False)
                expected = deepcopy(draft.settings)
                self.service.apply(draft)
                self.assertEqual(self.service.runtime_settings, expected)
                self.assertEqual(before.prayer.events, self.service.runtime_settings.prayer.events)
                self.assertIsNone(self.scheduler.current)
                self.assertEqual(self.scheduler.waiting, ())
                self.assertFalse(self.scheduler.schedule(self.ev(f'disabled{index}', scope=event_scope)))
                self.source.assert_not_called()
                setattr(target, name, True)
                self.source.return_value = [self.ev(f'new{index}', at=self.at(60), scope=event_scope),
                    self.ev(f'past{index}', at=self.at(-1), scope=event_scope)]
                self.service.apply(draft)
                self.source.assert_called_once_with(self.now, 'settingsApplied', scope)
                self.assertIsNone(self.scheduler.claim_for_presentation())
                self.assertEqual(self.scheduler.wakeup_at, self.at(60))
                self.scheduler.cancel_scope(None)
                self.assertIs(self.scheduler, original_scheduler)

    def test_disable_clock_keeps_prayer_current_and_other_waiting(self):
        self.scheduler.schedule_many([self.ev('p', scope='prayer'), self.ev('p2', scope='prayer'),
            self.ev('c', T.CLOCK, scope='clock')])
        self.scheduler.claim_for_presentation()
        draft = self.service.open_draft(); draft.settings.clock.automatic_alert_enabled = False
        self.service.apply(draft)
        self.assertEqual(self.scheduler.current.event_id, 'p')
        self.assertEqual(self.ids(self.scheduler.waiting), ['p2'])

    def test_disable_adhkar_keeps_clock(self):
        self.scheduler.schedule_many([self.ev('a', scope='adhkar.morning'), self.ev('c', T.CLOCK, scope='clock')])
        self.scheduler.claim_for_presentation()
        draft = self.service.open_draft(); draft.settings.adhkar.alerts_enabled = False
        self.service.apply(draft)
        self.assertEqual(self.scheduler.claim_for_presentation().event_id, 'c')

    def test_unchanged_apply_and_calendar_do_not_rebuild(self):
        draft = self.service.open_draft()
        self.service.apply(draft)
        draft.settings.calendar.open_daily_info_window = True
        self.service.apply(draft)
        self.source.assert_not_called()

    def test_changed_timing_rebuilds_only_function_from_event_time(self):
        self.clock.value = self.at(100)
        draft = self.service.open_draft(); draft.settings.adhkar.morning.minutes = 20
        self.service.apply(draft)
        self.source.assert_called_once_with(self.at(100), 'settingsApplied', 'adhkar.morning')

    def test_rebuild_from_marker(self):
        state = self.service.runtime_settings
        scheduler = AlertScheduler(self.clock, lambda: state)
        source = Mock(return_value=[])
        dispatcher = EventDispatcher(); coordinator = AlertCoordinator(scheduler, dispatcher, source)
        state.clock.intervals.on_half = True
        dispatcher.publish(SettingsApplied(self.now, 1, self.at(100)))
        source.assert_called_once_with(self.at(100), 'settingsApplied', 'clock')
        coordinator.close()

    def test_calculation_rebuilds_affected_scopes(self):
        draft = self.service.open_draft()
        draft.settings.prayer.calculation_method = next(kind for kind in CalculationMethod if kind != draft.settings.prayer.calculation_method)
        self.service.apply(draft)
        self.assertEqual([call.args[2] for call in self.source.call_args_list],
            ['prayer', 'clock', 'adhkar.morning', 'adhkar.evening', 'adhkar.friday'])

    def test_location_event_cancels_old_and_rebuilds(self):
        self.scheduler.schedule(self.ev('old', at=self.at(100)))
        self.source.return_value = [self.ev('new', at=self.at(200))]
        self.service.events.publish(LocationChanged(self.at(20), None, None))
        self.source.assert_called_once_with(self.at(20), 'locationChanged', None)
        self.assertEqual(self.scheduler.wakeup_at, self.at(200))
        self.assertEqual(self.ids(self.scheduler.due(self.at(200))), ['new'])

    def test_system_time_event_rebuilds_from_occurrence(self):
        self.scheduler.schedule(self.ev('old', at=self.at(100)))
        self.service.events.publish(SystemTimeChanged(self.at(20)))
        self.source.assert_called_once_with(self.at(20), 'systemTimeChanged', None)
        self.assertIsNone(self.scheduler.wakeup_at)

    def test_coordinator_resume_uses_source(self):
        self.source.return_value = [self.ev('new', at=self.at(30))]
        self.assertIsNone(self.coordinator.resume())
        self.source.assert_called_once_with(self.now, 'resume', None)
        self.assertEqual(self.scheduler.wakeup_at, self.at(30))

    def test_legacy_wird_scope_cancels_immediately_on_apply(self):
        self.scheduler.schedule(self.ev('legacy', T.DAILY_WIRD, scope='adhkar.daily_wird'))
        self.scheduler.claim_for_presentation()
        self.assertEqual(self.scheduler.current.scope, 'adhkar.dailyWird')
        draft = self.service.open_draft(); draft.settings.adhkar.daily_wird.enabled = False
        self.service.apply(draft)
        self.assertIsNone(self.scheduler.current)

    def test_static_settings_rejected_for_event_coordinator(self):
        with self.assertRaisesRegex(ValueError, 'provider'):
            AlertCoordinator(AlertScheduler(self.clock, default_settings()), EventDispatcher(), self.source)

    def test_item_disable_preserves_current_and_rebuilds_recurring_future(self):
        first, second = list(self.service.runtime_settings.adhkar.recurring.items)[:2]
        self.scheduler.schedule_many([self.ev('current', T.RECURRING_DHIKR, scope='adhkar.recurring.' + first.value),
            self.ev('sibling', T.RECURRING_DHIKR, scope='adhkar.recurring.' + second.value)])
        self.scheduler.claim_for_presentation()
        draft = self.service.open_draft()
        before = deepcopy(draft.settings.adhkar.recurring)
        draft.settings.adhkar.recurring.items[first].enabled = False
        self.service.apply(draft)
        self.assertEqual(self.service.runtime_settings.adhkar.recurring.items[second], before.items[second])
        self.assertEqual(self.scheduler.current.event_id, 'current')
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertEqual(self.scheduler.waiting, ())
        self.source.assert_called_once_with(self.now, 'recurringMembershipChanged', 'adhkar.recurring')

    def test_location_apply_reads_committed_settings_and_rebuilds_once(self):
        from awqati.domain import Location, StoredLocation, LocationKind
        draft = self.service.open_draft()
        draft.settings.location = StoredLocation(LocationKind.CUSTOM, Location('custom', 'Place', 24, 46, 'Asia/Riyadh'))
        draft.settings.clock.automatic_alert_enabled = False
        seen = []
        def source(now, reason, scope):
            seen.append(self.scheduler.settings.clock.automatic_alert_enabled)
            return [self.ev('clock', T.CLOCK, self.at(30), scope='clock')]
        self.coordinator._rebuild = Mock(side_effect=source)
        self.service.apply(draft)
        self.assertEqual(seen, [False])
        self.coordinator._rebuild.assert_called_once_with(self.now, 'locationChanged', None)
        self.assertIsNone(self.scheduler.wakeup_at)

    def test_scope_callback_sees_new_values_before_build(self):
        seen = []
        def source(now, reason, scope):
            seen.append(self.scheduler.settings.adhkar.morning.minutes)
            return []
        self.coordinator._rebuild = source
        draft = self.service.open_draft(); draft.settings.adhkar.morning.minutes = 40
        self.service.apply(draft)
        self.assertEqual(seen, [40])

    def test_closed_listener_snapshot_does_not_invoke_source(self):
        # Dispatcher snapshots listeners; close can occur earlier in that snapshot.
        dispatcher = EventDispatcher()
        holder = []
        dispatcher.subscribe(SystemTimeChanged, lambda _: holder[0].close())
        coordinator = AlertCoordinator(self.scheduler, dispatcher, self.source)
        holder.append(coordinator)
        dispatcher.publish(SystemTimeChanged(self.now))
        self.source.assert_not_called()

    def test_close_unsubscribes_and_shutdown_once(self):
        self.scheduler.shutdown = Mock(wraps=self.scheduler.shutdown)
        self.coordinator.close(); self.coordinator.close()
        self.scheduler.shutdown.assert_called_once_with()
        for event in (SettingsApplied(self.now, 1), LocationChanged(self.now, None, None), SystemTimeChanged(self.now)):
            self.service.events.publish(event)
        self.source.assert_not_called()
        with self.assertRaises(RuntimeError): self.coordinator.resume()


class AlertArchitectureTests(unittest.TestCase):
    def test_no_platform_output_network_producer_or_timer(self):
        root = Path(__file__).resolve().parents[1] / 'addon/globalPlugins/awqati'
        forbidden = {'wx', 'speech', 'nvwave', 'ui', 'ctypes', 'socket', 'urllib', 'threading', 'requests'}
        for path in (root / 'domain/alerts.py', root / 'application/alert_scheduler.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            # 4.2 adds standalone producers, never inside the 4.1 core.
            self.assertTrue({'PrayerAlertProducer', 'ClockAlertProducer'}.isdisjoint(
                node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(forbidden.isdisjoint(a.name.split('.')[0] for a in node.names))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden)
        # Task 4.4 supplies these classes outside the 4.1 scheduler/domain core.
        expected = {
            root / 'application/alert_presenter.py': 'AlertPresenter',
            root / 'nvda_adapter/audio_service.py': 'AudioService',
            root / 'nvda_adapter/speech_service.py': 'SpeechService',
        }
        for path, class_name in expected.items():
            names = {node.name for node in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
                if isinstance(node, ast.ClassDef)}
            self.assertIn(class_name, names)


if __name__ == '__main__': unittest.main()
