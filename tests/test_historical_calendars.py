"""Focused contract tests, independent numeric anchors, and bounded properties."""
from datetime import date
from itertools import permutations
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.domain.historical_calendars import (  # noqa: E402
	ConversionResult, ErrorCode, HistoricalCalendar as C, HistoricalCalendarError,
	HistoricalDate as D, MAX_RD, METHOD, MIN_RD, convert, from_rd,
	is_leap_year, month_length, to_rd,
)

# Wustenfeld 1854 / Mahler scan: printed pages 2,4,6,IV,17,28,36.
# Dates after 1582 in that table are Gregorian; earlier dates are Julian.
# Day 12 in 365 and day 4 in 656 are derived from the printed month starts.
# Tuple order is always (year, month, day); no event-date claims are made.
REFERENCES = (
	((1, 1, 1), (622, 7, 19), (622, 7, 16)),
	((16, 1, 1), (637, 2, 5), (637, 2, 2)),
	((61, 1, 1), (680, 10, 4), (680, 10, 1)),
	((132, 1, 1), (749, 8, 24), (749, 8, 20)),
	((151, 9, 1), (768, 9, 22), (768, 9, 18)),
	((365, 9, 1), (976, 5, 8), (976, 5, 3)),
	((365, 9, 12), (976, 5, 19), (976, 5, 14)),
	((656, 2, 1), (1258, 2, 14), (1258, 2, 7)),
	((656, 2, 4), (1258, 2, 17), (1258, 2, 10)),
	((857, 5, 1), (1453, 5, 19), (1453, 5, 10)),
	((897, 3, 1), (1492, 1, 11), (1492, 1, 2)),
	((1270, 3, 11), (1853, 12, 12), (1853, 11, 30)),
)


def fields(value):
	return value.year, value.month, value.day


