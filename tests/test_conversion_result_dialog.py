"""Result acceptance; all clipboard writes use an injected in-memory port."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from calendar_converter_launcher import prepare_wx,create_model_dependencies
wx=prepare_wx()
from awqati.nvda_adapter.conversion_result_dialog import ConversionResultDialog,copy_to_clipboard
from awqati.nvda_adapter.calendar_converter_text import ConverterText
from awqati.nvda_adapter.calendar_converter_dialog import CalendarConverterDialog
from awqati.nvda_adapter.advanced_converter_dialog import AdvancedConverterDialog
from awqati.nvda_adapter.advanced_converter_model import AdvancedConversionModel
from awqati.application.historical_conversion import ConversionCalendar as C, HijriMethod as M


class ResultDialogTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):cls.app=wx.App.Get() or wx.App(False)

	def setUp(self):
		self.model=AdvancedConversionModel(*create_model_dependencies('2026-09-12'))
		self.result=self.model.convert(dict(day='12',month='9',year='365'))
		self.messages=[];self.copies=[]
		self.d=ConversionResultDialog(None,self.result,texts=ConverterText('en'),announce=self.messages.append,
			copy_text=lambda t:self.copies.append(t) or True)
		self.d.Show();wx.Yield()

	def tearDown(self):
		if self.d:self.d.Destroy()
		wx.Yield()

	def test_content_readonly_focus_tab_and_no_ok(self):
		d=self.d
		self.assertIs(wx.Window.FindFocus(),d.output)
		self.assertEqual(d.output.GetInsertionPoint(),0)
		self.assertFalse(d.output.IsEditable())
		self.assertIn('12 Ramadan 365 (Hijri)',d.output.GetValue())
		self.assertIn('19 May 976 (Gregorian)',d.output.GetValue())
		self.assertIn('IIc',d.output.GetValue())
		self.assertIsNone(d.FindWindowById(wx.ID_OK,d))
		controls=[d.output,d.copy_button,d.reverse_button,d.close_button]
		for control in controls[1:]:
			wx.Window.FindFocus().Navigate();wx.Yield();self.assertIs(wx.Window.FindFocus(),control)
		for control in reversed(controls[:-1]):
			wx.Window.FindFocus().Navigate(wx.NavigationKeyEvent.IsBackward);wx.Yield()
			self.assertIs(wx.Window.FindFocus(),control)

	def test_copy_only_converted_date_and_reversal_keeps_window_and_button_focus(self):
		d=self.d;d.copy_button.SetFocus();wx.Yield();d._copy()
		self.assertEqual(self.copies,['19 May 976 CE (Gregorian)'])
		self.assertIs(wx.Window.FindFocus(),d.copy_button)
		d.reverse_button.SetFocus();wx.Yield();d._reverse();d._copy()
		self.assertEqual(self.copies[-1],'12 Ramadan 365 AH')
		self.assertIs(wx.Window.FindFocus(),d.reverse_button)
		self.assertIs(d.result.reference,self.result.reference)
		d._reverse();self.assertEqual(d.result,self.result)
		self.assertTrue(d.IsShown())

	def test_copy_failure_is_announced_without_close(self):
		for copier in (lambda t:False,lambda t:1/0):
			self.d.copy_text=copier;self.d._copy()
			self.assertIn('could not',self.messages[-1]);self.assertTrue(self.d.IsShown())

	def test_approved_clipboard_formats_all_calendars_and_languages(self):
		from awqati.application.historical_conversion import ConversionDate
		for language, expected in (
			('ar', ['12 رمضان 365 هـ', '19 مايو أيار 976 م', '14 مايو أيار 976 م (يولياني)']),
			('en', ['12 Ramadan 365 AH', '19 May 976 CE (Gregorian)', '14 May 976 CE (Julian)'])):
			texts=ConverterText(language)
			for calendar,year,month,day,text in zip(C,(365,976,976),(9,5,5),(12,19,14),expected):
				value=ConversionDate(calendar,year,month,day)
				self.assertEqual(texts.clipboard_date(value),text)
				self.d.texts=texts
				from dataclasses import replace
				self.d.result=replace(self.result,converted=value)
				self.d._copy()
				self.assertEqual(self.copies[-1],text)
		# Every Eastern Syriac name is in calendar order; independent approved list.
		months=('كانون الثاني','شباط','آذار','نيسان','أيار','حزيران','تموز','آب','أيلول','تشرين الأول','تشرين الثاني','كانون الأول')
		for number,name in enumerate(months,1):
			for calendar in (C.GREGORIAN,C.JULIAN):
				self.assertIn(name,ConverterText('ar').clipboard_date(ConversionDate(calendar,2026,number,1)))

	def test_arabic_and_english_all_references_and_identity(self):
		for language in ('ar','en'):
			texts=ConverterText(language)
			for method in M:
				self.model.method=method
				r=self.model.convert(self.model.current())
				self.assertIn('أم القرى' if language=='ar' else 'Umm al-Qura',texts.result(r)) if method is M.UMM_AL_QURA else self.assertIn('IIc',texts.result(r))
			self.model.source,self.model.target=C.GREGORIAN,C.JULIAN
			r=self.model.convert(dict(year='1582',month='10',day='10'))
			text=texts.result(r)
			self.assertIn('يولياني' if language=='ar' else 'Julian',text)
			self.assertIn('غريغوري' if language=='ar' else 'Gregorian',text)
			self.assertNotIn('IIc',text)
			self.assertEqual(texts.gettext('OK'),'موافق' if language=='ar' else 'OK')
			self.assertEqual(texts.gettext('Cancel'),'إلغاء' if language=='ar' else 'Cancel')
			self.model.source,self.model.target=C.HIJRI,C.GREGORIAN

	def test_real_modal_result_integrates_both_parents_and_restores_focus(self):
		for cls in (CalendarConverterDialog,AdvancedConverterDialog):
			p=cls(None,*create_model_dependencies('2026-09-12'),language='en',announce=lambda t:None)
			p.Show();wx.Yield();p.convert_button.SetFocus();wx.Yield();seen=[]
			original=p.model.convert(p.values())
			def act():
				for w in wx.GetTopLevelWindows():
					if isinstance(w,ConversionResultDialog) and w.IsModal():
						seen.append(w.GetTitle());w._reverse();w._close()
			wx.CallLater(100,act)
			try:
				p._convert()
				self.assertEqual(seen,['Conversion result'])
				self.assertIs(wx.Window.FindFocus(),p.convert_button)
				self.assertEqual(p.model.source,original.converted.calendar)
				self.assertEqual(p.model.convert(p.values()).converted,original.original)
			finally:p.Destroy()

	def test_enter_and_escape_from_output_close(self):
		for code in (wx.WXK_RETURN,wx.WXK_ESCAPE):
			if self.d:self.d.Destroy();wx.Yield()
			self.d=ConversionResultDialog(None,self.result,texts=ConverterText('en'),copy_text=lambda t:True)
			self.d.Show();wx.Yield()
			event=wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId);event.KeyCode=code
			self.d.GetEventHandler().ProcessEvent(event);wx.Yield()
			self.assertFalse(bool(self.d));self.d=None

	def test_clipboard_port_data_and_ownership_on_failure(self):
		class Clipboard:
			def __init__(self,opened=True,fail=False):self.opened=opened;self.fail=fail;self.closed=False
			def Open(self):return self.opened
			def SetData(self,data):
				self.text=data.GetText()
				if self.fail:raise RuntimeError('owned clipboard failure')
				return True
			def Close(self):self.closed=True
		with patch('awqati.nvda_adapter.conversion_result_dialog.wx.TheClipboard',None):
			port=Clipboard();self.assertTrue(copy_to_clipboard('19 May 976 (Gregorian)',port))
			self.assertEqual(port.text,'19 May 976 (Gregorian)');self.assertTrue(port.closed)
			port=Clipboard(opened=False);self.assertFalse(copy_to_clipboard('test',port));self.assertFalse(port.closed)
			port=Clipboard(fail=True)
			with self.assertRaises(RuntimeError):copy_to_clipboard('test',port)
			self.assertTrue(port.closed)
