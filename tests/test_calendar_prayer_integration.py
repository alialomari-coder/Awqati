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
from awqati.domain import (  # noqa: E402
	AsrMethod, CalculationMethod, CalendarOutOfRangeError, HighLatitudeRule,
	PrayerCalculationRequest,
)
from awqati.infrastructure import (  # noqa: E402
	BundledCalculationMethodRepository, BundledTimezoneProvider, UmmAlQuraProvider,
)


class CalendarPrayerIntegrationTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.service = PrayerService(BundledCalculationMethodRepository(),
			BundledTimezoneProvider(), lunar_calendar=UmmAlQuraProvider())

	def request(self, local_date: date) -> PrayerCalculationRequest:
		return PrayerCalculationRequest(local_date, 24.6877, 46.7219, "Asia/Riyadh",
			CalculationMethod.MAKKAH, AsrMethod.STANDARD, HighLatitudeRule.AUTO,
			is_ramadan=None)

	def test_makkah_context_is_supplied_from_umm_al_qura_only_in_application(self) -> None:
		ramadan = self.service.calculate(self.request(date(2026, 2, 18)))
		outside = self.service.calculate(self.request(date(2026, 3, 20)))
		self.assertTrue(ramadan.metadata.is_ramadan)
		self.assertFalse(outside.metadata.is_ramadan)
		self.assertEqual(ramadan.isha - ramadan.maghrib, timedelta(minutes=120))
		self.assertEqual(outside.isha - outside.maghrib, timedelta(minutes=90))

	def test_out_of_range_context_never_guesses_ramadan(self) -> None:
		with self.assertRaises(CalendarOutOfRangeError):
			self.service.calculate(self.request(date(1882, 11, 11)))


if __name__ == "__main__":
	unittest.main()
