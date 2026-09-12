from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import locale
import sys
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
for path in (PACKAGES, ROOT / "tests"):
	if str(path) not in sys.path:
		sys.path.insert(0, str(path))

from awqati.application import ClockService  # noqa: E402
from awqati.domain import (  # noqa: E402
	AsrMethod, CalculationMethod, HighLatitudeRule, Instant, Location,
	PrayerCalculationRequest,
)
from awqati.application import PrayerService  # noqa: E402
from awqati.infrastructure import (  # noqa: E402
	BundledCalculationMethodRepository, BundledTimezoneProvider,
)
from support.event_clock import EventClock  # noqa: E402


RIYADH = Location("riyadh", "Riyadh", 24.6877, 46.7219, "Asia/Riyadh")
LONDON = Location("london", "London", 51.5074, -0.1278, "Europe/London")


class FakePrayerService:
	def __init__(self, maghribs: dict[tuple[str, date], datetime]) -> None:
		self.maghribs = maghribs
		self.requests: list[PrayerCalculationRequest] = []

	def calculate(self, request: PrayerCalculationRequest):
		self.requests.append(request)
		key = (request.timezone_id, request.local_date)
		return SimpleNamespace(maghrib=self.maghribs[key])


def request_for(day: date, location: Location) -> PrayerCalculationRequest:
	return PrayerCalculationRequest(
		day, location.latitude, location.longitude, location.timezone_id,
		CalculationMethod.MWL, AsrMethod.STANDARD, HighLatitudeRule.AUTO,
	)


