from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import (  # noqa: E402
	ArabicWordClockFormatter, ClockFormatter, EnglishWordClockFormatter,
	NumericClockFormatter,
)
from awqati.domain import (  # noqa: E402
	AnnouncementStyle, ClockFormatOptions, ClockReading, ClockType, HourSystem,
	TimeRepresentation,
)


def reading(*, hour: int = 15, minute: int = 51, second: int = 44,
		elapsed: timedelta = timedelta(hours=10, minutes=51, seconds=44)) -> ClockReading:
	return ClockReading(
		datetime(2026, 1, 15, hour, minute, second, tzinfo=timezone.utc),
		elapsed,
		datetime(2026, 1, 15, 5, tzinfo=timezone.utc),
	)


def options(**changes) -> ClockFormatOptions:
	values = dict(hour_system=HourSystem.TWELVE, show_seconds=True,
		speak_zero_minute=False, style=AnnouncementStyle.SHORT)
	values.update(changes)
	return ClockFormatOptions(**values)


class ArabicClockFormatterTests(unittest.TestCase):
	def setUp(self) -> None:
		self.words = ArabicWordClockFormatter()
		self.numeric = NumericClockFormatter("ar")

	def test_formatter_protocol_and_neutral_representation_values(self) -> None:
		self.assertIsInstance(self.words, ClockFormatter)
		self.assertIsInstance(self.numeric, ClockFormatter)
		self.assertIs(self.words.representation, TimeRepresentation.WORDS)
		self.assertIs(self.numeric.representation, TimeRepresentation.NUMERIC)

	def test_required_zawali_word_order_puts_period_after_hour(self) -> None:
		self.assertEqual(
			self.words.format_announcement(reading(), ClockType.ZAWALI, options()),
			"الثالثة مساءً وإحدى وخمسون دقيقة وأربع وأربعون ثانية.",
		)
		self.assertEqual(
			self.words.format_announcement(reading(hour=3), ClockType.ZAWALI, options()),
			"الثالثة صباحًا وإحدى وخمسون دقيقة وأربع وأربعون ثانية.",
		)

	def test_required_ghurubi_word_period_follows_hour(self) -> None:
		self.assertEqual(
			self.words.format_announcement(reading(), ClockType.GHURUBI, options()),
			"العاشرة ليلًا وإحدى وخمسون دقيقة وأربع وأربعون ثانية.",
		)
		self.assertEqual(
			self.words.format_announcement(
				reading(elapsed=timedelta(hours=22, minutes=51, seconds=44)),
				ClockType.GHURUBI, options()),
			"العاشرة نهارًا وإحدى وخمسون دقيقة وأربع وأربعون ثانية.",
		)

	def test_required_numeric_ghurubi_is_unambiguous_and_period_is_last(self) -> None:
		first = self.numeric.format_time(
			reading(elapsed=timedelta(hours=11, minutes=12, seconds=14)),
			ClockType.GHURUBI, options())
		second = self.numeric.format_time(
			reading(elapsed=timedelta(hours=22, minutes=53, seconds=43)),
			ClockType.GHURUBI, options())
		self.assertEqual(first, "11 و12 دقيقة و14 ثانية، ليلية")
		self.assertEqual(second, "10 و53 دقيقة و43 ثانية، نهارية")
		self.assertNotIn(":", first)
		self.assertNotIn("صباح", first)
		self.assertNotIn("مساء", first)

	def test_ghurubi_twelve_hour_boundaries(self) -> None:
		cases = (
			(timedelta(0), "الثانية عشرة ليلًا"),
			(timedelta(seconds=1), "الثانية عشرة ليلًا وثانية واحدة"),
			(timedelta(hours=11, minutes=59), "الحادية عشرة ليلًا وتسع وخمسون دقيقة"),
			(timedelta(hours=12), "الثانية عشرة نهارًا"),
			(timedelta(hours=12, minutes=1), "الثانية عشرة نهارًا ودقيقة واحدة"),
			(timedelta(hours=24, minutes=30), "الثانية عشرة نهارًا وثلاثون دقيقة"),
		)
		for elapsed, expected in cases:
			actual = self.words.format_time(reading(elapsed=elapsed), ClockType.GHURUBI,
				options(show_seconds=elapsed.seconds % 60 != 0))
			with self.subTest(elapsed=elapsed):
				self.assertEqual(actual, expected)

	def test_arabic_minute_inflections_are_exact_final_outputs(self) -> None:
		expected = {
			0: "الثالثة مساءً وصفر دقيقة.",
			1: "الثالثة مساءً ودقيقة واحدة.",
			2: "الثالثة مساءً ودقيقتان.",
			3: "الثالثة مساءً وثلاث دقائق.",
			10: "الثالثة مساءً وعشر دقائق.",
			11: "الثالثة مساءً وإحدى عشرة دقيقة.",
			12: "الثالثة مساءً واثنتا عشرة دقيقة.",
			42: "الثالثة مساءً واثنتان وأربعون دقيقة.",
			51: "الثالثة مساءً وإحدى وخمسون دقيقة.",
		}
		for minute, final in expected.items():
			actual = self.words.format_announcement(
				reading(minute=minute, second=0), ClockType.ZAWALI,
				options(show_seconds=False, speak_zero_minute=True))
			with self.subTest(minute=minute):
				self.assertEqual(actual, final)

	def test_arabic_second_inflections_are_exact_final_outputs(self) -> None:
		expected = {
			1: "الثالثة مساءً وثانية واحدة.",
			2: "الثالثة مساءً وثانيتان.",
			3: "الثالثة مساءً وثلاث ثوانٍ.",
			10: "الثالثة مساءً وعشر ثوانٍ.",
			11: "الثالثة مساءً وإحدى عشرة ثانية.",
			12: "الثالثة مساءً واثنتا عشرة ثانية.",
			14: "الثالثة مساءً وأربع عشرة ثانية.",
			43: "الثالثة مساءً وثلاث وأربعون ثانية.",
		}
		for second, final in expected.items():
			actual = self.words.format_announcement(
				reading(minute=0, second=second), ClockType.ZAWALI,
				options(show_seconds=True, speak_zero_minute=False))
			with self.subTest(second=second):
				self.assertEqual(actual, final)

	def test_arabic_eight_forms_are_exact_for_minutes_and_seconds(self) -> None:
		numbers = {
			8: ("ثماني دقائق", "ثماني ثوانٍ"),
			18: ("ثماني عشرة دقيقة", "ثماني عشرة ثانية"),
			28: ("ثمانٍ وعشرون دقيقة", "ثمانٍ وعشرون ثانية"),
			38: ("ثمانٍ وثلاثون دقيقة", "ثمانٍ وثلاثون ثانية"),
			48: ("ثمانٍ وأربعون دقيقة", "ثمانٍ وأربعون ثانية"),
			58: ("ثمانٍ وخمسون دقيقة", "ثمانٍ وخمسون ثانية"),
		}
		for value, (minutes, seconds) in numbers.items():
			minute_output = self.words.format_announcement(
				reading(minute=value, second=0), ClockType.ZAWALI,
				options(show_seconds=False, speak_zero_minute=True),
			)
			second_output = self.words.format_announcement(
				reading(minute=0, second=value), ClockType.ZAWALI,
				options(show_seconds=True, speak_zero_minute=False),
			)
			with self.subTest(value=value, unit="minute"):
				self.assertEqual(minute_output, f"الثالثة مساءً و{minutes}.")
			with self.subTest(value=value, unit="second"):
				self.assertEqual(second_output, f"الثالثة مساءً و{seconds}.")

	def test_seconds_and_zero_minute_are_independent(self) -> None:
		value = reading(hour=16, minute=0, second=5)
		cases = (
			(False, False, "الرابعة مساءً"),
			(False, True, "الرابعة مساءً وصفر دقيقة"),
			(True, False, "الرابعة مساءً وخمس ثوانٍ"),
			(True, True, "الرابعة مساءً وصفر دقيقة وخمس ثوانٍ"),
		)
		for seconds, zero, expected in cases:
			with self.subTest(seconds=seconds, zero=zero):
				self.assertEqual(self.words.format_time(value, ClockType.ZAWALI,
					options(show_seconds=seconds, speak_zero_minute=zero)), expected)

	def test_24_hour_words_and_numeric_elapsed_over_24_do_not_reset(self) -> None:
		self.assertEqual(self.words.format_time(reading(hour=23), ClockType.ZAWALI,
			options(hour_system=HourSystem.TWENTY_FOUR)),
			"الثالثة والعشرون وإحدى وخمسون دقيقة وأربع وأربعون ثانية")
		self.assertEqual(self.numeric.format_time(
			reading(elapsed=timedelta(hours=25, minutes=3, seconds=4)), ClockType.GHURUBI,
			options(hour_system=HourSystem.TWENTY_FOUR)), "25:03:04")

	def test_all_arabic_announcement_styles_and_double_order(self) -> None:
		value = reading(hour=16, minute=42, second=43,
			elapsed=timedelta(hours=11, minutes=12, seconds=14))
		base = dict(hour_system=HourSystem.TWELVE, show_seconds=True, speak_zero_minute=False)
		self.assertEqual(self.numeric.format_announcement(value, ClockType.ZAWALI,
			ClockFormatOptions(style=AnnouncementStyle.FULL, **base)),
			"الساعة الآن هي: 4:42:43 مساءً حسب التوقيت الزوالي.")
		self.assertEqual(self.numeric.format_announcement(value, ClockType.ZAWALI,
			ClockFormatOptions(style=AnnouncementStyle.MODERATE, **base)),
			"الساعة: 4:42:43 مساءً.")
		self.assertEqual(self.numeric.format_announcement(value, ClockType.ZAWALI,
			ClockFormatOptions(style=AnnouncementStyle.SHORT, **base)), "4:42:43 مساءً.")
		double = self.numeric.format_announcement(value, ClockType.ZAWALI,
			ClockFormatOptions(style=AnnouncementStyle.DOUBLE, **base),
			ghurubi_formatter=self.numeric,
			ghurubi_options=ClockFormatOptions(style=AnnouncementStyle.FULL, **base))
		self.assertEqual(double,
			"الساعة الآن هي: 4:42:43 مساءً حسب التوقيت الزوالي، "
			"11 و12 دقيقة و14 ثانية، ليلية حسب التوقيت الغروبي.")
		self.assertLess(double.index("الزوالي"), double.index("الغروبي"))
		self.assertNotIn("الساعة الغروبية:", double)
		self.assertNotIn("الغروبي: 11", double)

	def test_standalone_ghurubi_has_three_styles_and_rejects_double(self) -> None:
		value = reading(elapsed=timedelta(hours=10, minutes=5))
		base = dict(hour_system=HourSystem.TWELVE, show_seconds=False, speak_zero_minute=False)
		expected = {
			AnnouncementStyle.FULL: "الساعة الغروبية: 10 و5 دقائق، ليلية.",
			AnnouncementStyle.MODERATE: "الغروبي: 10 و5 دقائق، ليلية.",
			AnnouncementStyle.SHORT: "10 و5 دقائق، ليلية.",
		}
		for style, final in expected.items():
			self.assertEqual(self.numeric.format_announcement(value, ClockType.GHURUBI,
				ClockFormatOptions(style=style, **base)), final)
		with self.assertRaisesRegex(ValueError, "DOUBLE"):
			self.numeric.format_announcement(value, ClockType.GHURUBI,
				ClockFormatOptions(style=AnnouncementStyle.DOUBLE, **base),
				ghurubi_formatter=self.numeric, ghurubi_options=options())

	def test_numeric_and_words_use_original_hour_for_twelve_hour_period(self) -> None:
		setting = options(hour_system=HourSystem.TWELVE, show_seconds=False, speak_zero_minute=True)
		for hour, minute, expected in (
			(0, 0, "صباحًا"), (0, 30, "صباحًا"), (6, 0, "صباحًا"),
			(11, 59, "صباحًا"), (12, 0, "مساءً"), (12, 30, "مساءً"),
			(18, 0, "مساءً"), (23, 59, "مساءً"),
		):
			with self.subTest(hour=hour, minute=minute):
				value = reading(hour=hour, minute=minute)
				numeric = self.numeric.format_time(value, ClockType.ZAWALI, setting)
				words = self.words.format_time(value, ClockType.ZAWALI, setting)
				self.assertIn(expected, numeric)
				self.assertIn(expected, words)
				self.assertEqual("صباحًا" in numeric, "صباحًا" in words)

