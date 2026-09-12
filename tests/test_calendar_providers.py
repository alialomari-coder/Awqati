from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.domain import (  # noqa: E402
	AfghanSolarHijriProvider,
	CalendarDate,
	CalendarId,
	CalendarOutOfRangeError,
	GregorianProvider,
	PersianSolarHijriProvider,
	SaudiSolarHijriProvider,
)
from awqati.infrastructure import UmmAlQuraProvider  # noqa: E402


class CalendarIdentityTests(unittest.TestCase):
	def test_five_stable_identities_exist(self) -> None:
		self.assertEqual([item.value for item in CalendarId], [
			"GREGORIAN", "HIJRI_UMM_AL_QURA", "SAUDI_SOLAR_HIJRI",
			"PERSIAN_SOLAR_HIJRI", "AFGHAN_SOLAR_HIJRI",
		])
		providers = [GregorianProvider(), UmmAlQuraProvider(), SaudiSolarHijriProvider(),
			PersianSolarHijriProvider(), AfghanSolarHijriProvider()]
		self.assertEqual([provider.calendar_id for provider in providers], list(CalendarId))


class GregorianProviderTests(unittest.TestCase):
	def test_round_trips_leap_month_year_and_year_end(self) -> None:
		provider = GregorianProvider()
		for value in (date(2024, 2, 29), date(2026, 1, 31), date(2026, 12, 31)):
			self.assertEqual(provider.to_gregorian(provider.from_gregorian(value)), value)


class UmmAlQuraProviderTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.provider = UmmAlQuraProvider()

	def test_reference_samples_month_and_year_boundaries(self) -> None:
		samples = {
			date(1882, 11, 12): (1300, 1, 1),
			date(2026, 9, 10): (1448, 3, 28),
			date(2026, 9, 11): (1448, 3, 29),
			date(2026, 9, 12): (1448, 4, 1),
			date(2174, 11, 25): (1600, 12, 30),
		}
		for civil, expected in samples.items():
			with self.subTest(civil=civil):
				converted = self.provider.from_gregorian(civil)
				self.assertEqual((converted.year, converted.month, converted.day), expected)
				self.assertEqual(self.provider.to_gregorian(converted), civil)

	def test_data_boundaries_reject_without_fallback(self) -> None:
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.from_gregorian(date(1882, 11, 11))
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.from_gregorian(date(2174, 11, 26))
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.to_gregorian(CalendarDate(1299, 12, 29, self.provider.calendar_id))
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.to_gregorian(CalendarDate(1601, 1, 1, self.provider.calendar_id))

	def test_adjustment_crosses_month_and_year_without_mutating_base(self) -> None:
		base = self.provider.from_gregorian(date(2026, 9, 12))
		self.assertEqual((base.year, base.month, base.day), (1448, 4, 1))
		self.assertEqual((self.provider.add_days(base, -2).month,
			self.provider.add_days(base, -2).day), (3, 28))
		last = CalendarDate(1447, 12, self.provider.month_length(1447, 12), self.provider.calendar_id)
		self.assertEqual(self.provider.add_days(last, 1), CalendarDate(1448, 1, 1, self.provider.calendar_id))
		self.assertEqual(base, self.provider.from_gregorian(date(2026, 9, 12)))


class SaudiSolarHijriProviderTests(unittest.TestCase):
	def setUp(self) -> None:
		self.provider = SaudiSolarHijriProvider()

	def test_reference_september_boundary_and_round_trip(self) -> None:
		samples = {
			date(2026, 9, 10): (1404, 12, 19),
			date(2026, 9, 22): (1404, 12, 31),
			date(2026, 9, 23): (1405, 1, 1),
		}
		for civil, expected in samples.items():
			converted = self.provider.from_gregorian(civil)
			self.assertEqual((converted.year, converted.month, converted.day), expected)
			self.assertEqual(self.provider.to_gregorian(converted), civil)

	def test_hut_uses_its_own_corresponding_gregorian_leap_rule(self) -> None:
		self.assertEqual(self.provider.saudi_solar_hijri_algorithm_version,
			"awqati-saudi-solar-1-mizan-23-september-v1")
		self.assertTrue(self.provider.is_leap_year(1402))   # contains February 2024
		self.assertFalse(self.provider.is_leap_year(1403))  # contains February 2025
		self.assertEqual(self.provider.month_length(1402, 6), 30)
		self.assertEqual(self.provider.month_length(1403, 6), 29)
		self.assertEqual(self.provider.month_length(1403, 7), 31)
		for year in (1402, 1403):
			for month in range(1, 13):
				first = CalendarDate(year, month, 1, self.provider.calendar_id)
				last = CalendarDate(year, month, self.provider.month_length(year, month), self.provider.calendar_id)
				self.assertEqual(self.provider.from_gregorian(self.provider.to_gregorian(first)), first)
				self.assertEqual(self.provider.from_gregorian(self.provider.to_gregorian(last)), last)
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.from_gregorian(date.min)


