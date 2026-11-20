"""Task-2 service acceptance checks, using the real unadjusted provider."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.application.historical_conversion import (
	ConversionCalendar as C, HijriMethod as M, HistoricalConversionService,
)
from awqati.domain.calendar import CalendarDate, CalendarId
from awqati.domain.settings import CalendarSettings
from awqati.infrastructure.ummalqura_provider import UmmAlQuraProvider


class ConversionServiceTests(unittest.TestCase):
	def setUp(self):
		self.provider = UmmAlQuraProvider()
		self.service = HistoricalConversionService(self.provider)

	def convert(self, source=C.HIJRI, target=C.GREGORIAN, y=1448, m=4, d=1, method=M.UMM_AL_QURA):
		return self.service.convert(source, target, year=y, month=m, day=d, hijri_method=method)

	def assert_date(self, result, expected):
		self.assertTrue(result.successful, result.error)
		self.assertEqual((result.converted.year, result.converted.month, result.converted.day), expected)

	def test_distinct_known_references(self):
		u = self.convert()
		h = self.convert(method=M.IIC)
		self.assert_date(u, (2026, 9, 12))
		self.assert_date(h, (2026, 9, 14))
		self.assertNotEqual(u.rd, h.rd)
		self.assertEqual(u.reference.version, self.provider.hijri_data_version)
		self.assertEqual(u.reference.table_sha256, self.provider.metadata["tableFileSha256"])
		self.assertEqual(h.reference.identifier, "islamic-civil-IIc-v1")

	def test_all_ten_directions_and_identity_roundtrip(self):
		for method in M:
			for civil in (C.GREGORIAN, C.JULIAN):
				forward = self.convert(target=civil, method=method)
				self.assertTrue(forward.successful)
				v = forward.converted
				back = self.convert(civil, C.HIJRI, v.year, v.month, v.day, method)
				self.assert_date(back, (1448, 4, 1))
				self.assertEqual(back.reference, forward.reference)
				self.assertEqual(back.rd, forward.rd)
				self.assertIs(back.original.calendar, civil)
			self.assert_date(self.convert(target=C.HIJRI, method=method), (1448, 4, 1))
		for source, target in ((C.GREGORIAN, C.JULIAN), (C.JULIAN, C.GREGORIAN)):
			a = self.convert(source, target, 1582, 10, 10, None)
			b = self.convert(target, source, a.converted.year, a.converted.month, a.converted.day, None)
			self.assert_date(b, (1582, 10, 10))
			self.assertIsNone(a.hijri_method)
			self.assertIsNone(a.reference)

	def test_direct_provider_daily_full_table_both_civil_calendars(self):
		first = self.provider.first_supported_gregorian_date
		last = self.provider.last_supported_gregorian_date
		for offset in range((last - first).days + 1):
			civil = first + timedelta(days=offset)
			h = self.provider.from_gregorian(civil)
			result = self.convert(y=h.year, m=h.month, d=h.day)
			self.assert_date(result, (civil.year, civil.month, civil.day))
			self.assertEqual(result.rd, self.provider.to_gregorian(h).toordinal())
			j = self.convert(target=C.JULIAN, y=h.year, m=h.month, d=h.day)
			for value in (result.converted, j.converted):
				back = self.convert(value.calendar, C.HIJRI, value.year, value.month, value.day)
				self.assert_date(back, (h.year, h.month, h.day))

	def test_ummalqura_closed_boundaries_and_immediate_neighbors(self):
		for civil in (self.provider.first_supported_gregorian_date, self.provider.last_supported_gregorian_date):
			h = self.provider.from_gregorian(civil)
			self.assert_date(self.convert(y=h.year, m=h.month, d=h.day), (civil.year, civil.month, civil.day))
		for civil in (self.provider.first_supported_gregorian_date - timedelta(days=1),
				self.provider.last_supported_gregorian_date + timedelta(days=1)):
			r = self.convert(C.GREGORIAN, C.HIJRI, civil.year, civil.month, civil.day)
			self.assertEqual(r.error.code, "ummalqura_out_of_range")
			self.assertEqual(r.error.stage, "target")
			self.assertIsNotNone(r.error.bounds)
			j = self.convert(C.GREGORIAN, C.JULIAN, civil.year, civil.month, civil.day, None).converted
			self.assertEqual(self.convert(C.JULIAN, C.HIJRI, j.year, j.month, j.day).error.code,
				"ummalqura_out_of_range")
		for y, m, d in ((1299, 12, 29), (1601, 1, 1)):
			r = self.convert(y=y, m=m, d=d)
			self.assertEqual(r.error.code, "ummalqura_out_of_range")
			self.assertEqual(r.error.stage, "source")
			self.assertIsNotNone(r.error.bounds)
			self.assertIsNone(r.converted)

	def test_no_provider_needed_or_touched_for_iic_and_civil(self):
		class Forbidden:
			def __getattribute__(self, name):
				raise AssertionError("must not touch Umm al-Qura")
		for service in (HistoricalConversionService(), HistoricalConversionService(Forbidden())):
			r = service.convert(C.HIJRI, C.GREGORIAN, year=365, month=9, day=12, hijri_method=M.IIC)
			self.assert_date(r, (976, 5, 19))
			r = service.convert(C.GREGORIAN, C.JULIAN, year=976, month=5, day=19)
			self.assert_date(r, (976, 5, 14))
		self.assertEqual(HistoricalConversionService().convert(C.HIJRI, C.GREGORIAN,
			year=1448, month=4, day=1, hijri_method=M.UMM_AL_QURA).error.code, "ummalqura_provider_required")

	def test_clean_process_civil_import_never_loads_provider_or_ui(self):
		code = """
