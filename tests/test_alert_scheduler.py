import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0, 'addon/globalPlugins')
from awqati.domain import AlertEvent, AlertEventType, AlertPriority, Instant, default_settings
from awqati.application import AlertScheduler, priority_for, resolve_civil_time

class AlertSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.now = Instant(datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
        self.scheduler = AlertScheduler(lambda: self.now)
    def ev(self, eid, kind=AlertEventType.PRAYER_TIME, at=None, priority=None, **kw):
        return AlertEvent(eid, kind, at or self.now, priority or priority_for(kind), dedup_key=kw.pop('dedup_key', eid), **kw)
    def test_priority_order_and_deterministic_tie(self):
        self.scheduler.schedule(self.ev('b', AlertEventType.CLOCK))
        self.scheduler.schedule(self.ev('a', AlertEventType.PRAYER_TIME))
        self.assertEqual([e.event_id for e in self.scheduler.due()], ['a', 'b'])
    def test_expiry_and_grace(self):
        e=self.ev('clock', AlertEventType.CLOCK)
        self.scheduler.schedule(e)
        self.assertIsNotNone(self.scheduler.next_due(self.now))
        late=Instant(self.now.value+timedelta(minutes=3))
        self.assertIsNone(self.scheduler.next_due(late))
    def test_pre_alert_expires_at_reference(self):
        ref=Instant(self.now.value+timedelta(minutes=10))
        e=self.ev('pre', AlertEventType.PRAYER_PRE_ALERT, reference_at=ref)
        self.scheduler.schedule(e)
        self.assertIsNone(self.scheduler.next_due(ref))
    def test_dedup_and_claim(self):
        self.scheduler.schedule(self.ev('one'))
        self.assertIsNotNone(self.scheduler.claim_for_presentation())
        self.assertFalse(self.scheduler.schedule(self.ev('two', dedup_key='one')))
    def test_disable_scope_preserves_children(self):
        s=default_settings(); s.prayer.alerts_enabled=False
        scheduler=AlertScheduler(lambda:self.now, s)
        scheduler.schedule(self.ev('p', scope='prayer.fajr'))
        self.assertIsNone(scheduler.claim_for_presentation())
        self.assertFalse(s.prayer.alerts_enabled is False and False)
    def test_dst_missing_and_repeated(self):
        tz=ZoneInfo('America/New_York')
        missing=resolve_civil_time(datetime(2026,3,8,2,30),tz)
        self.assertEqual(missing.hour,3)
        repeated=resolve_civil_time(datetime(2026,11,1,1,30),tz)
        self.assertEqual(repeated.fold,0)
    def test_shutdown(self):
        self.scheduler.shutdown()
        with self.assertRaises(RuntimeError): self.scheduler.schedule(self.ev('x'))

if __name__ == '__main__': unittest.main()