class HistoricalCalendarTests(unittest.TestCase):
	def assert_error(self, code, function, *args, **kwargs):
		with self.assertRaises(HistoricalCalendarError) as caught:
			function(*args, **kwargs)
		self.assertEqual(caught.exception.code, code)
		self.assertIsInstance(caught.exception.field, str)

	def test_reference_anchors_all_six_directions(self):
		for h, g, j in REFERENCES:
			values = dict(zip((C.HIJRI_IIC, C.GREGORIAN, C.JULIAN), (h, g, j)))
			for source, target in permutations(C, 2):
				with self.subTest(h=h, source=source, target=target):
					year, month, day = values[source]
					result = convert(source, target, year=year, month=month, day=day)
					self.assertEqual(fields(result.target), values[target])

	def test_exact_day_limits_all_calendars(self):
		for calendar, lower, upper in (
			(C.HIJRI_IIC, (1, 1, 1), (9666, 4, 2)),
			(C.GREGORIAN, (622, 7, 19), (9999, 12, 31)),
			(C.JULIAN, (622, 7, 16), (9999, 10, 19)),
		):
			self.assertEqual(fields(from_rd(MIN_RD, calendar)), lower)
			self.assertEqual(fields(from_rd(MAX_RD, calendar)), upper)
			self.assertEqual(to_rd(D(calendar, *lower)), MIN_RD)
			self.assertEqual(to_rd(D(calendar, *upper)), MAX_RD)
		for calendar, invalid in (
			(C.HIJRI_IIC, (9666, 4, 3)), (C.HIJRI_IIC, (9666, 12, 1)),
			(C.GREGORIAN, (622, 7, 18)), (C.GREGORIAN, (10000, 1, 1)),
			(C.JULIAN, (622, 7, 15)), (C.JULIAN, (9999, 10, 20)),
		):
			self.assert_error(ErrorCode.OUT_OF_RANGE, D, calendar, *invalid)
		for calendar in C:
			for rd in (MIN_RD - 1, MAX_RD + 1):
				self.assert_error(ErrorCode.OUT_OF_RANGE, from_rd, rd, calendar)

	def test_hijri_cycle_and_year_15_16(self):
		expected = {2, 5, 7, 10, 13, 16, 18, 21, 24, 26, 29}
		for cycle in (0, 1, 100, 300):
			self.assertEqual({y for y in range(1, 31) if is_leap_year(C.HIJRI_IIC, y + 30 * cycle)}, expected)
		self.assertEqual(to_rd(D(C.HIJRI_IIC, 31, 1, 1)) - MIN_RD, 10631)
		self.assert_error(ErrorCode.INVALID_DAY, D, C.HIJRI_IIC, 15, 12, 30)
		self.assertEqual(to_rd(D(C.HIJRI_IIC, 17, 1, 1)) - to_rd(D(C.HIJRI_IIC, 16, 12, 30)), 1)

	def test_complete_hijri_cycle_against_day_count(self):
		# Independent enumeration of specified months/leap-year list, not the RD formula.
		rd = MIN_RD
		for year in range(1, 31):
			for month in range(1, 13):
				length = 30 if month % 2 or (month == 12 and year in METHOD.leap_years) else 29
				for day in range(1, length + 1):
					value = D(C.HIJRI_IIC, year, month, day)
					self.assertEqual(to_rd(value), rd)
					self.assertEqual(from_rd(rd, C.HIJRI_IIC), value)
					rd += 1
		self.assertEqual(rd - MIN_RD, 10631)

	def test_gregorian_and_julian_century_rules(self):
		for year in (1600, 1700, 1800, 1900, 2000, 2100, 2400):
			self.assertTrue(is_leap_year(C.JULIAN, year))
			self.assertEqual(is_leap_year(C.GREGORIAN, year), year % 400 == 0)
			D(C.JULIAN, year, 2, 29)
			if year % 400:
				self.assert_error(ErrorCode.INVALID_DAY, D, C.GREGORIAN, year, 2, 29)
			else:
				D(C.GREGORIAN, year, 2, 29)

	def test_month_boundaries_distributed_across_centuries(self):
		for calendar in C:
			maximum = 9600 if calendar is C.HIJRI_IIC else 9900
			for year in range(700, maximum + 1, 100):
				for month in range(1, 13):
					first = D(calendar, year, month, 1)
					last = D(calendar, year, month, month_length(calendar, year, month))
					self.assertEqual(from_rd(to_rd(first), calendar), first)
					self.assertEqual(from_rd(to_rd(last), calendar), last)
					next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
					self.assertEqual(from_rd(to_rd(last) + 1, calendar), D(calendar, next_year, next_month, 1))

	def test_six_way_roundtrips_distributed_days(self):
		for rd in (MIN_RD, MIN_RD + 1, MAX_RD - 1, MAX_RD, *range(MIN_RD, MAX_RD, 7919)):
			values = {c: from_rd(rd, c) for c in C}
			for source, target in permutations(C, 2):
				year, month, day = fields(values[source])
				result = convert(source, target, year=year, month=month, day=day)
				self.assertEqual(result.target, values[target])
				year, month, day = fields(result.target)
				self.assertEqual(convert(target, source, year=year, month=month, day=day).target, values[source])

	def test_no_1582_gap(self):
		for calendar in (C.GREGORIAN, C.JULIAN):
			for day in range(1, 32):
				self.assertEqual(fields(from_rd(to_rd(D(calendar, 1582, 10, day)), calendar)), (1582, 10, day))
		self.assertEqual(to_rd(D(C.JULIAN, 1582, 10, 4)), date(1582, 10, 14).toordinal())

	def test_invalid_components(self):
		for calendar in C:
			for year in (0, -1):
				self.assert_error(ErrorCode.INVALID_YEAR, D, calendar, year, 1, 1)
			for month in (0, 13, -1):
				self.assert_error(ErrorCode.INVALID_MONTH, D, calendar, 2000, month, 1)
			for day in (0, -1, 32):
				self.assert_error(ErrorCode.INVALID_DAY, D, calendar, 2000, 1, day)
		self.assert_error(ErrorCode.INVALID_DAY, D, C.HIJRI_IIC, 1448, 2, 30)
		self.assert_error(ErrorCode.INVALID_DAY, D, C.GREGORIAN, 2026, 4, 31)
		self.assert_error(ErrorCode.OUT_OF_RANGE, D, C.HIJRI_IIC, 10 ** 100, 1, 1)

	def test_strict_types_including_digit_strings(self):
		for calendar in C:
			for invalid in (True, False, 1.0, 1.5, "2026", "٢٠٢٦", "۲۰۲۶", "abc", None, [], {}):
				for field in range(3):
					args = [2000, 1, 1]
					args[field] = invalid
					self.assert_error(ErrorCode.INVALID_TYPE, D, calendar, *args)
		for invalid in (True, 1.5, "227015", None):
			self.assert_error(ErrorCode.INVALID_TYPE, from_rd, invalid, C.HIJRI_IIC)
		self.assert_error(ErrorCode.INVALID_TYPE, to_rd, date(2026, 1, 1))

	def test_unknown_calendar_is_structured_error(self):
		for invalid in ("HIJRI_UMM_AL_QURA", "HIJRI_TABULAR_IIC", None, [], True):
			self.assert_error(ErrorCode.UNSUPPORTED_CALENDAR, convert, invalid, C.GREGORIAN, year=2026, month=1, day=1)
			self.assert_error(ErrorCode.UNSUPPORTED_CALENDAR, convert, C.GREGORIAN, invalid, year=2026, month=1, day=1)

	def test_result_identity_and_metadata(self):
		for calendar in C:
			v = from_rd(MIN_RD, calendar)
			r = convert(calendar, calendar, year=v.year, month=v.month, day=v.day)
			self.assertIsInstance(r, ConversionResult)
			self.assertEqual(r.source, r.target)
			self.assertEqual(r.method.identifier, "islamic-civil-IIc-v1")
			self.assertTrue(r.early_islamic_proleptic)
		self.assertFalse(convert(C.GREGORIAN, C.HIJRI_IIC, year=2026, month=1, day=1).early_islamic_proleptic)

	def test_known_local_dates_are_not_forced_to_match(self):
		# Differences documented in the study, not a reason to change IIc.
		r = convert(C.HIJRI_IIC, C.JULIAN, year=367, month=10, day=29)
		self.assertEqual(fields(r.target), (978, 6, 9))  # observed eclipse June 8 J
		r = convert(C.HIJRI_IIC, C.GREGORIAN, year=1448, month=4, day=1)
		self.assertEqual(fields(r.target), (2026, 9, 14))  # current Umm al-Qura Sept 12

	def test_standalone_import_blocks_all_external_dependencies(self):
		# Load just this file with only standard-library imports permitted. Existing
		# package __init__ exports unrelated services, so use importlib in isolation.
		code = '''
import builtins, importlib.util, pathlib, sys
allowed = {'dataclasses', 'datetime', 'enum'}
original = builtins.__import__
def restricted(name, *args, **kwargs):
    if name.split('.')[0] not in allowed:
        raise AssertionError('Unexpected engine dependency: ' + name)
    return original(name, *args, **kwargs)
import dataclasses, datetime, enum
spec = importlib.util.spec_from_file_location('isolated_history', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
compiled = compile(pathlib.Path(sys.argv[1]).read_bytes(), sys.argv[1], 'exec')
builtins.__import__ = restricted
exec(compiled, module.__dict__)
c = module.HistoricalCalendar
assert module.convert(c.HIJRI_IIC, c.GREGORIAN, year=365, month=9, day=12).target.day == 19
'''
		r = subprocess.run([sys.executable, "-B", "-c", code,
			str(ROOT / "addon/globalPlugins/awqati/domain/historical_calendars.py")], capture_output=True, text=True)
		self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
	unittest.main()
