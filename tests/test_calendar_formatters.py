from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import ArabicDateFormatter, CalendarService, EnglishDateFormatter  # noqa: E402
from awqati.domain import (  # noqa: E402
	AfghanSolarHijriProvider, CalendarId, DateFormat, GregorianProvider,
	PersianSolarHijriProvider, PrimaryCalendar, SaudiSolarHijriProvider,
)
from awqati.infrastructure import UmmAlQuraProvider  # noqa: E402


class CalendarFormatterTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.service = CalendarService(object(), object(), (
			GregorianProvider(), UmmAlQuraProvider(), SaudiSolarHijriProvider(),
			PersianSolarHijriProvider(), AfghanSolarHijriProvider(),
		))

	def test_exact_arabic_output_for_every_format_and_calendar(self) -> None:
		expected = {
			CalendarId.GREGORIAN: (
				"اليوم هو: السبت 12 سبتمبر 2026 ميلاديًا، الموافق 1 ربيع الثاني 1448 هجريًا.",
				"اليوم هو: السبت 12 سبتمبر (أيلول) 2026 ميلاديًا.",
				"السبت 12 سبتمبر 2026 ميلاديًا.", "12 سبتمبر."),
			CalendarId.HIJRI_UMM_AL_QURA: (
				"اليوم هو: السبت 1 ربيع الثاني 1448 هجريًا، الموافق 12 سبتمبر 2026 ميلاديًا.",
				"اليوم هو: السبت 1 ربيع الثاني 1448 هجريًا.",
				"السبت 1 ربيع الثاني 1448 هجريًا.", "1 ربيع الثاني."),
			CalendarId.SAUDI_SOLAR_HIJRI: (
				"اليوم هو: السبت 21 السنبلة 1404 هجري شمسي، الموافق 1 ربيع الثاني 1448 هجريًا.",
				"اليوم هو: السبت 21 السنبلة 1404 هجري شمسي.",
				"السبت 21 السنبلة 1404 هجري شمسي.", "21 السنبلة."),
			CalendarId.PERSIAN_SOLAR_HIJRI: (
				"اليوم هو: السبت 21 شهریور 1405 هجري شمسي فارسي، الموافق 1 ربيع الثاني 1448 هجريًا.",
				"اليوم هو: السبت 21 شهریور 1405 هجري شمسي فارسي.",
				"السبت 21 شهریور 1405 هجري شمسي فارسي.", "21 شهریور."),
			CalendarId.AFGHAN_SOLAR_HIJRI: (
				"اليوم هو: السبت 21 سنبلة 1405 هجري شمسي أفغاني، الموافق 1 ربيع الثاني 1448 هجريًا.",
				"اليوم هو: السبت 21 سنبلة 1405 هجري شمسي أفغاني.",
				"السبت 21 سنبلة 1405 هجري شمسي أفغاني.", "21 سنبلة."),
		}
		formatter = ArabicDateFormatter()
		for calendar_id, values in expected.items():
			reading = self.service.read_date(date(2026, 9, 12), calendar_id)
			for style, value in zip(DateFormat, values):
				with self.subTest(calendar=calendar_id, style=style):
					self.assertEqual(formatter.format_calendar(reading, style), value)

	def test_exact_english_output_for_every_format_and_calendar(self) -> None:
		expected = {
			CalendarId.GREGORIAN: (
				"Today is: Saturday, September 12, 2026 CE, corresponding to 1 Rabi al-Thani 1448 AH.",
				"Today is: Saturday, September 12, 2026 CE.",
				"Saturday, September 12, 2026 CE.", "September 12."),
			CalendarId.HIJRI_UMM_AL_QURA: (
				"Today is: Saturday, 1 Rabi al-Thani 1448 AH, corresponding to September 12, 2026 CE.",
				"Today is: Saturday, 1 Rabi al-Thani 1448 AH.",
				"Saturday, 1 Rabi al-Thani 1448 AH.", "1 Rabi al-Thani."),
			CalendarId.SAUDI_SOLAR_HIJRI: (
				"Today is: Saturday, 21 al-Sunbula 1404 Solar AH, corresponding to 1 Rabi al-Thani 1448 AH.",
				"Today is: Saturday, 21 al-Sunbula 1404 Solar AH.",
				"Saturday, 21 al-Sunbula 1404 Solar AH.", "21 al-Sunbula."),
			CalendarId.PERSIAN_SOLAR_HIJRI: (
				"Today is: Saturday, 21 Shahrivar 1405 Persian Solar AH, corresponding to 1 Rabi al-Thani 1448 AH.",
				"Today is: Saturday, 21 Shahrivar 1405 Persian Solar AH.",
				"Saturday, 21 Shahrivar 1405 Persian Solar AH.", "21 Shahrivar."),
			CalendarId.AFGHAN_SOLAR_HIJRI: (
				"Today is: Saturday, 21 Sonbola 1405 Afghan Solar AH, corresponding to 1 Rabi al-Thani 1448 AH.",
				"Today is: Saturday, 21 Sonbola 1405 Afghan Solar AH.",
				"Saturday, 21 Sonbola 1405 Afghan Solar AH.", "21 Sonbola."),
		}
		formatter = EnglishDateFormatter()
		for calendar_id, values in expected.items():
			reading = self.service.read_date(date(2026, 9, 12), calendar_id)
			for style, value in zip(DateFormat, values):
				with self.subTest(calendar=calendar_id, style=style):
					self.assertEqual(formatter.format_calendar(reading, style), value)

	def test_primary_double_direction_and_single_formats(self) -> None:
		reading = self.service.read_date(date(2026, 9, 12), CalendarId.GREGORIAN)
		formatter = ArabicDateFormatter()
		hijri_first = formatter.format_primary(reading, PrimaryCalendar.HIJRI_UMM_AL_QURA)
		gregorian_first = formatter.format_primary(reading, PrimaryCalendar.GREGORIAN)
		self.assertEqual(formatter.format_primary(reading), hijri_first)
		self.assertLess(hijri_first.index("ربيع الثاني"), hijri_first.index("سبتمبر"))
		self.assertLess(gregorian_first.index("سبتمبر"), gregorian_first.index("ربيع الثاني"))
		for style in (DateFormat.FULL, DateFormat.MODERATE, DateFormat.SHORT):
			self.assertNotIn("سبتمبر", formatter.format_primary(
				reading, PrimaryCalendar.HIJRI_UMM_AL_QURA, style))
			self.assertNotIn("ربيع الثاني", formatter.format_primary(
				reading, PrimaryCalendar.GREGORIAN, style))

	def test_lunar_correction_changes_only_double_companion(self) -> None:
		formatter = ArabicDateFormatter()
		base = self.service.read_date(date(2026, 9, 12), CalendarId.SAUDI_SOLAR_HIJRI)
		corrected = self.service.read_date(date(2026, 9, 12), CalendarId.SAUDI_SOLAR_HIJRI,
			hijri_adjustment=-2)
		self.assertIn("21 السنبلة 1404", formatter.format_calendar(corrected, DateFormat.DOUBLE))
		self.assertIn("28 ربيع الأول 1448", formatter.format_calendar(corrected, DateFormat.DOUBLE))
		for style in (DateFormat.FULL, DateFormat.MODERATE, DateFormat.SHORT):
			self.assertEqual(formatter.format_calendar(base, style),
				formatter.format_calendar(corrected, style))


if __name__ == "__main__":
	unittest.main()
