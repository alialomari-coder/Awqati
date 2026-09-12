from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))
if str(ROOT / "tests") not in sys.path:
	sys.path.insert(0, str(ROOT / "tests"))

from awqati.application import (  # noqa: E402
	DEFAULT_CURRENT_PRAYER_DURATION_MINUTES, DEFAULT_EVENT_PRE_ALERT_MINUTES,
	DEFAULT_IQAMA_ALERT_BEFORE_MINUTES, DEFAULT_IQAMA_DELAYS_MINUTES,
	EventPreAlertSettings, IqamaRule, IqamaSettings, PrayerStatePriority, PrayerStateService,
)
from awqati.domain import Instant, PrayerEvent, PrayerEventKind, PrayerEventName  # noqa: E402
from support.event_clock import EventClock  # noqa: E402


UTC = timezone.utc


def at(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
	return datetime(2026, 1, day, hour, minute, second, tzinfo=UTC)


def event(name: PrayerEventName, day: int, hour: int, minute: int = 0) -> PrayerEvent:
	return PrayerEvent(name, at(day, hour, minute))


def timeline() -> tuple[PrayerEvent, ...]:
	return (
		event(PrayerEventName.ISHA, 14, 19, 0),
		event(PrayerEventName.MIDNIGHT, 14, 23, 30),
		event(PrayerEventName.LAST_THIRD, 15, 1, 30),
		event(PrayerEventName.FAJR, 15, 5, 0),
		event(PrayerEventName.SUNRISE, 15, 6, 20),
		event(PrayerEventName.DHUHR, 15, 12, 0),
		event(PrayerEventName.ASR, 15, 15, 15),
		event(PrayerEventName.MAGHRIB, 15, 17, 30),
		event(PrayerEventName.ISHA, 15, 19, 0),
		event(PrayerEventName.MIDNIGHT, 15, 23, 30),
		event(PrayerEventName.LAST_THIRD, 16, 1, 30),
		event(PrayerEventName.FAJR, 16, 5, 0),
		event(PrayerEventName.SUNRISE, 16, 6, 20),
	)


def pre_alerts(value: int = 0, **changes: int) -> EventPreAlertSettings:
	values = {name: value for name in PrayerEventName}
	values.update({PrayerEventName[key.upper()]: item for key, item in changes.items()})
	return EventPreAlertSettings(values)


def iqama_with(name: PrayerEventName, rule: IqamaRule) -> IqamaSettings:
	values = dict(IqamaSettings().rules)
	values[name] = rule
	return IqamaSettings(values)


class IqamaTests(unittest.TestCase):
	def test_central_defaults_and_estimated_times_cover_only_five_prayers(self) -> None:
		self.assertEqual(DEFAULT_IQAMA_ALERT_BEFORE_MINUTES, 5)
		self.assertEqual(DEFAULT_CURRENT_PRAYER_DURATION_MINUTES, 20)
		self.assertEqual(DEFAULT_EVENT_PRE_ALERT_MINUTES, 10)
		self.assertEqual(DEFAULT_IQAMA_DELAYS_MINUTES, {
			PrayerEventName.FAJR: 25, PrayerEventName.DHUHR: 20,
			PrayerEventName.ASR: 20, PrayerEventName.MAGHRIB: 10, PrayerEventName.ISHA: 20,
		})
		prayer_at = at(15, 12)
		for name, delay in DEFAULT_IQAMA_DELAYS_MINUTES.items():
			with self.subTest(name=name):
				rule = IqamaSettings().rules[name]
				self.assertEqual(rule.iqama_at(prayer_at), prayer_at + timedelta(minutes=delay))
				self.assertEqual(rule.alert_at(prayer_at), prayer_at + timedelta(minutes=delay - 5))

	def test_zero_disables_iqama_and_zero_prealert_only_disables_automatic_alert(self) -> None:
		disabled = IqamaRule(0)
		self.assertFalse(disabled.enabled)
		self.assertIsNone(disabled.iqama_at(at(15, 12)))
		self.assertIsNone(disabled.alert_at(at(15, 12)))
		enabled_without_alert = IqamaRule(20, 0)
		self.assertEqual(enabled_without_alert.iqama_at(at(15, 12)), at(15, 12, 20))
		self.assertIsNone(enabled_without_alert.alert_at(at(15, 12)))

	def test_iqama_validation_accepts_only_positive_prealert_below_delay(self) -> None:
		self.assertEqual(IqamaRule(20, 1).alert_before_minutes, 1)
		for delay, alert in ((20, 20), (20, 21)):
			with self.subTest(delay=delay, alert=alert):
				with self.assertRaises(ValueError):
					IqamaRule(delay, alert)
		for delay, alert in ((-1, 0), (20, -1)):
			with self.subTest(delay=delay, alert=alert):
				with self.assertRaises(ValueError):
					IqamaRule(delay, alert)


class PrayerStateTests(unittest.TestCase):
	def state(self, now: datetime, **kwargs):
		return PrayerStateService(EventClock(Instant(now))).snapshot(timeline(), **kwargs)

	def test_current_prayer_with_iqama_uses_half_open_boundaries(self) -> None:
		for now in (at(15, 15, 15), at(15, 15, 35), at(15, 15, 54, 59)):
			state = self.state(now, pre_alerts=pre_alerts())
			self.assertEqual(state.current_prayer.event.name, PrayerEventName.ASR)
			self.assertEqual(state.iqama_at, at(15, 15, 35))
			self.assertEqual(state.current_prayer.ends_at, at(15, 15, 55))
		self.assertIsNone(self.state(at(15, 15, 55), pre_alerts=pre_alerts()).current_prayer)

	def test_duration_zero_twenty_and_180_and_invalid_boundaries(self) -> None:
		self.assertIsNotNone(self.state(at(15, 15, 34, 59), pre_alerts=pre_alerts(),
			current_prayer_duration_minutes=0).current_prayer)
		self.assertIsNone(self.state(at(15, 15, 35), pre_alerts=pre_alerts(),
			current_prayer_duration_minutes=0).current_prayer)
		self.assertIsNotNone(self.state(at(15, 17, 0), pre_alerts=pre_alerts(),
			current_prayer_duration_minutes=180).current_prayer)
		for invalid in (-1, 181, 20.5, True):
			with self.subTest(invalid=invalid):
				with self.assertRaises((TypeError, ValueError)):
					self.state(at(15, 15, 20), current_prayer_duration_minutes=invalid)

	def test_disabled_iqama_counts_current_duration_from_prayer_entry(self) -> None:
		settings = iqama_with(PrayerEventName.ASR, IqamaRule(0, 0))
		state = self.state(at(15, 15, 34), pre_alerts=pre_alerts(), iqama=settings)
		self.assertEqual(state.current_prayer.ends_at, at(15, 15, 35))
		self.assertIsNone(state.iqama_at)
		self.assertIsNone(self.state(at(15, 15, 35), pre_alerts=pre_alerts(), iqama=settings).current_prayer)

	def test_next_prayer_and_sunrise_are_hard_end_boundaries(self) -> None:
		short = (
			event(PrayerEventName.FAJR, 15, 5), event(PrayerEventName.SUNRISE, 15, 5, 30),
			event(PrayerEventName.DHUHR, 15, 12), event(PrayerEventName.ASR, 15, 12, 10),
		)
		service = PrayerStateService(EventClock(Instant(at(15, 5, 30))))
		state = service.snapshot(short, pre_alerts=pre_alerts(), current_prayer_duration_minutes=180)
		self.assertIsNone(state.current_prayer)
		service = PrayerStateService(EventClock(Instant(at(15, 12, 10))))
		state = service.snapshot(short, pre_alerts=pre_alerts(), current_prayer_duration_minutes=180)
		self.assertEqual(state.current_prayer.event.name, PrayerEventName.ASR)

	def test_time_events_do_not_end_isha_but_next_fajr_does(self) -> None:
		settings = iqama_with(PrayerEventName.ISHA, IqamaRule(240, 5))
		for now in (at(15, 23, 30), at(16, 1, 30)):
			state = self.state(now, pre_alerts=pre_alerts(), iqama=settings,
				current_prayer_duration_minutes=180)
			self.assertEqual(state.current_prayer.event.name, PrayerEventName.ISHA)
		state = self.state(at(16, 5), pre_alerts=pre_alerts(), iqama=settings,
			current_prayer_duration_minutes=180)
		self.assertEqual(state.current_prayer.event.name, PrayerEventName.FAJR)

	def test_waiting_window_boundaries_and_zero(self) -> None:
		settings = pre_alerts(asr=10)
		self.assertIsNone(self.state(at(15, 15, 4), pre_alerts=settings).waiting_window)
		for now in (at(15, 15, 5), at(15, 15, 10), at(15, 15, 14, 59)):
			self.assertEqual(self.state(now, pre_alerts=settings).waiting_window.event.name,
				PrayerEventName.ASR)
		self.assertIsNone(self.state(at(15, 15, 15), pre_alerts=settings).waiting_window)
		self.assertIsNone(self.state(at(15, 15, 10), pre_alerts=pre_alerts()).waiting_window)

	def test_priority_waiting_then_current_then_next_and_preserves_other_fields(self) -> None:
		state = self.state(at(15, 10), pre_alerts=pre_alerts())
		self.assertIs(state.priority, PrayerStatePriority.NEXT_EVENT)
		state = self.state(at(15, 15, 20), pre_alerts=pre_alerts())
		self.assertIs(state.priority, PrayerStatePriority.CURRENT_PRAYER)
		state = self.state(at(15, 15, 10), pre_alerts=pre_alerts(asr=10))
		self.assertIs(state.priority, PrayerStatePriority.WAITING)
		self.assertIsNone(state.current_prayer)
		long_dhuhr = iqama_with(PrayerEventName.DHUHR, IqamaRule(180, 5))
		state = self.state(at(15, 15, 10), pre_alerts=pre_alerts(asr=10), iqama=long_dhuhr,
			current_prayer_duration_minutes=180)
		self.assertIs(state.priority, PrayerStatePriority.WAITING)
		self.assertEqual(state.current_prayer.event.name, PrayerEventName.DHUHR)
		self.assertEqual(state.previous_event.name, PrayerEventName.DHUHR)
		self.assertEqual(state.next_event.name, PrayerEventName.ASR)

	def test_point_event_never_creates_current_time_state(self) -> None:
		state = self.state(at(15, 6, 21), pre_alerts=pre_alerts())
		self.assertIsNone(state.current_prayer)
		self.assertIs(state.priority, PrayerStatePriority.NEXT_EVENT)
		self.assertEqual(state.previous_event.name, PrayerEventName.SUNRISE)
		self.assertIs(state.previous_event.kind, PrayerEventKind.TIME)
		self.assertEqual(state.next_event.name, PrayerEventName.DHUHR)
		self.assertIs(state.next_event.kind, PrayerEventKind.PRAYER)

	def test_previous_and_next_follow_full_dates_through_night_sequence(self) -> None:
		cases = (
			(at(15, 20), PrayerEventName.ISHA, PrayerEventName.MIDNIGHT),
			(at(15, 23, 45), PrayerEventName.MIDNIGHT, PrayerEventName.LAST_THIRD),
			(at(16, 2), PrayerEventName.LAST_THIRD, PrayerEventName.FAJR),
			(at(16, 5, 30), PrayerEventName.FAJR, PrayerEventName.SUNRISE),
		)
		for now, previous, following in cases:
			with self.subTest(now=now):
				state = self.state(now, pre_alerts=pre_alerts())
				self.assertEqual(state.previous_event.name, previous)
				self.assertEqual(state.next_event.name, following)


if __name__ == "__main__":
	unittest.main()
