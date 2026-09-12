from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import PrayerService  # noqa: E402
from awqati.domain import (  # noqa: E402
	AsrMethod, CalculationMethod, HighLatitudeRule, PrayerCalculationRequest,
	PrayerEventKind, PrayerEventName, calculate_night_times, complete_prayer_times,
)
from awqati.infrastructure import BundledCalculationMethodRepository, BundledTimezoneProvider  # noqa: E402


class NightCalculationTests(unittest.TestCase):
	def test_half_and_two_thirds_use_maghrib_to_next_fajr_across_civil_midnight(self) -> None:
		maghrib = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)
		next_fajr = datetime(2026, 1, 16, 5, 0, tzinfo=timezone.utc)
		result = calculate_night_times(maghrib, next_fajr)
		self.assertEqual(result.midnight, datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc))
		self.assertEqual(result.last_third_start, datetime(2026, 1, 16, 1, 20, tzinfo=timezone.utc))
		self.assertEqual(result.midnight - maghrib, (next_fajr - maghrib) / 2)
		self.assertEqual(result.last_third_start - maghrib, (next_fajr - maghrib) * 2 / 3)
		self.assertNotEqual(result.midnight, datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc))

	def test_calculation_uses_fajr_not_sunrise(self) -> None:
		maghrib = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)
		fajr_result = calculate_night_times(maghrib, datetime(2026, 1, 16, 5, 0, tzinfo=timezone.utc))
		sunrise_result = calculate_night_times(maghrib, datetime(2026, 1, 16, 6, 30, tzinfo=timezone.utc))
		self.assertNotEqual(fajr_result, sunrise_result)

	def test_naive_or_non_future_inputs_are_rejected(self) -> None:
		aware = datetime(2026, 1, 15, 18, 0, tzinfo=timezone.utc)
		with self.assertRaisesRegex(ValueError, "maghrib"):
			calculate_night_times(datetime(2026, 1, 15, 18, 0), aware)
		with self.assertRaisesRegex(ValueError, "next_fajr"):
			calculate_night_times(aware, datetime(2026, 1, 16, 5, 0))
		with self.assertRaisesRegex(ValueError, "after maghrib"):
			calculate_night_times(aware, aware)

	def test_dst_transition_uses_absolute_elapsed_time(self) -> None:
		zone = BundledTimezoneProvider().get_timezone("America/New_York")
		maghrib = datetime(2026, 10, 31, 18, 0, tzinfo=zone)
		next_fajr = datetime(2026, 11, 1, 5, 0, tzinfo=zone)
		result = calculate_night_times(maghrib, next_fajr)
		start_utc = maghrib.astimezone(timezone.utc)
		end_utc = next_fajr.astimezone(timezone.utc)
		self.assertEqual(result.midnight.astimezone(timezone.utc) - start_utc, (end_utc - start_utc) / 2)
		self.assertEqual(result.last_third_start.astimezone(timezone.utc) - start_utc,
			(end_utc - start_utc) * 2 / 3)

	def test_completed_day_exposes_eight_aware_semantic_events(self) -> None:
		service = PrayerService(BundledCalculationMethodRepository(), BundledTimezoneProvider())
		def request(day: date) -> PrayerCalculationRequest:
			return PrayerCalculationRequest(day, 24.6877, 46.7219, "Asia/Riyadh",
				CalculationMethod.MWL, AsrMethod.STANDARD, HighLatitudeRule.AUTO)
		today = service.calculate(request(date(2026, 1, 15)))
		next_day = service.calculate(request(date(2026, 1, 16)))
		completed = complete_prayer_times(today, next_day.fajr)
		self.assertEqual(len(completed.events), 8)
		self.assertTrue(all(event.occurs_at.tzinfo is not None for event in completed.events))
		kinds = {event.name: event.kind for event in completed.events}
		for name in (PrayerEventName.FAJR, PrayerEventName.DHUHR, PrayerEventName.ASR,
				PrayerEventName.MAGHRIB, PrayerEventName.ISHA):
			self.assertIs(kinds[name], PrayerEventKind.PRAYER)
		for name in (PrayerEventName.SUNRISE, PrayerEventName.MIDNIGHT, PrayerEventName.LAST_THIRD):
			self.assertIs(kinds[name], PrayerEventKind.TIME)
		self.assertLess(completed.maghrib, completed.midnight)
		self.assertLess(completed.midnight, completed.last_third_start)
		self.assertLess(completed.last_third_start, next_day.fajr)


if __name__ == "__main__":
	unittest.main()
