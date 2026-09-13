from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
for path in (PACKAGES, ROOT / "tests"):
	if str(path) not in sys.path:
		sys.path.insert(0, str(path))

from awqati.application import (  # noqa: E402
	ArabianCalendarService,
	ArabicDailyInfoFormatter,
	AstronomyService,
	DailyInfoFormatter,
)
from awqati.domain import DailyInfoReading, Instant, Location, SolarDayState  # noqa: E402
from awqati.infrastructure import (  # noqa: E402
	BundledArabianCalendarRepository,
	BundledTimezoneProvider,
)
from support.event_clock import EventClock  # noqa: E402


RIYADH = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
LONDON = Location("london", "London", 51.5074, -0.1278, "Europe/London")
LONGYEARBYEN = Location("longyearbyen", "Longyearbyen", 78.2232, 15.6469, "Arctic/Longyearbyen")


class RecordingHeritageFormatter:
	def __init__(self) -> None:
		self.detailed_calls = []

	def format_short(self, reading) -> str:
		raise AssertionError("combined daily information must use the detailed heritage formatter")

	def format_detailed(self, reading) -> str:
		self.detailed_calls.append(reading)
		return "HERITAGE-MARKER"


class DailyInfoFormatterTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.timezones = BundledTimezoneProvider()
		cls.formatter = ArabicDailyInfoFormatter()
		cls.scientific = cls._read(datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc), RIYADH)
		cls.heritage = ArabianCalendarService(BundledArabianCalendarRepository()).read_date(
			date(2026, 9, 13),
		)

	@classmethod
	def _read(cls, moment: datetime, location: Location):
		return AstronomyService(EventClock(Instant(moment)), cls.timezones).read(location)

	@classmethod
	def _read_local(cls, local_value: datetime, location: Location):
		zone = cls.timezones.get_timezone(location.timezone_id)
		aware = local_value.replace(tzinfo=zone)
		return cls._read(aware.astimezone(timezone.utc), location)

	def test_implements_daily_info_formatter_contract(self) -> None:
		self.assertIsInstance(self.formatter, DailyInfoFormatter)

	def test_complete_scientific_text_is_natural_and_contains_every_required_fact(self) -> None:
		text = self.formatter.format_scientific(self.scientific)
		for phrase in (
			"المعلومات الفلكية لهذا اليوم:",
			"الفصل الفلكي الحالي هو الصيف",
			"وقد بقي على انتهائه 9 أيام و23 ساعة",
			"ويبدأ الخريف مع الاعتدال الخريفي يوم 23 سبتمبر",
			"بالتوقيت المحلي",
			"طول النهار اليوم",
			"وطول الليل",
			"وقد قصر النهار عن أمس بنحو دقيقة واحدة",
			"شروق الشمس عند الساعة 5 و39 دقيقة صباحًا",
			"وغروبها عند الساعة 6 مساءً",
			"القمر في طور الهلال المتزايد",
			"وعمره التقريبي يومان",
			"وتبلغ نسبة إضاءته 4.2 بالمئة",
			"المحاق القادم يوم 10 أكتوبر",
			"والبدر القادم يوم 26 سبتمبر",
		):
			with self.subTest(phrase=phrase):
				self.assertIn(phrase, text)
		self.assertNotIn("UTC", text)
		self.assertNotIn("0 دقائق", text)

	def test_season_remaining_uses_observation_time_not_midnight(self) -> None:
		morning = self._read(datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc), RIYADH)
		afternoon = self._read(datetime(2026, 9, 13, 12, 30, tzinfo=timezone.utc), RIYADH)
		self.assertEqual((morning.observed_at_local.hour, afternoon.observed_at_local.hour), (3, 15))
		self.assertIn("9 أيام و23 ساعة", self.formatter.format_scientific(morning))
		self.assertIn("9 أيام و11 ساعة", self.formatter.format_scientific(afternoon))

	def test_season_remaining_is_elapsed_time_across_dst(self) -> None:
		reading = self._read_local(datetime(2026, 10, 24, 12), LONDON)
		shifted = replace(
			reading,
			next_seasonal_event_local=reading.observed_at_local + timedelta(days=1),
		)
		# Preserve the same local wall time while crossing the fall-back transition.
		shifted = replace(
			shifted,
			next_seasonal_event_local=shifted.next_seasonal_event_local.replace(fold=1),
		)
		elapsed = (
			shifted.next_seasonal_event_local.astimezone(timezone.utc)
			- shifted.observed_at_local.astimezone(timezone.utc)
		)
		self.assertEqual(elapsed, timedelta(hours=25))
		self.assertIn("يوم واحد وساعة واحدة", self.formatter.format_scientific(shifted))

	def test_increasing_day_uses_natural_longer_phrase(self) -> None:
		reading = self._read_local(datetime(2026, 3, 1, 12), RIYADH)
		self.assertGreater(reading.daylight_change_from_previous_day, timedelta(0))
		self.assertIn("طال النهار عن أمس بنحو", self.formatter.format_scientific(reading))

	def test_decreasing_day_uses_natural_shorter_phrase(self) -> None:
		self.assertLess(self.scientific.daylight_change_from_previous_day, timedelta(0))
		self.assertIn("قصر النهار عن أمس بنحو", self.formatter.format_scientific(self.scientific))

	def test_sub_minute_change_uses_no_zero_or_direction(self) -> None:
		reading = replace(self.scientific, daylight_change_from_previous_day=timedelta(seconds=29))
		text = self.formatter.format_scientific(reading)
		self.assertIn("ولم يتغير طول النهار عن أمس تغيرًا ملحوظًا", text)
		self.assertNotIn("طال النهار", text)
		self.assertNotIn("قصر النهار", text)
		self.assertNotIn("بصفر", text)

	def test_sunrise_and_sunset_use_dst_adjusted_local_times(self) -> None:
		reading = self._read_local(datetime(2026, 4, 1, 12), LONDON)
		assert reading.sunrise_local and reading.sunset_local
		self.assertEqual(reading.sunrise_local.utcoffset(), timedelta(hours=1))
		self.assertEqual(reading.sunset_local.utcoffset(), timedelta(hours=1))
		text = self.formatter.format_scientific(reading)
		self.assertIn("شروق الشمس عند الساعة", text)
		self.assertIn("وغروبها عند الساعة", text)
		self.assertIn("صباحًا", text)
		self.assertIn("مساءً", text)
		self.assertNotIn("UTC", text)

	def test_polar_day_and_night_have_no_invented_event_times(self) -> None:
		for local_value, expected_state, phrase in (
			(datetime(2026, 6, 21, 12), SolarDayState.POLAR_DAY, "تسود حالة اليوم القطبي"),
			(datetime(2026, 12, 21, 12), SolarDayState.POLAR_NIGHT, "تسود حالة الليل القطبي"),
		):
			with self.subTest(expected_state=expected_state):
				reading = self._read_local(local_value, LONGYEARBYEN)
				self.assertEqual(reading.solar_day.state, expected_state)
				text = self.formatter.format_scientific(reading)
				self.assertIn(phrase, text)
				self.assertIn("لا يوجد شروق أو غروب شمسي اعتيادي اليوم", text)
				self.assertNotIn("شروق الشمس عند الساعة", text)
				self.assertNotIn("غروبها عند الساعة", text)

	def test_first_supported_day_omits_unavailable_previous_day_comparison(self) -> None:
		reading = self._read(datetime(1900, 12, 31, 21, tzinfo=timezone.utc), RIYADH)
		self.assertIsNone(reading.daylight_change_from_previous_day)
		text = self.formatter.format_scientific(reading)
		self.assertIn("المعلومات الفلكية لهذا اليوم:", text)
		self.assertNotIn("عن أمس", text)

	def test_daily_reading_without_heritage_has_no_empty_heritage_section(self) -> None:
		text = self.formatter.format(DailyInfoReading(self.scientific, None))
		self.assertNotIn("معلومات التقويم العربي:", text)
		self.assertNotIn("وفي التقويم العربي:", text)

	def test_combined_output_separates_sections_and_reuses_heritage_formatter(self) -> None:
		heritage_formatter = RecordingHeritageFormatter()
		formatter = ArabicDailyInfoFormatter(heritage_formatter)
		text = formatter.format(DailyInfoReading(self.scientific, self.heritage))
		self.assertLess(text.index("المعلومات الفلكية لهذا اليوم:"), text.index("معلومات التقويم العربي:"))
		self.assertIn("\n\nمعلومات التقويم العربي:\nHERITAGE-MARKER", text)
		self.assertEqual(heritage_formatter.detailed_calls, [self.heritage])

	def test_formatting_does_not_change_astronomy_reading(self) -> None:
		before = self.scientific.solar_day.daylight
		self.formatter.format_scientific(self.scientific)
		self.assertEqual(self.scientific.solar_day.daylight, before)


if __name__ == "__main__":
	unittest.main()
