"""Pure input/controller acceptance checks for the basic converter."""
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.nvda_adapter.calendar_converter_model import (
	EntryError, SimpleConversionModel, parse_number, stepped_value, local_today,
)
from awqati.nvda_adapter.calendar_converter_text import ConverterText
from awqati.application.historical_conversion import HistoricalConversionService, ConversionCalendar as C
from awqati.infrastructure.ummalqura_provider import UmmAlQuraProvider


class EntryModelTests(unittest.TestCase):
	def setUp(self):
		self.lunar = UmmAlQuraProvider()
		self.service = HistoricalConversionService(self.lunar)
		self.model = SimpleConversionModel(self.service, self.lunar, lambda: date(2026, 9, 12))

	def test_three_digit_sets_and_mixed_digits(self):
		for text in ("2026", "٢٠٢٦", "۲۰۲۶", "2٠۲6", "0002026"):
			self.assertEqual(parse_number(text, "year"), 2026)

	def test_reject_ambiguous_empty_fraction_sign_and_unicode_controls(self):
		for text in ("", " ", " 2", "2 ", "-2", "+2", "2.0", "٢٫٥", "1,000", "1_000",
			"²", "②", "𝟚", "2\u200f", "2\n", "1e3", "zero", None, True, "1"*33):
			with self.subTest(text=text), self.assertRaises(EntryError):
				parse_number(text, "day")
		for field in ("day", "month", "year"):
			with self.assertRaises(EntryError) as caught:
				parse_number("٠", field)
			self.assertEqual(caught.exception.field, field)

	def test_all_navigation_keys_for_three_fields(self):
		for field, text, low, high in (("day", "15", 1, 30), ("month", "6", 1, 12), ("year", "1448", 1300, 1600)):
			for key, expected in (("up", min(high,int(text)+1)), ("down",max(low,int(text)-1)),
				("pageup",min(high,int(text)+10)), ("pagedown",max(low,int(text)-10)),
				("home",low),("end",high),("left",int(text)),("right",int(text))):
				self.assertEqual(stepped_value(text,key,low,high,field),str(expected))
			self.assertEqual(stepped_value(str(high),"up",low,high,field),str(high))
			self.assertEqual(stepped_value(str(low),"down",low,high,field),str(low))

	def test_dynamic_day_lengths_and_invalid_context(self):
		for year in (1300, 1448, 1600):
			for month in range(1,13):
				values={"year":str(year),"month":str(month),"day":"1"}
				self.assertEqual(self.model.limits("day",values),(1,self.lunar.month_length(year,month)))
		self.model.source=C.GREGORIAN
		for year,month,days in ((2024,2,29),(2026,2,28),(2100,2,28),(2000,2,29),(2026,4,30),(2026,1,31)):
			self.assertEqual(self.model.limits("day",dict(year=str(year),month=str(month))), (1,days))
		for year,month in (("", "2"),("2026",""),("2026","13"),("-1","2")):
			self.assertIsNone(self.model.limits("day",dict(year=year,month=month)))

	def test_navigation_does_not_roll_over_other_fields(self):
		values=dict(day="30",month="12",year="1448")
		original=values.copy()
		self.model.navigate("month","12","up",values)
		self.model.navigate("day","30","up",values)
		self.assertEqual(values,original)
		with self.assertRaises(EntryError):
			self.model.navigate("day","2","up",dict(month="",year="1448"))

	def test_year_limits_from_provider_and_partial_civil_year_range(self):
		bounds=self.model.bounds()
		self.assertEqual(self.model.limits("year",{}),(bounds.first_hijri_year,bounds.last_hijri_year))
		self.model.source=C.GREGORIAN
		self.assertEqual(self.model.limits("year",{}),(bounds.first.year,bounds.last.year))
		for civil in (bounds.first-timedelta(days=1),bounds.last+timedelta(days=1)):
			with self.assertRaises(EntryError) as caught:
				self.model.convert(dict(day=str(civil.day),month=str(civil.month),year=str(civil.year)))
			self.assertEqual(caught.exception.code,"ummalqura_out_of_range")

	def test_invalid_date_is_preserved_and_not_normalized(self):
		self.model.source=C.GREGORIAN
		for values in (dict(day="31",month="4",year="2026"),dict(day="29",month="2",year="2026")):
			original=values.copy()
			with self.assertRaises(EntryError) as caught:self.model.convert(values)
			self.assertEqual(caught.exception.field,"day")
			self.assertEqual(values,original)

	def test_today_and_actual_conversion_both_directions(self):
		self.assertEqual(self.model.current(),dict(day="1",month="4",year="1448"))
		r=self.model.convert(dict(day="١",month="۴",year="1448"))
		self.assertEqual((r.converted.year,r.converted.month,r.converted.day),(2026,9,12))
		self.model.source=C.GREGORIAN
		self.assertEqual(self.model.current(),dict(day="12",month="9",year="2026"))
		r=self.model.convert(dict(day="12",month="9",year="2026"))
		self.assertEqual((r.converted.year,r.converted.month,r.converted.day),(1448,4,1))

	def test_old_date_and_today_outside_table_do_not_use_iic(self):
		with self.assertRaises(EntryError) as caught:
			self.model.convert(dict(day="12",month="9",year="365"))
		self.assertEqual(caught.exception.code,"ummalqura_out_of_range")
		self.model.today=lambda:date(1800,1,1)
		for source in (C.HIJRI,C.GREGORIAN):
			self.model.source=source
			with self.assertRaises(EntryError):self.model.current()

	def test_provider_unavailable_and_unexpected_reference_error(self):
		with patch.object(self.lunar,"from_gregorian",side_effect=RuntimeError("secret")):
			with self.assertRaises(EntryError) as caught:self.model.current()
			self.assertNotIn("secret",str(caught.exception))
		with patch.object(self.service,"convert",side_effect=RuntimeError("secret")):
			with self.assertRaises(EntryError) as caught:self.model.convert(dict(day="1",month="4",year="1448"))
			self.assertEqual(caught.exception.code,"reference_data_error")

	def test_location_timezone_is_used_across_utc_midnight(self):
		zone=timezone(timedelta(hours=3))
		for utc,expected in ((datetime(2026,9,11,21,tzinfo=timezone.utc),date(2026,9,12)),
			(datetime(2026,9,12,20,59,tzinfo=timezone.utc),date(2026,9,12)),
			(datetime(2026,9,12,21,tzinfo=timezone.utc),date(2026,9,13))):
			clock=SimpleNamespace(now=lambda:SimpleNamespace(value=utc))
			zones=SimpleNamespace(get_timezone=lambda identity:zone)
			self.assertEqual(local_today(clock,zones,SimpleNamespace(timezone_id="Asia/Riyadh")),expected)

	def test_arabic_english_labels_months_and_error_text(self):
		ar,en=ConverterText("ar-SA"),ConverterText("en_US")
		self.assertEqual(ar.gettext("Date converter"),"محوّل التاريخ")
		self.assertEqual(en.gettext("Date converter"),"Date converter")
		self.assertEqual(ar.month(C.HIJRI,9),"رمضان")
		self.assertEqual(ar.month(C.GREGORIAN,9),"سبتمبر")
		self.assertEqual(en.month(C.HIJRI,9),"Ramadan")
		self.assertEqual(en.month(C.GREGORIAN,9),"September")
		for code in ("invalid_number","invalid_day","invalid_month","invalid_year","ummalqura_out_of_range",
			"reference_data_error","out_of_range","date_context_required","ummalqura_provider_required","unknown"):
			self.assertNotEqual(ar.error(EntryError(code,"day")),en.error(EntryError(code,"day")))

	def test_no_personal_correction_in_either_direction(self):
		from awqati.domain.settings import CalendarSettings
		outputs=[]
		for correction in range(-2,3):
			settings=CalendarSettings(hijri_adjustment_days=correction)
			with patch.object(self.lunar,"add_days",side_effect=AssertionError("no correction")):
				self.model.source=C.HIJRI
				a=self.model.convert(dict(day="1",month="4",year="1448"))
				self.model.source=C.GREGORIAN
				b=self.model.convert(dict(day="12",month="9",year="2026"))
				outputs.append((a,b))
			self.assertEqual(settings.hijri_adjustment_days,correction)
		self.assertTrue(all(value==outputs[0] for value in outputs))


if __name__=="__main__":unittest.main()
