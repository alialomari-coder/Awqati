"""Accepted civil-midnight horizon, night bridges and central renewal."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addon/globalPlugins'))
from awqati.application import (AlertScheduler, AlertCoordinator, EventDispatcher,
	PrayerClockRebuildSource, PrayerService)
from awqati.application.prayer_clock_rebuild_source import next_local_midnight
from awqati.domain import (Instant, Location, LocationKind, StoredLocation, default_settings,
	AlertEventType as T, PrayerEventName as N, SettingsApplied, SystemTimeChanged, LocationChanged)
from awqati.domain.alerts import utc
from awqati.infrastructure import BundledTimezoneProvider, BundledCalculationMethodRepository


class BridgePrayers:
	"""A ten-hour night crossing civil midnight: middle 01:00, last third 02:40."""
	def __init__(self, zones): self.zones, self.calls = zones, []
	def calculate(self, request):
		self.calls.append(request)
		zone = self.zones.get_timezone(request.timezone_id)
		def at(hour): return datetime.combine(request.local_date, datetime.min.time(), zone).replace(hour=hour)
		return SimpleNamespace(fajr=at(6), sunrise=at(7), dhuhr=at(12), asr=at(15),
			maghrib=at(20), isha=at(22), metadata=None)


class DailyRenewalTests(unittest.TestCase):
	def setUp(self):
		self.zones = BundledTimezoneProvider()
		self.settings = default_settings()
		self.settings.location = StoredLocation(LocationKind.SELECTED,
			Location('test', 'Test', 51.5, 0, 'Etc/UTC'), 'GB')
		self.settings.clock.automatic_alert_enabled = True
		self.prayers = BridgePrayers(self.zones)
		self.source = PrayerClockRebuildSource.from_services(lambda: self.settings, self.prayers, self.zones)
		self.now = self.at(15)

	@staticmethod
	def at(day, hour=0, minute=0): return Instant(datetime(2026, 1, day, hour, minute, tzinfo=timezone.utc))
	def events(self, start=None, scope=None): return self.source(start or self.now, 'test', scope)

	def test_window_includes_now_excludes_next_midnight(self):
		start = self.at(15, 23)
		events = self.events(start, 'clock')
		self.assertEqual([utc(e.scheduled_at) for e in events], [utc(start)])
		self.assertEqual(self.source.next_rebuild_at(start), self.at(16))

	def test_midnight_is_in_new_batch_only(self):
		old = self.events(self.at(15, 23), 'clock')
		new = self.events(self.at(16), 'clock')
		self.assertEqual(new[0].scheduled_at, self.at(16))
		self.assertFalse({e.dedup_key for e in old} & {e.dedup_key for e in new})

	def test_2345_to_midnight_selected_quarters(self):
		self.settings.clock.intervals.on_three_quarters = True
		self.assertEqual([e.scheduled_at for e in self.events(self.at(15, 23, 45), 'clock')], [self.at(15, 23, 45)])

	def test_last_third_of_previous_night_survives_midnight_rebuild(self):
		events = self.events(self.at(16), 'prayer')
		event = next(e for e in events if e.event_type is T.LAST_THIRD)
		self.assertEqual(event.scheduled_at, self.at(16, 2, 40))
		self.assertTrue(any(request.local_date.day == 15 for request in self.prayers.calls))

	def test_religious_midnight_of_previous_night_survives(self):
		event = next(e for e in self.events(self.at(16), 'prayer') if e.event_type is T.MIDNIGHT)
		self.assertEqual(event.scheduled_at, self.at(16, 1))

	def test_previous_night_pre_and_post_alerts_survive(self):
		self.settings.prayer.events[N.MIDNIGHT].post_alert_minutes = 20
		events = self.events(self.at(16), 'prayer')
		middle = [e for e in events if e.metadata['event_name'] == 'midnight']
		self.assertEqual({e.scheduled_at for e in middle}, {self.at(16, 0, 50), self.at(16, 1), self.at(16, 1, 20)})

	def test_previous_day_iqama_crossing_midnight_survives(self):
		self.settings.prayer.events[N.ISHA].iqama.delay_minutes = 180
		events = self.events(self.at(16), 'prayer')
		iqama = next(e for e in events if e.event_type is T.IQAMA_PRE_ALERT and e.metadata['event_name'] == 'isha')
		self.assertEqual(iqama.scheduled_at, self.at(16, 0, 55))

	def test_next_day_reference_prealert_inside_window(self):
		# Moving the middle of tonight earlier makes its prealert occur today.
		self.settings.prayer.events[N.MIDNIGHT].pre_alert_minutes = 180
		events = self.events(self.at(15, 21), 'prayer')
		event = next(e for e in events if e.event_type is T.PRAYER_PRE_ALERT and e.metadata['event_name'] == 'midnight')
		self.assertEqual(event.scheduled_at, self.at(15, 22))
		self.assertEqual(event.reference_at, self.at(16, 1))

	def test_no_past_occurrences_replayed(self):
		start = self.at(16, 2, 41)
		events = self.events(start)
		self.assertTrue(all(utc(start) <= utc(e.scheduled_at) < utc(self.at(17)) for e in events))
		self.assertFalse(any(e.event_type in (T.MIDNIGHT, T.LAST_THIRD) for e in events))

	def test_scopes_share_same_horizon(self):
		start = self.at(15, 23)
		for scope in ('prayer', 'clock', None):
			with self.subTest(scope=scope):
				events = self.events(start, scope)
				self.assertTrue(all(utc(start) <= utc(e.scheduled_at) < utc(self.at(16)) for e in events))
				self.assertTrue(all(scope is None or e.scope == scope for e in events))

	def test_effective_location_midnight_not_utc_midnight(self):
		self.settings.location.location = Location('riyadh', 'Riyadh', 24.7, 46.7, 'Asia/Riyadh')
		self.assertEqual(utc(self.source.next_rebuild_at(self.at(15, 12))), utc(self.at(15, 21)))

	def test_dst_spring_day_is_23_hours(self):
		self.assert_dst_day(3, 29, 23)

	def test_dst_fall_day_is_25_hours(self):
		self.assert_dst_day(10, 25, 25)

	def assert_dst_day(self, month, day, hours):
		zone = self.zones.get_timezone('Europe/London')
		start = Instant(datetime(2026, month, day, tzinfo=zone))
		end = next_local_midnight(start, zone)
		self.assertEqual(utc(end) - utc(start), timedelta(hours=hours))
		self.assertEqual(end.value.hour, 0)
		self.assertEqual(end.value.day, day + 1)

	def test_rebuild_at_midnight_uses_following_civil_date(self):
		self.assertEqual(next_local_midnight(self.at(16), timezone.utc), self.at(17))

	def test_repeated_central_renewal_deduplicates_midnight(self):
		self.now = self.at(16)
		scheduler = AlertScheduler(lambda: self.now, lambda: self.settings)
		coordinator = AlertCoordinator(scheduler, EventDispatcher(), self.source)
		coordinator.renew_day(self.now)
		first_ids = set(scheduler._events)
		coordinator.renew_day(self.now)
		self.assertEqual(set(scheduler._events), first_ids)
		event = scheduler.claim_for_presentation()
		self.assertEqual(event.event_type, T.CLOCK)
		self.assertEqual(event.scheduled_at, self.now)
		scheduler.complete()
		coordinator.renew_day(self.now)
		self.assertIsNone(scheduler.claim_for_presentation())

	def test_daily_renewal_keeps_existing_presentation_lease(self):
		self.now = self.at(15, 23)
		scheduler = AlertScheduler(lambda: self.now, lambda: self.settings)
		coordinator = AlertCoordinator(scheduler, EventDispatcher(), self.source)
		coordinator.renew_day(self.now)
		current = scheduler.claim_for_presentation()
		self.now = self.at(16)
		coordinator.renew_day(self.now)
		self.assertIs(scheduler.current, current)
		self.assertIsNone(scheduler.claim_for_presentation())
		scheduler.complete()
		self.assertEqual(scheduler.claim_for_presentation().scheduled_at, self.now)

	def test_central_renewal_reason_and_failure_atomicity(self):
		dispatcher = EventDispatcher()
		scheduler = AlertScheduler(lambda: self.now, lambda: self.settings)
		source = Mock(wraps=self.source)
		coordinator = AlertCoordinator(scheduler, dispatcher, source)
		coordinator.renew_day(self.now)
		source.assert_called_once_with(self.now, 'localDayChanged', None)
		before = dict(scheduler._events)
		source.side_effect = RuntimeError('preparation failed')
		with self.assertRaises(RuntimeError): coordinator.renew_day(self.now)
		self.assertEqual(scheduler._events, before)
		coordinator.close()
		with self.assertRaises(RuntimeError): coordinator.renew_day(self.now)

	def test_existing_rebuild_reasons_still_immediate(self):
		dispatcher = EventDispatcher()
		source = Mock(wraps=self.source)
		scheduler = AlertScheduler(lambda: self.now, lambda: self.settings)
		coordinator = AlertCoordinator(scheduler, dispatcher, source)
		self.now = self.at(15, 14)
		dispatcher.publish(SystemTimeChanged(self.now))
		source.assert_called_with(self.now, 'systemTimeChanged', None)
		dispatcher.publish(LocationChanged(self.now, None, self.settings.location.location))
		source.assert_called_with(self.now, 'locationChanged', None)
		self.settings.clock.intervals.on_half = True
		dispatcher.publish(SettingsApplied(self.now, 1))
		source.assert_called_with(self.now, 'settingsApplied', 'clock')
		coordinator.resume(self.now)
		source.assert_called_with(self.now, 'resume', None)

	def test_disabled_and_unknown_scopes_do_not_calculate(self):
		self.settings.prayer.alerts_enabled = False
		self.settings.clock.automatic_alert_enabled = False
		self.assertEqual(self.events(), ())
		self.assertEqual(self.prayers.calls, [])
		self.assertEqual(self.events(scope='adhkar'), ())
		self.assertEqual(self.prayers.calls, [])

	def test_location_missing_has_no_boundary_or_events(self):
		self.settings.location = None
		self.assertIsNone(self.source.next_rebuild_at(self.now))
		self.assertEqual(self.events(), ())

	def test_real_calculator_source_integration(self):
		service = PrayerService(BundledCalculationMethodRepository(), self.zones)
		source = PrayerClockRebuildSource.from_services(lambda: self.settings, service, self.zones)
		events = source(self.now, 'test', None)
		self.assertEqual({e.scope for e in events}, {'prayer', 'clock'})
		self.assertTrue(any(e.event_type is T.LAST_THIRD for e in events))
		self.assertEqual(len({e.event_id for e in events}), len(events))

	def test_night_corrections_apply_without_recomputing_state(self):
		self.settings.prayer.corrections_minutes[N.LAST_THIRD] = 7
		event = next(e for e in self.events(scope='prayer') if e.event_type is T.LAST_THIRD)
		self.assertEqual(event.scheduled_at, self.at(15, 2, 47))


if __name__ == '__main__': unittest.main()