class ClockServiceTests(unittest.TestCase):
	def service(self, now: datetime, maghribs: dict[tuple[str, date], datetime]):
		prayers = FakePrayerService(maghribs)
		service = ClockService(
			EventClock(Instant(now)), BundledTimezoneProvider(), prayers, request_for,
		)
		return service, prayers

	def test_before_maghrib_uses_yesterday_and_boundaries_are_exact(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("Asia/Riyadh")
		day = date(2026, 1, 15)
		maghribs = {
			("Asia/Riyadh", day - timedelta(days=1)): datetime(2026, 1, 14, 17, 25, tzinfo=zone),
			("Asia/Riyadh", day): datetime(2026, 1, 15, 17, 26, tzinfo=zone),
		}
		for now, expected, calls in (
			(datetime(2026, 1, 15, 17, 25, 59, tzinfo=zone), timedelta(days=1, seconds=59), 2),
			(datetime(2026, 1, 15, 17, 26, tzinfo=zone), timedelta(0), 1),
			(datetime(2026, 1, 15, 17, 26, 1, tzinfo=zone), timedelta(seconds=1), 1),
			(datetime(2026, 1, 15, 17, 31, tzinfo=zone), timedelta(minutes=5), 1),
		):
			service, prayers = self.service(now, maghribs)
			reading = service.read(RIYADH)
			with self.subTest(now=now):
				self.assertEqual(reading.ghurubi_elapsed, expected)
				self.assertEqual(len(prayers.requests), calls)

	def test_zawali_uses_location_timezone_not_host_timezone(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("Asia/Riyadh")
		day = date(2026, 1, 15)
		service, _ = self.service(datetime(2026, 1, 15, 12, tzinfo=timezone.utc), {
			("Asia/Riyadh", day - timedelta(days=1)): datetime(2026, 1, 14, 17, 25, tzinfo=zone),
			("Asia/Riyadh", day): datetime(2026, 1, 15, 17, 26, tzinfo=zone),
		})
		with (
			mock.patch.object(time, "localtime", side_effect=AssertionError("host timezone consulted")),
			mock.patch.object(locale, "getlocale", side_effect=AssertionError("locale consulted")),
		):
			reading = service.read(RIYADH)
		self.assertEqual(reading.zawali, datetime(2026, 1, 15, 15, tzinfo=zone))

	def test_spring_forward_uses_real_elapsed_time(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("Europe/London")
		day = date(2026, 3, 29)
		service, _ = self.service(datetime(2026, 3, 29, 2, tzinfo=timezone.utc), {
			("Europe/London", day - timedelta(days=1)): datetime(2026, 3, 28, 18, tzinfo=zone),
			("Europe/London", day): datetime(2026, 3, 29, 19, tzinfo=zone),
		})
		reading = service.read(LONDON)
		self.assertEqual(reading.zawali.hour, 3)
		self.assertEqual(reading.ghurubi_elapsed, timedelta(hours=8))
		self.assertNotEqual(reading.ghurubi_elapsed, reading.zawali.replace(tzinfo=None) - datetime(2026, 3, 28, 18))

	def test_fall_back_repeated_wall_time_still_advances_one_real_hour(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("Europe/London")
		day = date(2026, 10, 25)
		maghribs = {
			("Europe/London", day - timedelta(days=1)): datetime(2026, 10, 24, 18, tzinfo=zone),
			("Europe/London", day): datetime(2026, 10, 25, 17, tzinfo=zone),
		}
		first, _ = self.service(datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc), maghribs)
		second, _ = self.service(datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc), maghribs)
		first_reading = first.read(LONDON)
		second_reading = second.read(LONDON)
		self.assertEqual((first_reading.zawali.hour, first_reading.zawali.minute), (1, 30))
		self.assertEqual((second_reading.zawali.hour, second_reading.zawali.minute), (1, 30))
		self.assertEqual(second_reading.ghurubi_elapsed - first_reading.ghurubi_elapsed, timedelta(hours=1))

	def test_elapsed_time_is_not_reset_modulo_24_before_next_maghrib(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("Europe/London")
		day = date(2026, 10, 25)
		service, _ = self.service(datetime(2026, 10, 25, 1, 15, tzinfo=timezone.utc), {
			("Europe/London", day - timedelta(days=1)): datetime(2026, 10, 24, 1, tzinfo=zone),
			("Europe/London", day): datetime(2026, 10, 25, 1, 30, fold=1, tzinfo=zone),
		})
		self.assertEqual(service.read(LONDON).ghurubi_elapsed, timedelta(hours=25, minutes=15))

	def test_each_location_read_uses_its_own_timezone_and_maghrib(self) -> None:
		timezones = BundledTimezoneProvider()
		riyadh_zone = timezones.get_timezone("Asia/Riyadh")
		london_zone = timezones.get_timezone("Europe/London")
		day = date(2026, 1, 15)
		maghribs = {
			("Asia/Riyadh", day): datetime(2026, 1, 15, 17, tzinfo=riyadh_zone),
			("Europe/London", day): datetime(2026, 1, 15, 16, tzinfo=london_zone),
		}
		service, prayers = self.service(datetime(2026, 1, 15, 17, tzinfo=timezone.utc), maghribs)
		riyadh = service.read(RIYADH)
		london = service.read(LONDON)
		self.assertEqual(riyadh.ghurubi_elapsed, timedelta(hours=3))
		self.assertEqual(london.ghurubi_elapsed, timedelta(hours=1))
		self.assertEqual([item.timezone_id for item in prayers.requests], ["Asia/Riyadh", "Europe/London"])

	def test_request_factory_must_preserve_date_and_effective_location(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("Asia/Riyadh")
		day = date(2026, 1, 15)
		prayers = FakePrayerService({("Asia/Riyadh", day): datetime(2026, 1, 15, 17, tzinfo=zone)})
		clock = EventClock(Instant(datetime(2026, 1, 15, 18, tzinfo=zone)))
		bad_date = lambda _, location: request_for(day - timedelta(days=1), location)
		with self.assertRaisesRegex(ValueError, "date"):
			ClockService(clock, BundledTimezoneProvider(), prayers, bad_date).read(RIYADH)
		bad_location = lambda requested_day, _: request_for(requested_day, LONDON)
		with self.assertRaisesRegex(ValueError, "location"):
			ClockService(clock, BundledTimezoneProvider(), prayers, bad_location).read(RIYADH)

	def test_naive_maghrib_is_rejected(self) -> None:
		day = date(2026, 1, 15)
		service, _ = self.service(datetime(2026, 1, 15, 18, tzinfo=timezone.utc), {
			("Asia/Riyadh", day): datetime(2026, 1, 15, 17),
		})
		with self.assertRaisesRegex(ValueError, "naive Maghrib"):
			service.read(RIYADH)

	def test_real_prayer_service_supplies_the_maghrib_reference(self) -> None:
		timezones = BundledTimezoneProvider()
		zone = timezones.get_timezone("Asia/Riyadh")
		service = ClockService(
			EventClock(Instant(datetime(2026, 1, 15, 17, 26, tzinfo=zone))),
			timezones,
			PrayerService(BundledCalculationMethodRepository(), timezones),
			request_for,
		)
		result = service.read(RIYADH)
		self.assertEqual(result.maghrib_reference, datetime(2026, 1, 15, 17, 26, tzinfo=zone))
		self.assertEqual(result.ghurubi_elapsed, timedelta(0))


if __name__ == "__main__":
	unittest.main()
