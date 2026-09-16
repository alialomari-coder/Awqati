from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))
if str(ROOT / ".build-deps") not in sys.path:
	sys.path.insert(0, str(ROOT / ".build-deps"))

from awqati.application import PrayerStatePriority  # noqa: E402
from awqati.domain import Instant, PrayerEventName  # noqa: E402
from awqati.nvda_adapter.commands import CommandContent  # noqa: E402
from awqati.nvda_adapter.duration_formatter import format_minutes  # noqa: E402
from tests.test_corrective_followup import Translator  # noqa: E402


class PrayerStateDurationFormatterTests(unittest.TestCase):
	ARABIC = {
		0: "0 دقيقة", 1: "دقيقة", 2: "دقيقتان", 3: "3 دقائق", 10: "10 دقائق",
		11: "11 دقيقة", 26: "26 دقيقة", 59: "59 دقيقة", 60: "ساعة",
		61: "ساعة ودقيقة", 62: "ساعة ودقيقتان", 119: "ساعة و59 دقيقة",
		120: "ساعتان", 121: "ساعتان ودقيقة", 122: "ساعتان ودقيقتان",
		136: "ساعتان و16 دقيقة", 180: "3 ساعات", 181: "3 ساعات ودقيقة",
		182: "3 ساعات ودقيقتان", 190: "3 ساعات و10 دقائق",
	}

	def test_all_required_arabic_boundaries(self) -> None:
		translate = Translator("ar")
		for minutes, expected in self.ARABIC.items():
			with self.subTest(minutes=minutes):
				self.assertEqual(expected, format_minutes(minutes, translate))
				self.assertNotIn("0 دقيقة", format_minutes(minutes, translate) if minutes else "")

	def test_all_required_english_boundaries(self) -> None:
		translate = Translator("en")
		for minutes in self.ARABIC:
			hours, remainder = divmod(minutes, 60)
			parts = []
			if hours:
				parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
			if remainder or not parts:
				parts.append(f"{remainder} minute{'s' if remainder != 1 else ''}")
			with self.subTest(minutes=minutes):
				self.assertEqual(" ".join(parts), format_minutes(minutes, translate))

	def test_rejects_non_integer_negative_and_boolean_values(self) -> None:
		for value in (-1, 1.5, True):
			with self.subTest(value=value), self.assertRaises(ValueError):
				format_minutes(value, Translator("en"))


class PrayerStateDurationIntegrationTests(unittest.TestCase):
	@staticmethod
	def event(name, hour, minute, kind="prayer"):
		return SimpleNamespace(
			name=name, kind=SimpleNamespace(value=kind),
			occurs_at=datetime(2026, 9, 16, hour, minute, tzinfo=timezone.utc),
		)

	def content(self, state):
		content = object.__new__(CommandContent)
		content._state = lambda: state
		return content

	def base_state(self):
		return SimpleNamespace(
			as_of=Instant(datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)),
			priority=SimpleNamespace(),
			next_event=self.event(PrayerEventName.DHUHR, 11, 26),
			previous_event=self.event(PrayerEventName.SUNRISE, 7, 44, "time"),
		)

	def test_next_and_previous_use_hours_and_minutes_without_changing_difference(self) -> None:
		content = self.content(self.base_state())
		self.assertEqual("الصلاة القادمة هي الظهر عند 11:26؛ بقي عليها ساعة و26 دقيقة.", content.current_details(Translator("ar")))
		self.assertEqual("الوقت السابق كان الشروق عند 07:44؛ قبل ساعتين و16 دقيقة.", content.previous_details(Translator("ar")))
		self.assertEqual("The next prayer is Dhuhr at 11:26; in 1 hour 26 minutes.", content.current_details(Translator("en")))
		self.assertEqual("The previous time was Sunrise at 07:44; 2 hours 16 minutes ago.", content.previous_details(Translator("en")))

	def test_waiting_and_current_prayer_use_the_same_duration_formatter(self) -> None:
		waiting_event = self.event(PrayerEventName.DHUHR, 10, 26)
		waiting = self.base_state()
		waiting.priority = PrayerStatePriority.WAITING
		waiting.waiting_window = SimpleNamespace(event=waiting_event)
		current_event = self.event(PrayerEventName.FAJR, 8, 58)
		current = self.base_state()
		current.priority = PrayerStatePriority.CURRENT_PRAYER
		current.current_prayer = SimpleNamespace(event=current_event)
		self.assertEqual("في انتظار الظهر؛ بقي 26 دقيقة.", self.content(waiting).current_details(Translator("ar")))
		self.assertEqual("Waiting for Dhuhr; 26 minutes remain.", self.content(waiting).current_details(Translator("en")))
		self.assertEqual("الصلاة الحالية هي الفجر؛ بدأت قبل ساعة ودقيقتين.", self.content(current).current_details(Translator("ar")))
		self.assertEqual("The current prayer is Fajr; it began 1 hour 2 minutes ago.", self.content(current).current_details(Translator("en")))

	def test_exact_acceptance_examples_for_next_time_and_previous_prayer(self) -> None:
		next_time = self.base_state()
		next_time.as_of = Instant(datetime(2026, 9, 16, 21, 28, tzinfo=timezone.utc))
		next_time.next_event = self.event(PrayerEventName.MIDNIGHT, 22, 54, "time")
		previous_prayer = self.base_state()
		previous_prayer.as_of = Instant(datetime(2026, 9, 16, 21, 29, tzinfo=timezone.utc))
		previous_prayer.previous_event = self.event(PrayerEventName.ISHA, 19, 13)
		self.assertEqual(
			"الوقت القادم هو منتصف الليل عند 22:54؛ بقي عليه ساعة و26 دقيقة.",
			self.content(next_time).current_details(Translator("ar")),
		)
		self.assertEqual(
			"الصلاة السابقة كانت العشاء عند 19:13؛ قبل ساعتين و16 دقيقة.",
			self.content(previous_prayer).previous_details(Translator("ar")),
		)
		self.assertEqual(
			"The next time is Midnight at 22:54; in 1 hour 26 minutes.",
			self.content(next_time).current_details(Translator("en")),
		)
		self.assertEqual(
			"The previous prayer was Isha at 19:13; 2 hours 16 minutes ago.",
			self.content(previous_prayer).previous_details(Translator("en")),
		)


if __name__ == "__main__":
	unittest.main()