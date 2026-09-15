"""Approved 4.3 contract: compact recurring future while retaining its grid."""

from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import Mock

from test_adhkar_integration import CoordinatorFixture
from test_adhkar_producers import ORDER
from awqati.domain import RecurringDhikrId as D, AlertEventType as T, AlertAction, SystemTimeChanged
from awqati.domain.alerts import utc


class MembershipTests(CoordinatorFixture):
    def recurring_events(self):
        return sorted((e for e in self.scheduler._events.values() if e.event_type is T.RECURRING_DHIKR), key=lambda e: utc(e.scheduled_at))

    def membership(self, identity, enabled):
        self.apply(lambda s: setattr(s.adhkar.recurring.items[identity], 'enabled', enabled))

    def test_reenable_item_inserts_at_canonical_future_position(self):
        self.membership(D.ALHAMDU_LILLAH, False)
        self.seed()
        self.clock.value = self.at(16, 1)
        first = self.scheduler.claim_for_presentation()
        self.assertEqual(first.metadata['dhikr_id'], ORDER[0])
        self.scheduler.complete(now=self.clock.now())
        self.clock.value = self.at(16, 1, 30)
        self.membership(D.ALHAMDU_LILLAH, True)
        future = self.recurring_events()
        self.assertEqual(future[0].scheduled_at, self.at(16, 2))
        self.assertEqual([e.metadata['dhikr_id'] for e in future[:4]], list(ORDER[1:5]))
        self.assertIsNone(self.scheduler.claim_for_presentation())

    def test_reenable_earlier_item_waits_for_wrap(self):
        self.membership(D.SUBHAN_ALLAH, False)
        self.seed()
        self.clock.value = self.at(16, 2, 30)
        self.membership(D.SUBHAN_ALLAH, True)
        future = self.recurring_events()
        # Old sequence at 01:00/02:00 was alhamduLillah/laIlahaIllaAllah.
        self.assertEqual([e.metadata['dhikr_id'] for e in future[:8]], list(ORDER[3:]) + list(ORDER[:2]))
        self.assertEqual(future[0].scheduled_at, self.at(16, 3))

    def test_disable_current_keeps_lease_until_completion(self):
        self.seed()
        self.clock.value = self.at(16, 1)
        current = self.scheduler.claim_for_presentation()
        self.assertEqual(current.metadata['dhikr_id'], ORDER[0])
        self.membership(D.SUBHAN_ALLAH, False)
        self.assertIs(self.scheduler.current, current)
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertIs(self.scheduler.current, current)
        self.assertEqual(self.recurring_events()[0].scheduled_at, self.at(16, 2))
        self.assertEqual(self.recurring_events()[0].metadata['dhikr_id'], ORDER[1])
        self.assertTrue(self.scheduler.complete(now=self.clock.now()))
        self.assertIsNone(self.scheduler.current)

    def test_disable_all_leaves_current_but_no_recurring_future(self):
        self.seed()
        self.clock.value = self.at(16, 1)
        current = self.scheduler.claim_for_presentation()
        def edit(s):
            for item in s.adhkar.recurring.items.values(): item.enabled = False
        self.apply(edit)
        self.assertEqual(self.recurring_events(), [])
        self.assertIs(self.scheduler.current, current)
        self.assertIsNone(self.scheduler.claim_for_presentation())
        self.assertIs(self.scheduler.current, current)
        self.scheduler.complete(now=self.clock.now())
        self.assertTrue(all(e.event_type is not T.RECURRING_DHIKR for e in self.scheduler._events.values()))

    def test_empty_then_reenable_keeps_original_grid(self):
        self.seed()
        self.clock.value = self.at(16, 1, 30)
        def edit(s):
            for item in s.adhkar.recurring.items.values(): item.enabled = False
        self.apply(edit)
        self.clock.value = self.at(16, 4, 45)
        self.membership(D.ALHAMDU_LILLAH, True)
        event = self.recurring_events()[0]
        self.assertEqual(event.scheduled_at, self.at(16, 5))
        self.assertEqual(event.metadata['dhikr_id'], ORDER[1])

    def test_initial_empty_cycle_remembers_grid_without_events(self):
        def edit(s):
            for item in s.adhkar.recurring.items.values(): item.enabled = False
        self.apply(edit)
        self.seed()
        self.assertEqual(self.recurring_events(), [])
        self.clock.value = self.at(16, 0, 30)
        self.membership(D.SUBHAN_ALLAH, True)
        self.assertEqual(self.recurring_events()[0].scheduled_at, self.at(16, 1))

    def test_disabled_cycle_membership_saves_only(self):
        self.apply(lambda s: setattr(s.adhkar.recurring, 'enabled', False))
        self.seed()
        spy = Mock(wraps=self.source)
        self.coordinator._rebuild = spy
        self.clock.value = self.at(16, 0, 30)
        self.membership(D.SUBHAN_ALLAH, False)
        spy.assert_not_called()
        self.assertEqual(self.recurring_events(), [])
        self.assertFalse(self.service.runtime_settings.adhkar.recurring.items[D.SUBHAN_ALLAH].enabled)
        self.apply(lambda s: setattr(s.adhkar.recurring, 'enabled', True))
        self.assertEqual(self.recurring_events()[0].scheduled_at, self.at(16, 1, 30))
        self.assertEqual(self.recurring_events()[0].metadata['dhikr_id'], ORDER[1])

    def test_single_membership_edit_rebuilds_only_recurring_once(self):
        self.seed()
        before = {key:e for key,e in self.scheduler._events.items() if e.event_type is not T.RECURRING_DHIKR}
        spy = Mock(wraps=self.source)
        self.coordinator._rebuild = spy
        self.clock.value = self.at(16, 0, 30)
        self.membership(D.SUBHAN_ALLAH, False)
        spy.assert_called_once_with(self.clock.now(), 'recurringMembershipChanged', 'adhkar.recurring')
        for key,event in before.items(): self.assertIs(self.scheduler._events[key], event)

    def test_multiple_membership_edits_rebuild_once(self):
        self.seed()
        spy = Mock(wraps=self.source)
        self.coordinator._rebuild = spy
        self.apply(lambda s: [setattr(s.adhkar.recurring.items[d], 'enabled', False) for d in (D.SUBHAN_ALLAH,D.ALLAHU_AKBAR,D.LA_TANSA_DHIKR_ALLAH)])
        spy.assert_called_once_with(self.clock.now(), 'recurringMembershipChanged', 'adhkar.recurring')

    def test_repeated_identical_apply_and_rebuild_no_duplicates(self):
        self.seed()
        self.clock.value = self.at(16, 0, 30)
        self.membership(D.SUBHAN_ALLAH, False)
        first = self.recurring_events()
        self.membership(D.SUBHAN_ALLAH, False)
        self.coordinator.renew_day(self.clock.now())
        self.assertEqual(self.recurring_events(), first)
        self.assertEqual(len(first), len({e.dedup_key for e in first}))

    def test_membership_edit_at_due_time_never_issues_immediate_event(self):
        self.seed()
        self.clock.value = self.at(16, 1)
        self.membership(D.SUBHAN_ALLAH, False)
        self.assertEqual(self.recurring_events()[0].scheduled_at, self.at(16, 2))
        self.assertIsNone(self.scheduler.claim_for_presentation())

    def test_membership_preserves_unrelated_current_and_waiting(self):
        from awqati.domain import AlertEvent
        self.seed()
        current = AlertEvent('manual-fixture-current', T.DAILY_WIRD, self.start, scope='adhkar.dailyWird')
        waiting = AlertEvent('manual-fixture-waiting', T.MORNING_ADHKAR, self.start, scope='adhkar.morning')
        self.scheduler.schedule_many((current, waiting))
        claimed = self.scheduler.claim_for_presentation()
        sibling = self.scheduler.waiting[0]
        self.membership(D.SUBHAN_ALLAH, False)
        self.assertIs(self.scheduler.current, claimed)
        self.assertIs(self.scheduler.waiting[0], sibling)

    def test_membership_preserves_prayer_clock_and_all_timed_objects(self):
        self.apply(lambda s: (setattr(s.prayer, 'alerts_enabled', True), setattr(s.clock, 'automatic_alert_enabled', True)))
        self.seed()
        before = {k:e for k,e in self.scheduler._events.items() if e.event_type is not T.RECURRING_DHIKR}
        from awqati.domain import Instant
        # Keep the initial clock occurrence inside its existing two-minute grace.
        self.clock.value = Instant(utc(self.start) + timedelta(seconds=30))
        self.membership(D.ALLAHU_AKBAR, False)
        for key,event in before.items(): self.assertIs(self.scheduler._events[key], event)
        self.assertTrue(any(e.event_type is T.PRAYER_TIME for e in before.values()))
        self.assertTrue(any(e.event_type is T.CLOCK for e in before.values()))

    def test_parent_disable_still_cancels_preserved_current(self):
        self.seed()
        self.clock.value = self.at(16, 1)
        self.scheduler.claim_for_presentation()
        self.membership(D.SUBHAN_ALLAH, False)
        self.apply(lambda s: setattr(s.adhkar.recurring, 'enabled', False))
        self.assertIsNone(self.scheduler.current)

    def test_membership_does_not_change_interval_output_or_other_items(self):
        self.seed()
        old = deepcopy(self.service.runtime_settings)
        self.membership(D.SUBHAN_ALLAH, False)
        old.adhkar.recurring.items[D.SUBHAN_ALLAH].enabled = False
        self.assertEqual(old, self.service.runtime_settings)

    def test_reactivation_after_membership_edit_restarts_from_first(self):
        self.seed()
        self.clock.value = self.at(16, 4, 30)
        self.membership(D.SUBHAN_ALLAH, False)
        self.apply(lambda s: setattr(s.adhkar.recurring, 'enabled', False))
        self.apply(lambda s: setattr(s.adhkar.recurring, 'enabled', True))
        event = self.recurring_events()[0]
        self.assertEqual(event.scheduled_at, self.at(16, 5, 30))
        self.assertEqual(event.metadata['dhikr_id'], ORDER[1])

    def test_interval_change_still_starts_new_full_interval(self):
        self.seed()
        self.clock.value = self.at(16, 4, 30)
        self.membership(D.SUBHAN_ALLAH, False)
        self.apply(lambda s: setattr(s.adhkar.recurring, 'interval_minutes', 5))
        self.assertEqual(self.recurring_events()[0].scheduled_at, self.at(16, 4, 35))

    def test_membership_mapping_continues_across_midnight(self):
        self.seed()
        self.clock.value = self.at(16, 22, 30)
        self.membership(D.LA_HAWLA_WA_LA_QUWWATA, False)
        last = self.recurring_events()[-1]
        self.clock.value = self.end
        self.coordinator.renew_day(self.end)
        next_event = self.recurring_events()[0]
        enabled = [d for d in ORDER if d != D.LA_HAWLA_WA_LA_QUWWATA.value]
        expected = enabled[(enabled.index(last.metadata['dhikr_id']) + 1) % len(enabled)]
        self.assertEqual(next_event.scheduled_at, self.end)
        self.assertEqual(next_event.metadata['dhikr_id'], expected)

    def test_technical_time_change_keeps_grid_after_membership_edit(self):
        self.seed()
        self.clock.value = self.at(16, 0, 30)
        self.membership(D.SUBHAN_ALLAH, False)
        self.clock.value = self.at(16, 3, 45)
        self.service.events.publish(SystemTimeChanged(self.clock.now()))
        self.assertEqual(self.recurring_events()[0].scheduled_at, self.at(16, 4))


def removal_case(index, before_start):
    def test(self):
        self.seed()
        self.clock.value = self.at(16, 0 if before_start else index, 30)
        original_grid = [e.scheduled_at for e in self.recurring_events() if utc(e.scheduled_at) > utc(self.clock.now())]
        self.membership(tuple(D)[index], False)
        future = self.recurring_events()
        self.assertEqual([e.scheduled_at for e in future], original_grid)
        enabled = [d for d in ORDER if d != ORDER[index]]
        offset = 0 if before_start else index % len(enabled)
        expected = [enabled[(offset+i) % len(enabled)] for i in range(len(future))]
        self.assertEqual([e.metadata['dhikr_id'] for e in future], expected)
        self.assertTrue(all(utc(b.scheduled_at)-utc(a.scheduled_at) == timedelta(hours=1) for a,b in zip(future,future[1:])))
    return test


for index, name in ((0,'first'),(4,'middle'),(8,'last')):
    for before_start in (True,False):
        setattr(MembershipTests, 'test_remove_' + name + ('_before_start' if before_start else '_during_cycle'), removal_case(index,before_start))


if __name__ == '__main__': unittest.main()
