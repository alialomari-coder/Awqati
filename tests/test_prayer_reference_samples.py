from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import PrayerService  # noqa: E402
from awqati.domain import AsrMethod, CalculationMethod, HighLatitudeRule, PrayerCalculationRequest, PrayerName  # noqa: E402
from awqati.infrastructure import BundledCalculationMethodRepository, BundledTimezoneProvider  # noqa: E402


# Deterministic PrayTimes-formula snapshots. They mean calculated according to the
# named method, not literal copies of a ministry or mosque timetable.
SAMPLES = (
	("Riyadh", 24.6877, 46.7219, "Asia/Riyadh", "SA", date(2026, 1, 15), False,
		("05:17", "06:39", "12:02", "15:05", "17:26", "18:56"), "MAKKAH"),
	("Makkah", 21.4225, 39.8262, "Asia/Riyadh", "SA", date(2026, 1, 15), False,
		("05:41", "07:01", "12:30", "15:38", "17:59", "19:29"), "MAKKAH"),
	("Dammam", 26.4344, 50.1033, "Asia/Riyadh", "SA", date(2026, 1, 15), False,
		("05:06", "06:29", "11:49", "14:49", "17:09", "18:39"), "MAKKAH"),
	("Cairo", 30.0444, 31.2357, "Africa/Cairo", "EG", date(2026, 1, 15), None,
		("05:21", "06:52", "12:04", "14:58", "17:17", "18:39"), "EGYPT"),
	("Istanbul", 41.0082, 28.9784, "Europe/Istanbul", "TR", date(2026, 1, 15), None,
		("06:50", "08:27", "13:13", "15:41", "18:00", "19:32"), "TURKEY"),
	("London winter", 51.5074, -0.1278, "Europe/London", "GB", date(2026, 1, 15), None,
		("05:59", "07:59", "12:10", "14:01", "16:21", "18:15"), "MWL"),
	("London summer", 51.5074, -0.1278, "Europe/London", "GB", date(2026, 7, 15), None,
		("02:40", "05:01", "13:07", "17:25", "21:11", "00:49"), "MWL"),
	("Oslo winter", 59.9139, 10.7522, "Europe/Oslo", "NO", date(2026, 1, 15), None,
		("06:28", "09:04", "12:26", "13:35", "15:49", "18:18"), "MWL"),
	("Oslo summer", 59.9139, 10.7522, "Europe/Oslo", "NO", date(2026, 7, 15), None,
		("02:34", "04:21", "13:23", "17:57", "22:23", "00:05"), "MWL"),
	("Jakarta", -6.2088, 106.8456, "Asia/Jakarta", "ID", date(2026, 1, 15), None,
		("04:25", "05:49", "12:02", "15:27", "18:15", "19:30"), "KEMENAG"),
	("Kuala Lumpur", 3.139, 101.6869, "Asia/Kuala_Lumpur", "MY", date(2026, 1, 15), None,
		("06:01", "07:24", "13:23", "16:46", "19:21", "20:35"), "JAKIM"),
	("New York", 40.7128, -74.006, "America/New_York", "US", date(2026, 1, 15), None,
		("05:58", "07:18", "12:06", "14:34", "16:53", "18:14"), "ISNA"),
	("Toronto", 43.6532, -79.3832, "America/Toronto", "CA", date(2026, 1, 15), None,
		("06:23", "07:48", "12:27", "14:47", "17:06", "18:31"), "ISNA"),
)


class PrayerReferenceSamplesTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.service = PrayerService(BundledCalculationMethodRepository(), BundledTimezoneProvider())

	def test_required_saudi_and_global_samples(self) -> None:
		for name, lat, lon, zone, country, day, ramadan, expected, method in SAMPLES:
			request = PrayerCalculationRequest(day, lat, lon, zone,
				CalculationMethod.AUTO, AsrMethod.STANDARD, HighLatitudeRule.AUTO,
				country_code=country, is_ramadan=ramadan)
			result = self.service.calculate(request)
			actual = tuple(getattr(result, prayer.value).strftime("%H:%M") for prayer in PrayerName)
			with self.subTest(name=name):
				self.assertEqual(actual, expected)
				self.assertEqual(request.calculation_method, CalculationMethod.AUTO)
				self.assertEqual(result.metadata.requested_method, CalculationMethod.AUTO)
				self.assertEqual(result.metadata.effective_method.value, method)

	def test_london_and_oslo_apply_dst_from_iana_data(self) -> None:
		provider = BundledTimezoneProvider()
		for key in ("Europe/London", "Europe/Oslo"):
			zone = provider.get_timezone(key)
			winter = __import__("datetime").datetime(2026, 1, 15, 12, tzinfo=zone).utcoffset()
			summer = __import__("datetime").datetime(2026, 7, 15, 12, tzinfo=zone).utcoffset()
			self.assertEqual(summer - winter, timedelta(hours=1))


if __name__ == "__main__":
	unittest.main()
