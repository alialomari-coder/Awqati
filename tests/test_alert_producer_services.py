"""Exercise 4.2 with the existing real calculation and clock services."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon/globalPlugins"))
from awqati.application import ClockAlertProducer, ClockService, PrayerAlertProducer, PrayerService
from awqati.domain import (AsrMethod, HighLatitudeRule, CalculationMethod, Instant, Location, LocationKind,
	PrayerCalculationRequest, StoredLocation, complete_prayer_times, default_settings)
from awqati.infrastructure import BundledCalculationMethodRepository, BundledTimezoneProvider


class Clock:
	def __init__(self, value): self.value = value
	def now(self): return self.value


class ProducerServiceTests(unittest.TestCase):
	def setUp(self):
		self.location = Location("riyadh", "Riyadh", 24.6877, 46.7219, "Asia/Riyadh")
		self.zones = BundledTimezoneProvider()
		self.prayers = PrayerService(BundledCalculationMethodRepository(), self.zones)
		self.settings = default_settings()
		self.settings.location = StoredLocation(LocationKind.SELECTED, self.location, "SA")
		self.settings.clock.automatic_alert_enabled = True
		self.now = Clock(Instant(datetime(2026, 1, 15, 0, tzinfo=timezone.utc)))
		self.clock = ClockService(self.now, self.zones, self.prayers, self.request)

	@staticmethod
	def request(day, location):
		return PrayerCalculationRequest(day, location.latitude, location.longitude, location.timezone_id,
			CalculationMethod.MWL, AsrMethod.STANDARD, HighLatitudeRule.AUTO)

	def test_read_at_matches_read_without_moving_clock(self):
		future = Instant(self.now.value.value + timedelta(hours=3))
		reading = self.clock.read_at(self.location, future)
		self.assertEqual(self.now.now().value.hour, 0)
		self.now.value = future
		self.assertEqual(reading, self.clock.read(self.location))

	def test_read_at_preserves_maghrib_boundary(self):
		maghrib = self.prayers.calculate(self.request(date(2026, 1, 15), self.location)).maghrib
		self.assertEqual(self.clock.read_at(self.location, Instant(maghrib)).ghurubi_elapsed, timedelta(0))
		before = Instant(maghrib - timedelta(seconds=1))
		self.assertGreater(self.clock.read_at(self.location, before).ghurubi_elapsed, timedelta(hours=20))

	def test_producer_uses_prepared_real_clock_readings(self):
		start = self.now.now()
		end = Instant(start.value + timedelta(hours=2))
		# Preparing values is deliberately outside the producer's no-I/O boundary.
		zone = self.zones.get_timezone(self.location.timezone_id)
		readings = {start.value + timedelta(hours=hour): self.clock.read_at(
			self.location, Instant(start.value + timedelta(hours=hour))) for hour in range(2)}
		producer = ClockAlertProducer(lambda: self.settings, lambda _: zone, lambda at: readings[at.value])
		events = producer.produce(start, end)
		self.assertEqual(len(events), 2)
		for event in events:
			self.assertEqual(event.metadata["reading"], self.clock.read_at(self.location, event.scheduled_at))

	def test_existing_complete_timeline_feeds_prayer_producer(self):
		day = date(2026, 1, 15)
		today = self.prayers.calculate(self.request(day, self.location))
		next_day = self.prayers.calculate(self.request(day + timedelta(days=1), self.location))
		timeline = complete_prayer_times(today, next_day.fajr)
		producer = PrayerAlertProducer(lambda: self.settings, lambda *_: timeline.events)
		start = Instant(today.fajr - timedelta(minutes=10))
		end = Instant(next_day.fajr)
		events = producer.produce(start, end)
		self.assertEqual(len(events), 22)  # 8 before + 8 at + 5 Iqama + sunrise after.
		self.assertEqual({event.metadata["event_name"] for event in events}, {event.name.value for event in timeline.events})


if __name__ == "__main__":
	unittest.main()
