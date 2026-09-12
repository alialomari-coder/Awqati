from __future__ import annotations

from datetime import date, timedelta, timezone
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import PrayerService  # noqa: E402
from awqati.domain import (  # noqa: E402
	AsrMethod, CalculationMethod, CalculationMethodDefinition, HighLatitudeRule,
	MAX_USER_CORRECTION_MINUTES, MIN_USER_CORRECTION_MINUTES,
	PrayerCalculationRequest, PrayerCalculator, PrayerCorrections, PrayerName,
	RamadanContextRequired, SUNRISE_SUNSET_ANGLE,
)
from awqati.infrastructure import BundledCalculationMethodRepository, BundledTimezoneProvider  # noqa: E402


class PrayerCalculatorTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.methods = BundledCalculationMethodRepository()
		cls.service = PrayerService(cls.methods, BundledTimezoneProvider())

	def request(self, **changes) -> PrayerCalculationRequest:
		values = dict(local_date=date(2026, 1, 15), latitude=24.6877, longitude=46.7219,
			timezone_id="Asia/Riyadh", calculation_method=CalculationMethod.MAKKAH,
			asr_method=AsrMethod.STANDARD, high_latitude_rule=HighLatitudeRule.AUTO,
			is_ramadan=False)
		values.update(changes)
		return PrayerCalculationRequest(**values)

	def test_six_results_are_aware_ordered_and_use_the_fixed_horizon_angle(self) -> None:
		result = self.service.calculate(self.request())
		self.assertEqual(SUNRISE_SUNSET_ANGLE, 0.833)
		values = [getattr(result, prayer.value) for prayer in PrayerName]
		self.assertTrue(all(value.tzinfo is not None and value.utcoffset() == timedelta(hours=3) for value in values))
		self.assertLess(result.fajr, result.sunrise)
		self.assertLess(result.sunrise, result.dhuhr)
		self.assertLess(result.dhuhr, result.asr)
		self.assertLess(result.asr, result.maghrib)
		self.assertLess(result.maghrib, result.isha)

	def test_standard_and_hanafi_use_shadow_factors_not_fixed_offsets(self) -> None:
		differences = []
		for latitude, longitude in ((24.6877, 46.7219), (40.7128, -74.006)):
			standard = self.service.calculate(self.request(latitude=latitude, longitude=longitude,
				timezone_id="Etc/UTC", calculation_method=CalculationMethod.MWL,
				asr_method=AsrMethod.STANDARD, is_ramadan=None)).asr
			hanafi = self.service.calculate(self.request(latitude=latitude, longitude=longitude,
				timezone_id="Etc/UTC", calculation_method=CalculationMethod.MWL,
				asr_method=AsrMethod.HANAFI, is_ramadan=None)).asr
			self.assertGreater(hanafi, standard)
			differences.append(hanafi - standard)
		self.assertNotEqual(differences[0], differences[1])

	def test_makkah_requires_explicit_context_and_uses_90_or_120_minutes(self) -> None:
		auto_sa = dict(calculation_method=CalculationMethod.AUTO, country_code="SA")
		with self.assertRaises(RamadanContextRequired):
			self.service.calculate(self.request(is_ramadan=None, **auto_sa))
		regular = self.service.calculate(self.request(is_ramadan=False, **auto_sa))
		ramadan = self.service.calculate(self.request(is_ramadan=True, **auto_sa))
		self.assertEqual(regular.isha - regular.maghrib, timedelta(minutes=90))
		self.assertEqual(ramadan.isha - ramadan.maghrib, timedelta(minutes=120))
		self.assertEqual((regular.metadata.isha_interval_minutes, ramadan.metadata.isha_interval_minutes), (90, 120))
		self.assertEqual(regular.metadata.requested_method, CalculationMethod.AUTO)
		self.assertEqual(regular.metadata.effective_method, CalculationMethod.MAKKAH)
		self.service.calculate(self.request(calculation_method=CalculationMethod.MWL, is_ramadan=None))

	def test_portugal_and_jordan_offsets_are_method_metadata_not_user_tuning(self) -> None:
		portugal = self.service.calculate(self.request(calculation_method=CalculationMethod.PORTUGAL,
			latitude=38.7223, longitude=-9.1393, timezone_id="Europe/Lisbon", is_ramadan=None))
		jordan = self.service.calculate(self.request(calculation_method=CalculationMethod.JORDAN,
			latitude=31.9539, longitude=35.9106, timezone_id="Asia/Amman", is_ramadan=None))
		self.assertEqual(portugal.metadata.method_offsets_minutes["maghrib"], 3)
		self.assertEqual(portugal.metadata.isha_interval_minutes, 77)
		self.assertEqual(portugal.isha - portugal.maghrib, timedelta(minutes=77))
		self.assertEqual(jordan.metadata.method_offsets_minutes["maghrib"], 5)
		self.assertTrue(all(value == 0 for value in portugal.metadata.user_corrections_minutes.values()))

	def test_user_corrections_are_independent_last_step_and_visible(self) -> None:
		base = self.service.calculate(self.request(calculation_method=CalculationMethod.MWL, is_ramadan=None))
		corrections = PrayerCorrections(fajr=2, sunrise=-1, dhuhr=3, asr=-2, maghrib=4, isha=-3)
		adjusted = self.service.calculate(self.request(calculation_method=CalculationMethod.MWL,
			is_ramadan=None, corrections=corrections))
		for prayer in PrayerName:
			self.assertEqual(getattr(adjusted, prayer.value) - getattr(base, prayer.value),
				timedelta(minutes=getattr(corrections, prayer.value)))
		self.assertEqual(dict(adjusted.metadata.user_corrections_minutes), dict(corrections.as_mapping()))
		with self.assertRaises(TypeError): PrayerCorrections(fajr=1.5)  # type: ignore[arg-type]

	def test_user_correction_boundaries_are_inclusive_and_outside_values_are_rejected(self) -> None:
		self.assertEqual((MIN_USER_CORRECTION_MINUTES, MAX_USER_CORRECTION_MINUTES), (-30, 30))
		for value in (-30, 0, 30):
			with self.subTest(valid=value):
				self.assertEqual(PrayerCorrections(fajr=value).fajr, value)
		for value in (-31, 31):
			with self.subTest(invalid=value):
				with self.assertRaisesRegex(ValueError, "between -30 and 30"):
					PrayerCorrections(fajr=value)

	def test_auto_resolution_requires_country_and_falls_back_to_mwl(self) -> None:
		with self.assertRaises(ValueError): self.request(calculation_method=CalculationMethod.AUTO)
		result = self.service.calculate(self.request(calculation_method=CalculationMethod.AUTO,
			country_code="GB", is_ramadan=None))
		self.assertEqual(result.metadata.requested_method, CalculationMethod.AUTO)
		self.assertEqual(result.metadata.effective_method, CalculationMethod.MWL)

	def test_no_network_config_nvda_or_system_clock_is_consulted(self) -> None:
		with mock.patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
			result = self.service.calculate(self.request())
		self.assertEqual(result.fajr.date(), date(2026, 1, 15))
		self.assertNotIn("config", sys.modules)
		self.assertNotIn("globalPluginHandler", sys.modules)

	def test_high_latitude_missing_twilight_combinations_and_rules(self) -> None:
		calculator = PrayerCalculator()
		zone = timezone.utc
		for fajr, isha, expected_missing in ((18, 6, "fajr"), (6, 18, "isha"), (18, 18, "both")):
			definition = CalculationMethodDefinition(CalculationMethod.MWL, "fixture", fajr, isha_angle=isha)
			request = PrayerCalculationRequest(date(2026, 7, 15), 59.9139, 10.7522, "Etc/UTC",
				CalculationMethod.MWL, AsrMethod.STANDARD, HighLatitudeRule.AUTO)
			result = calculator.calculate(request, definition, zone, effective_method=CalculationMethod.MWL)
			with self.subTest(expected_missing=expected_missing):
				self.assertTrue(result.metadata.angle_based_used)
				self.assertEqual(result.metadata.effective_high_latitude_rule, HighLatitudeRule.ANGLE_BASED)
		for rule in (HighLatitudeRule.ANGLE_BASED, HighLatitudeRule.ONE_SEVENTH, HighLatitudeRule.NIGHT_MIDDLE):
			result = self.service.calculate(self.request(local_date=date(2026, 7, 15), latitude=59.9139,
				longitude=10.7522, timezone_id="Europe/Oslo", calculation_method=CalculationMethod.MWL,
				high_latitude_rule=rule, is_ramadan=None))
			self.assertEqual(result.metadata.effective_high_latitude_rule, rule)

	def test_polar_fallback_uses_signed_48_5_and_preserves_other_inputs(self) -> None:
		for latitude, expected in ((78.2232, 48.5), (-77.8419, -48.5)):
			request = self.request(local_date=date(2026, 6, 21), latitude=latitude, longitude=15.6469,
				timezone_id="Etc/UTC", calculation_method=CalculationMethod.MWL, is_ramadan=None)
			result = self.service.calculate(request)
			with self.subTest(latitude=latitude):
				self.assertTrue(result.metadata.high_latitude_fallback_used)
				self.assertEqual(result.metadata.fallback_latitude, expected)
				self.assertEqual(result.metadata.effective_high_latitude_rule, HighLatitudeRule.NEAREST_LATITUDE)
				self.assertEqual(result.metadata.timezone_id, request.timezone_id)
				direct = self.service.calculate(self.request(local_date=request.local_date, latitude=expected,
					longitude=request.longitude, timezone_id=request.timezone_id,
					calculation_method=CalculationMethod.MWL, high_latitude_rule=HighLatitudeRule.AUTO,
					is_ramadan=None))
				self.assertEqual(tuple(getattr(result, name.value) for name in PrayerName),
					tuple(getattr(direct, name.value) for name in PrayerName))


if __name__ == "__main__":
	unittest.main()