import sys
from awqati.application.historical_conversion import HistoricalConversionService, ConversionCalendar as C
r = HistoricalConversionService().convert(C.GREGORIAN, C.JULIAN, year=2026, month=9, day=12)
assert r.successful
assert 'awqati.infrastructure.ummalqura_provider' not in sys.modules
assert 'wx' not in sys.modules and 'globalPluginHandler' not in sys.modules
"""
		result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
		self.assertEqual(result.returncode, 0, result.stderr)

	def test_user_settings_corrections_cannot_affect_either_direction(self):
		from awqati.application.calendar_service import CalendarService
		from awqati.domain.calendar import GregorianProvider
		display = CalendarService(None, None, (GregorianProvider(), self.provider))
		baseline = {}
		visible = set()
		for correction in range(-2, 3):
			settings = CalendarSettings(hijri_adjustment_days=correction)
			reading = display.read_date(date(2026, 9, 12), CalendarId.HIJRI_UMM_AL_QURA,
				hijri_adjustment=settings.hijri_adjustment_days)
			visible.add(reading.lunar_visible.day)
			with patch.object(CalendarService, "read_date", side_effect=AssertionError("display forbidden")), \
				patch.object(self.provider, "add_days", side_effect=AssertionError("adjustment forbidden")):
				for method in M:
					for civil in (C.GREGORIAN, C.JULIAN):
						r = self.convert(target=civil, method=method)
						v = r.converted
						back = self.convert(civil, C.HIJRI, v.year, v.month, v.day, method)
						key = (method, civil)
						baseline.setdefault(key, (r, back))
						self.assertEqual((r, back), baseline[key])
		self.assertEqual(len(visible), 5)

	def test_injected_updated_real_table_is_used_in_both_directions(self):
		# A synthetic update in a temporary directory, never a production table edit.
		data = ROOT / "addon/globalPlugins/awqati/data/calendars/ummalqura"
		with tempfile.TemporaryDirectory() as directory:
			from awqati.infrastructure.network_services import active_data_path
			user_root = Path(directory)
			root = user_root / "data/ummalqura/current"
			shutil.copytree(data, root, dirs_exist_ok=True)
			meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
			table = json.loads((root / meta["tableFile"]).read_text(encoding="utf-8"))
			for document in (meta, table):
				document["hijriDataVersion"] = "synthetic-active-task2"
			# Move the whole table by one day to detect accidental default selection.
			table["firstGregorianDate"] = "1882-11-13"
			meta["firstGregorianDate"] = table["firstGregorianDate"]
			payload = json.dumps(table).encode("utf-8")
			(root / meta["tableFile"]).write_bytes(payload)
			meta["tableFileSha256"] = hashlib.sha256(payload).hexdigest()
			(root / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
			selected = active_data_path(data.parents[1], user_root, "ummalqura")
			self.assertEqual(selected, root)
			provider = UmmAlQuraProvider(selected)
			service = HistoricalConversionService(provider)
			a = service.convert(C.HIJRI, C.GREGORIAN, year=1448, month=4, day=1, hijri_method=M.UMM_AL_QURA)
			self.assert_date(a, (2026, 9, 13))
			self.assertEqual(a.reference.version, "synthetic-active-task2")
			self.assertEqual(a.reference.table_sha256, meta["tableFileSha256"])
			self.assertEqual(a.source_bounds.min_rd, date(1882, 11, 13).toordinal())
			b = service.convert(C.GREGORIAN, C.HIJRI, year=2026, month=9, day=13, hijri_method=M.UMM_AL_QURA)
			self.assert_date(b, (1448, 4, 1))
			self.assertEqual(a.reference, b.reference)

	def test_validation_codes_no_normalization(self):
		for field in ("year", "month", "day"):
			for value in (True, 1.0, "1", None, [], {}):
				args = dict(year=1448, month=4, day=1)
				args[field] = value
				for method in M:
					r = self.service.convert(C.HIJRI, C.GREGORIAN, **args, hijri_method=method)
					self.assertEqual((r.error.code, r.error.field), ("invalid_type", field))
		for y, m, d, code in ((0, 1, 1, "invalid_year"), (-1, 1, 1, "invalid_year"),
			(1448, 0, 1, "invalid_month"), (1448, 13, 1, "invalid_month"),
			(1448, 4, 0, "invalid_day"), (1448, 4, 31, "invalid_day")):
			for method in M:
				self.assertEqual(self.convert(y=y, m=m, d=d, method=method).error.code, code)
		for source, target, method, code in (("HIJRI", C.GREGORIAN, M.IIC, "unsupported_calendar"),
			(C.HIJRI, [], M.IIC, "unsupported_calendar"),
			(C.HIJRI, C.GREGORIAN, "IIC", "unsupported_hijri_method"),
			(C.HIJRI, C.GREGORIAN, None, "hijri_method_required"),
			(C.GREGORIAN, C.JULIAN, M.IIC, "unexpected_hijri_method")):
			self.assertEqual(self.convert(source, target, method=method).error.code, code)
		for y in range(1300, 1601, 17):
			for m in range(1, 13):
				length = self.provider.month_length(y, m)
				self.assertEqual(self.convert(y=y, m=m, d=length + 1).error.code, "invalid_day")

	def test_historical_bounds_and_julian_rules(self):
		self.assert_date(self.convert(y=1, m=1, d=1, method=M.IIC), (622, 7, 19))
		self.assert_date(self.convert(y=9666, m=4, d=2, method=M.IIC), (9999, 12, 31))
		for args in ((C.HIJRI, C.GREGORIAN, 9666, 4, 3, M.IIC),
			(C.GREGORIAN, C.HIJRI, 622, 7, 18, M.IIC),
			(C.JULIAN, C.GREGORIAN, 9999, 10, 20, None)):
			self.assertEqual(self.convert(*args).error.code, "out_of_range")
		self.assert_date(self.convert(C.JULIAN, C.GREGORIAN, 1700, 2, 29, None), (1700, 3, 11))
		self.assertEqual(self.convert(C.GREGORIAN, C.JULIAN, 1700, 2, 29, None).error.code, "invalid_day")

	def test_provider_failure_is_structured_and_never_falls_back(self):
		with patch.object(self.provider, "to_gregorian", side_effect=RuntimeError("private diagnostic")):
			r = self.convert()
			self.assertEqual(r.error.code, "reference_data_error")
			self.assertNotIn("private diagnostic", repr(r))
			self.assertIsNone(r.converted)
		with patch.object(self.provider, "from_gregorian", side_effect=OSError("unavailable")):
			self.assertEqual(self.convert().error.code, "reference_data_error")


if __name__ == "__main__":
	unittest.main()