class EnglishClockFormatterTests(unittest.TestCase):
	def setUp(self) -> None:
		self.words = EnglishWordClockFormatter()
		self.numeric = NumericClockFormatter("en")

	def test_numeric_and_words_use_original_hour_for_twelve_hour_period(self) -> None:
		setting = options(hour_system=HourSystem.TWELVE, show_seconds=False, speak_zero_minute=True)
		for hour, minute, expected in (
			(0, 0, "AM"), (0, 30, "AM"), (6, 0, "AM"), (11, 59, "AM"),
			(12, 0, "PM"), (12, 30, "PM"), (18, 0, "PM"), (23, 59, "PM"),
		):
			with self.subTest(hour=hour, minute=minute):
				value = reading(hour=hour, minute=minute)
				numeric = self.numeric.format_time(value, ClockType.ZAWALI, setting)
				words = self.words.format_time(value, ClockType.ZAWALI, setting)
				self.assertIn(expected, numeric)
				self.assertIn(expected, words)
				self.assertEqual("AM" in numeric, "AM" in words)
	def test_english_words_and_numeric_are_real_exact_outputs(self) -> None:
		value = reading(hour=15, minute=51, second=44)
		self.assertEqual(self.words.format_announcement(value, ClockType.ZAWALI, options()),
			"three PM and fifty-one minutes and forty-four seconds.")
		self.assertEqual(self.numeric.format_announcement(value, ClockType.ZAWALI, options()),
			"3:51:44 PM.")
		self.assertEqual(self.words.format_time(value, ClockType.ZAWALI,
			options(hour_system=HourSystem.TWENTY_FOUR)),
			"fifteen hours and fifty-one minutes and forty-four seconds")

	def test_24_hour_words_use_singular_and_plural_hours(self) -> None:
		setting = options(hour_system=HourSystem.TWENTY_FOUR, show_seconds=False,
			speak_zero_minute=False)
		self.assertEqual(
			self.words.format_time(reading(hour=1, minute=0), ClockType.ZAWALI, setting),
			"one hour",
		)
		self.assertEqual(
			self.words.format_time(reading(hour=15, minute=0), ClockType.ZAWALI, setting),
			"fifteen hours",
		)
		self.assertEqual(
			self.words.format_time(reading(elapsed=timedelta(hours=1)), ClockType.GHURUBI, setting),
			"one hour",
		)
		self.assertEqual(
			self.words.format_time(reading(elapsed=timedelta(hours=2)), ClockType.GHURUBI, setting),
			"two hours",
		)

	def test_english_ghurubi_periods_never_use_am_or_pm(self) -> None:
		for elapsed, period in ((timedelta(hours=10, minutes=2), "nighttime"),
				(timedelta(hours=12), "daytime"), (timedelta(hours=22, minutes=2), "daytime")):
			word_value = self.words.format_time(reading(elapsed=elapsed), ClockType.GHURUBI,
				options(show_seconds=False))
			numeric_value = self.numeric.format_time(reading(elapsed=elapsed), ClockType.GHURUBI,
				options(show_seconds=False))
			with self.subTest(elapsed=elapsed):
				self.assertIn(period, word_value)
				self.assertIn(period, numeric_value)
				self.assertNotIn(" AM", word_value + numeric_value)
				self.assertNotIn(" PM", word_value + numeric_value)

	def test_english_styles_double_and_independent_options(self) -> None:
		value = reading(hour=16, minute=0, second=5, elapsed=timedelta(hours=13, minutes=2))
		primary = options(style=AnnouncementStyle.DOUBLE, show_seconds=False,
			speak_zero_minute=True)
		ghurubi = options(style=AnnouncementStyle.SHORT, show_seconds=True,
			speak_zero_minute=False)
		actual = self.words.format_announcement(value, ClockType.ZAWALI, primary,
			ghurubi_formatter=self.numeric, ghurubi_options=ghurubi)
		self.assertEqual(actual,
			"The time now is: four PM and zero minutes in Zawali time, "
			"1 hour, 2 minutes, 0 seconds, daytime in Ghurubi time.")
		for style, expected in (
			(AnnouncementStyle.FULL, "Ghurubi time: ten nighttime and two minutes."),
			(AnnouncementStyle.MODERATE, "Ghurubi: ten nighttime and two minutes."),
			(AnnouncementStyle.SHORT, "ten nighttime and two minutes."),
		):
			self.assertEqual(self.words.format_announcement(
				reading(elapsed=timedelta(hours=10, minutes=2)), ClockType.GHURUBI,
				options(style=style, show_seconds=False)), expected)

	def test_numeric_24_hour_zero_minute_with_seconds_is_not_ambiguous(self) -> None:
		value = reading(elapsed=timedelta(hours=25, seconds=5))
		setting = options(hour_system=HourSystem.TWENTY_FOUR, show_seconds=True,
			speak_zero_minute=False)
		self.assertEqual(self.numeric.format_time(value, ClockType.GHURUBI, setting), "25 and 5 seconds")
		arabic = NumericClockFormatter("ar")
		self.assertEqual(arabic.format_time(value, ClockType.GHURUBI, setting), "25 و5 ثوانٍ")

	def test_cross_language_double_is_rejected(self) -> None:
		with self.assertRaisesRegex(ValueError, "same language"):
			self.words.format_announcement(reading(), ClockType.ZAWALI,
				options(style=AnnouncementStyle.DOUBLE),
				ghurubi_formatter=NumericClockFormatter("ar"),
				ghurubi_options=options())


if __name__ == "__main__":
	unittest.main()
