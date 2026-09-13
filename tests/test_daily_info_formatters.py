from __future__ import annotations

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
	ArabicDailyInfoFormatter,
	AstronomyService,
	DailyInfoFormatter,
)
from awqati.domain import DailyInfoReading, Instant, Location  # noqa: E402
from awqati.infrastructure import (  # noqa: E402
	BundledArabianCalendarRepository,
	BundledTimezoneProvider,
)
from awqati.application import ArabianCalendarService  # noqa: E402
from support.event_clock import EventClock  # noqa: E402


LOCATION = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")


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
		clock = EventClock(Instant(datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc)))
		cls.scientific = AstronomyService(clock, BundledTimezoneProvider()).read(LOCATION)
		cls.heritage = ArabianCalendarService(BundledArabianCalendarRepository()).read_date(
			date(2026, 9, 13),
		)

	def test_implements_daily_info_formatter_contract(self) -> None:
		self.assertIsInstance(ArabicDailyInfoFormatter(), DailyInfoFormatter)

	def test_scientific_only_contains_every_required_astronomy_item(self) -> None:
		text = ArabicDailyInfoFormatter().format_scientific(self.scientific)
		for label in (
			"المعلومات الفلكية العلمية:",
			"الفصل الفلكي الحالي:",
			"الاعتدال أو الانقلاب القادم:",
			"بالتوقيت المحلي",
			"طول النهار:",
			"طول الليل:",
			"طور القمر:",
			"عمر القمر التقريبي:",
			"نسبة الإضاءة:",
			"المحاق القادم:",
			"البدر القادم:",
		):
			with self.subTest(label=label):
				self.assertIn(label, text)

	def test_daily_reading_without_heritage_has_no_empty_heritage_section(self) -> None:
		text = ArabicDailyInfoFormatter().format(DailyInfoReading(self.scientific, None))
		self.assertIn("المعلومات الفلكية العلمية:", text)
		self.assertNotIn("معلومات التقويم العربي:", text)
		self.assertNotIn("وفي التقويم العربي:", text)

	def test_combined_output_separates_sections_and_reuses_heritage_formatter(self) -> None:
		heritage_formatter = RecordingHeritageFormatter()
		formatter = ArabicDailyInfoFormatter(heritage_formatter)
		text = formatter.format(DailyInfoReading(self.scientific, self.heritage))
		self.assertLess(text.index("المعلومات الفلكية العلمية:"), text.index("معلومات التقويم العربي:"))
		self.assertIn("\n\nمعلومات التقويم العربي:\nHERITAGE-MARKER", text)
		self.assertEqual(heritage_formatter.detailed_calls, [self.heritage])

	def test_duration_rounding_does_not_change_astronomy_reading(self) -> None:
		before = self.scientific.solar_day.daylight
		ArabicDailyInfoFormatter().format_scientific(self.scientific)
		self.assertEqual(self.scientific.solar_day.daylight, before)
		self.assertIsInstance(before, timedelta)


if __name__ == "__main__":
	unittest.main()
