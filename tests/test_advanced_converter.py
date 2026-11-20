"""Model and real wx acceptance cases; no user settings or clipboard access."""
from itertools import permutations
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from calendar_converter_launcher import prepare_wx, create_model_dependencies
wx = prepare_wx()
from awqati.application.historical_conversion import ConversionCalendar as C, HijriMethod as M
from awqati.nvda_adapter.advanced_converter_model import AdvancedConversionModel, reversed_result
from awqati.nvda_adapter.calendar_converter_model import EntryError
from awqati.nvda_adapter.advanced_converter_dialog import AdvancedConverterDialog, show_advanced_converter
from awqati.nvda_adapter.calendar_converter_dialog import CalendarConverterDialog


class AdvancedModelTests(unittest.TestCase):
	def setUp(self):
		self.model = AdvancedConversionModel(*create_model_dependencies("2026-09-12"))

	def test_defaults_and_today(self):
		m = self.model
		self.assertEqual((m.source, m.target, m.method), (C.HIJRI, C.GREGORIAN, M.IIC))
		self.assertEqual(m.current(), dict(day="29", month="3", year="1448"))
		m.method = M.UMM_AL_QURA
		self.assertEqual(m.current(), dict(day="1", month="4", year="1448"))
		m.source = C.JULIAN
		self.assertEqual(m.current(), dict(day="30", month="8", year="2026"))

	def test_all_directions_both_methods_and_repeated_reverse(self):
		m = self.model
		for method in M:
			for source, target in permutations(C, 2):
				m.source, m.target, m.method = source, target, method
				result = m.convert(m.current())
				self.assertEqual(result.hijri_method, method if C.HIJRI in (source, target) else None)
				original = result
				for i in range(100):
					result = reversed_result(result)
					self.assertIs(result.reference, original.reference)
					self.assertEqual(result.rd, original.rd)
					self.assertEqual(result.hijri_method, original.hijri_method)
				self.assertEqual(result, original)

	def test_historical_samples_and_partial_limits(self):
		m = self.model
		values = dict(day="١٢", month="۹", year="365")
		r = m.convert(values)
		self.assertEqual((r.converted.year,r.converted.month,r.converted.day),(976,5,19))
		m.target = C.JULIAN
		r = m.convert(values)
		self.assertEqual((r.converted.year,r.converted.month,r.converted.day),(976,5,14))
		self.assertEqual(m.limits("year", values),(1,9666))
		m.convert(dict(day="2",month="4",year="9666"))
		with self.assertRaises(EntryError):m.convert(dict(day="3",month="4",year="9666"))
		m.source,m.target = C.JULIAN,C.GREGORIAN
		m.convert(dict(day="19",month="10",year="9999"))
		with self.assertRaises(EntryError):m.convert(dict(day="20",month="10",year="9999"))
		m.convert(dict(day="16",month="7",year="622"))
		with self.assertRaises(EntryError):m.convert(dict(day="15",month="7",year="622"))

	def test_calendar_month_rules_and_no_clamping(self):
		m = self.model
		for source,year,length in ((C.JULIAN,"1700",29),(C.GREGORIAN,"1700",28),
				(C.GREGORIAN,"2000",29),(C.HIJRI,"15",29),(C.HIJRI,"16",30)):
			m.source = source
			values = dict(day="31",month="12" if source is C.HIJRI else "2",year=year)
			self.assertEqual(m.limits("day", values),(1,length))
			self.assertEqual(values["day"],"31")
			self.assertEqual(m.navigate("day","31","end",values),str(length))
			self.assertEqual(m.navigate("day","31","left",values),"31")

	def test_ummalqura_bounds_and_failure_never_falls_back(self):
		m = self.model;m.method = M.UMM_AL_QURA
		bounds = m.bounds()
		self.assertEqual(m.limits("year",{}),(bounds.first_hijri_year,bounds.last_hijri_year))
		for civil in (bounds.first,bounds.last):
			m.source,m.target=C.GREGORIAN,C.HIJRI
			m.convert({f:str(getattr(civil,f)) for f in ("day","month","year")})
		m.source,m.target = C.HIJRI,C.JULIAN
		with self.assertRaises(EntryError) as caught:m.convert(dict(day="12",month="9",year="365"))
		self.assertEqual(caught.exception.code,"ummalqura_out_of_range")

	def test_civil_conversion_never_reads_lunar_reference(self):
		m = AdvancedConversionModel(self.model.service,None,self.model.today)
		m.source,m.target,m.method = C.GREGORIAN,C.JULIAN,M.UMM_AL_QURA
		r = m.convert(dict(day="10",month="10",year="1582"))
		self.assertIsNone(r.reference);self.assertIsNone(r.hijri_method)
		self.assertEqual(m.limits("day",dict(year="1700",month="2")),(1,28))


class AdvancedDialogTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):cls.app = wx.App.Get() or wx.App(False)

	def setUp(self):
		self.messages=[];self.results=[];self.errors=[]
		self.dependencies=create_model_dependencies("2026-09-12")
		self.d=AdvancedConverterDialog(None,*self.dependencies,language="en",announce=self.messages.append,
			show_result=lambda p,r:self.results.append(r),show_error=lambda p,t:self.errors.append(t))
		self.d.Show();wx.Yield()

	def tearDown(self):
		if self.d:self.d.Destroy()
		wx.Yield()

	def test_tab_order_both_directions_and_default(self):
		d=self.d
		self.assertEqual(d.GetTitle(),"Advanced conversion")
		controls=[d.source,d.target,d.method,*d.entries.values(),d.today_button,d.convert_button,d.close_button]
		self.assertIs(wx.Window.FindFocus(),controls[0])
		for control in controls[1:]:
			wx.Window.FindFocus().Navigate();wx.Yield();self.assertIs(wx.Window.FindFocus(),control)
		for control in reversed(controls[:-1]):
			wx.Window.FindFocus().Navigate(wx.NavigationKeyEvent.IsBackward);wx.Yield()
			self.assertIs(wx.Window.FindFocus(),control)
		self.assertEqual(d.GetDefaultItem(),d.convert_button)

	def test_changes_preserve_input_except_source(self):
		d=self.d
		d.entries['year'].ChangeValue('365');before=d.values()
		d.target.SetSelection(2);d._target_changed(None)
		self.assertEqual(d.values(),before)
		d.method.SetSelection(1);d._method_changed(None)
		self.assertEqual(d.values(),before)
		d.source.SetSelection(1);d._source_changed(None)
		self.assertEqual(d.values(),dict(day='12',month='9',year='2026'))
		self.assertFalse(d.method.IsEnabled())
		self.assertIsNone(d.model.effective_method)
		d.target.SetSelection(0);d._target_changed(None)
		self.assertTrue(d.method.IsEnabled());self.assertEqual(d.method.GetSelection(),1)

	def test_reject_same_target_without_losing_date(self):
		d=self.d;before=d.values()
		d.target.SetSelection(0);d._target_changed(None)
		self.assertEqual(d.model.target,C.GREGORIAN);self.assertEqual(d.values(),before)
		d.source.SetSelection(1);d._source_changed(None)
		self.assertNotEqual(d.model.target,d.model.source)

	def test_parent_sync_for_simple_and_advanced(self):
		for cls in (CalendarConverterDialog,AdvancedConverterDialog):
			d=cls(None,*self.dependencies,language='ar',announce=lambda t:None)
			try:
				r=d.model.convert(d.values());rev=reversed_result(r)
				with patch('awqati.nvda_adapter.conversion_result_dialog.show_conversion_result',return_value=rev):d._message_result(d,r)
				self.assertEqual(d.model.source,C.GREGORIAN)
				self.assertEqual(d.values(),{f:str(getattr(rev.original,f)) for f in ('day','month','year')})
				self.assertEqual(d.model.convert(d.values()),rev)
			finally:d.Destroy()

	def test_basic_advanced_button_opens_independent_dialog_and_returns_focus(self):
		d=CalendarConverterDialog(None,*self.dependencies,language='ar',announce=lambda t:None)
		d.Show();wx.Yield();d.advanced_button.SetFocus();wx.Yield();seen=[]
		def close_child():
			for w in wx.GetTopLevelWindows():
				if isinstance(w,AdvancedConverterDialog) and w.IsModal():
					seen.append((w.GetTitle(),w.model.method));w._close()
		wx.CallLater(80,close_child)
		try:
			d._advanced(None)
			self.assertEqual(seen,[('التحويل المتقدم',M.IIC)])
			self.assertIs(wx.Window.FindFocus(),d.advanced_button)
		finally:d.Destroy()