class PersianSolarHijriProviderTests(unittest.TestCase):
	def setUp(self) -> None:
		self.provider = PersianSolarHijriProvider()

	def test_icu_78_3_reference_starts_and_esfand(self) -> None:
		self.assertEqual(self.provider.persian_solar_hijri_algorithm_version,
			"icu-78.3-persian-33-year-1304-1468")
		samples = {
			date(2020, 3, 20): (1399, 1, 1),
			date(2021, 3, 20): (1399, 12, 30),
			date(2021, 3, 21): (1400, 1, 1),
			date(2025, 3, 21): (1404, 1, 1),
		}
		for civil, expected in samples.items():
			converted = self.provider.from_gregorian(civil)
			self.assertEqual((converted.year, converted.month, converted.day), expected)
			self.assertEqual(self.provider.to_gregorian(converted), civil)
		self.assertTrue(self.provider.is_leap_year(1399))
		self.assertFalse(self.provider.is_leap_year(1400))

	def test_both_documented_boundaries_and_both_outsides(self) -> None:
		minimum = CalendarDate(1304, 1, 1, self.provider.calendar_id)
		maximum = CalendarDate(1468, 12, 29, self.provider.calendar_id)
		self.assertEqual(self.provider.from_gregorian(self.provider.to_gregorian(minimum)), minimum)
		self.assertEqual(self.provider.from_gregorian(self.provider.to_gregorian(maximum)), maximum)
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.to_gregorian(CalendarDate(1303, 12, 29, self.provider.calendar_id))
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.to_gregorian(CalendarDate(1469, 1, 1, self.provider.calendar_id))
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.from_gregorian(date(1925, 3, 20))
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.from_gregorian(date(2090, 3, 20))


class AfghanSolarHijriProviderTests(unittest.TestCase):
	def setUp(self) -> None:
		self.provider = AfghanSolarHijriProvider()

	def test_undp_anchor_and_leap_rule(self) -> None:
		self.assertEqual(self.provider.afghan_solar_hijri_algorithm_version,
			"undp-unicode-2003-afghanistan-x-plus-621-anchor-1382-v1")
		anchor = self.provider.from_gregorian(date(2003, 3, 21))
		self.assertEqual(anchor, CalendarDate(1382, 1, 1, self.provider.calendar_id))
		self.assertTrue(self.provider.is_leap_year(1383))
		self.assertFalse(self.provider.is_leap_year(1382))
		self.assertEqual(self.provider.month_length(1383, 12), 30)
		self.assertEqual(self.provider.month_length(1382, 12), 29)
		self.assertEqual(self.provider.from_gregorian(date(2004, 3, 20)),
			CalendarDate(1383, 1, 1, self.provider.calendar_id))
		self.assertEqual(self.provider.from_gregorian(date(2005, 3, 20)),
			CalendarDate(1383, 12, 30, self.provider.calendar_id))
		self.assertEqual(self.provider.from_gregorian(date(2005, 3, 21)),
			CalendarDate(1384, 1, 1, self.provider.calendar_id))
		for value in (date(2003, 3, 21), date(2004, 3, 20), date(2005, 3, 20)):
			self.assertEqual(self.provider.to_gregorian(self.provider.from_gregorian(value)), value)

	def test_datetime_limits_are_explicit(self) -> None:
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.from_gregorian(date.min)
		with self.assertRaises(CalendarOutOfRangeError):
			self.provider.to_gregorian(CalendarDate(9999, 1, 1, self.provider.calendar_id))


class PersianAfghanIndependenceTests(unittest.TestCase):
	def test_primary_source_rules_produce_the_documented_one_day_difference(self) -> None:
		# ICU 78.3 starts Persian 1408 on 2029-03-20. UNDP makes Afghan
		# 1407 leap because 2028 is Gregorian leap, so that day is 30 Hoot.
		civil = date(2029, 3, 20)
		persian = PersianSolarHijriProvider().from_gregorian(civil)
		afghan = AfghanSolarHijriProvider().from_gregorian(civil)
		self.assertEqual(persian, CalendarDate(1408, 1, 1, CalendarId.PERSIAN_SOLAR_HIJRI))
		self.assertEqual(afghan, CalendarDate(1407, 12, 30, CalendarId.AFGHAN_SOLAR_HIJRI))
		self.assertNotEqual(type(PersianSolarHijriProvider()), type(AfghanSolarHijriProvider()))


if __name__ == "__main__":
	unittest.main()
