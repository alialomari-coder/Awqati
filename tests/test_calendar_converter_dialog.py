"""Native wx tests. Event dispatch is not a claim of physical-key/NVDA listening."""
from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from calendar_converter_launcher import prepare_wx, create_model_dependencies
wx=prepare_wx()
from awqati.nvda_adapter.calendar_converter_dialog import CalendarConverterDialog


class ConverterDialogTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.app=wx.App.Get() or wx.App(False)

	def setUp(self):
		self.messages,self.results,self.errors=[],[],[]
		self.dependencies=create_model_dependencies("2026-09-12")
		self.dialog=CalendarConverterDialog(None,*self.dependencies,language="en",
			announce=self.messages.append,show_result=lambda parent,result:self.results.append(result),
			show_error=lambda parent,text:self.errors.append(text))
		self.dialog.Show();wx.Yield()

	def tearDown(self):
		if self.dialog and not self.dialog.IsBeingDeleted():self.dialog.Destroy()
		wx.Yield()

	def event(self,control,event_type,code=None):
		if code is None:event=wx.CommandEvent(event_type.typeId,control.GetId())
		else:
			event=wx.KeyEvent(event_type.typeId);event.KeyCode=code
		event.SetEventObject(control)
		control.GetEventHandler().ProcessEvent(event);wx.Yield()
		return event

	def fill(self,**values):
		for field,value in values.items():self.dialog.entries[field].SetValue(value)
		wx.Yield()

	def test_order_labels_vertical_layout_and_no_static_tab_stop(self):
		d=self.dialog
		self.assertEqual(d.GetTitle(),"Date converter")
		self.assertTrue(d.advanced_button.IsEnabled())
		self.assertFalse(d.info.AcceptsFocus())
		self.assertEqual(d.values(),dict(day="1",month="4",year="1448"))
		positions=[d.entries[field].GetPosition().y for field in ("day","month","year")]
		self.assertTrue(positions[0]<positions[1]<positions[2])
		controls=[d.source,d.target,*d.entries.values(),d.today_button,d.convert_button,d.advanced_button,d.close_button]
		d.source.SetFocus();wx.Yield()
		for control in controls[1:]:
			wx.Window.FindFocus().Navigate();wx.Yield()
			self.assertIs(wx.Window.FindFocus(),control)
		for control in reversed(controls[:-1]):
			wx.Window.FindFocus().Navigate(wx.NavigationKeyEvent.IsBackward);wx.Yield()
			self.assertIs(wx.Window.FindFocus(),control)

	def test_all_eight_keys_in_all_three_real_text_controls(self):
		d=self.dialog
		for field in ("day","month","year"):
			for key in (wx.WXK_UP,wx.WXK_DOWN,wx.WXK_PAGEUP,wx.WXK_PAGEDOWN,wx.WXK_HOME,wx.WXK_END,wx.WXK_LEFT,wx.WXK_RIGHT):
				self.fill(day="15",month="6",year="1448")
				control=d.entries[field];control.SetFocus();wx.Yield()
				before=d.values();selection=control.GetSelection()
				mapping={wx.WXK_UP:"up",wx.WXK_DOWN:"down",wx.WXK_PAGEUP:"pageup",wx.WXK_PAGEDOWN:"pagedown",
					wx.WXK_HOME:"home",wx.WXK_END:"end",wx.WXK_LEFT:"left",wx.WXK_RIGHT:"right"}
				expected=d.model.navigate(field,control.GetValue(),mapping[key],before)
				self.event(control,wx.EVT_KEY_DOWN,key)
				self.assertEqual(control.GetValue(),expected)
				self.assertIs(wx.Window.FindFocus(),control)
				for other in before:
					if other!=field:self.assertEqual(d.values()[other],before[other])
				if key in (wx.WXK_LEFT,wx.WXK_RIGHT):self.assertEqual(control.GetSelection(),selection)

	def test_source_change_refills_today_and_target_cannot_equal_source(self):
		d=self.dialog
		self.fill(day="31",month="12",year="1500")
		d.source.SetSelection(1);self.event(d.source,wx.EVT_CHOICE)
		self.assertEqual(d.values(),dict(day="12",month="9",year="2026"))
		self.assertEqual(d.target.GetStringSelection(),"Hijri")
		self.assertIn("September",d.labels["month"].GetLabel())
		self.assertEqual(len(self.messages),1)
		d.target.SetSelection(0);self.event(d.target,wx.EVT_CHOICE)
		self.assertEqual(d.target.GetSelection(),1)
		d.source.SetSelection(0);self.event(d.source,wx.EVT_CHOICE)
		self.assertEqual(d.values(),dict(day="1",month="4",year="1448"))

	def test_enter_converts_arabic_persian_and_preserves_original_and_focus(self):
		d=self.dialog
		self.fill(day="١",month="۴",year="١٤٤٨")
		d.entries["year"].SetFocus();wx.Yield();before=d.values()
		self.event(d.entries["year"],wx.EVT_TEXT_ENTER)
		self.assertEqual(len(self.results),1)
		r=self.results[0].converted
		self.assertEqual((r.year,r.month,r.day),(2026,9,12))
		self.assertEqual(d.values(),before)
		self.assertIs(wx.Window.FindFocus(),d.entries["year"])

	def test_error_focus_selection_and_no_silent_day_clamp(self):
		d=self.dialog
		d.source.SetSelection(1);self.event(d.source,wx.EVT_CHOICE)
		self.fill(day="31",month="4",year="2026")
		self.event(d.convert_button,wx.EVT_BUTTON)
		self.assertEqual(d.entries["day"].GetValue(),"31")
		self.assertIs(wx.Window.FindFocus(),d.entries["day"])
		self.assertEqual(d.entries["day"].GetStringSelection(),"31")
		self.assertTrue(self.errors)
		self.fill(year="invalid")
		self.event(d.convert_button,wx.EVT_BUTTON)
		self.assertIs(wx.Window.FindFocus(),d.entries["year"])

	def test_today_and_empty_context_key_do_not_crash_or_move_focus(self):
		d=self.dialog
		self.fill(day="1",month="",year="")
		d.entries["day"].SetFocus();wx.Yield()
		self.event(d.entries["day"],wx.EVT_KEY_DOWN,wx.WXK_UP)
		self.assertEqual(d.entries["day"].GetValue(),"1")
		self.assertIs(wx.Window.FindFocus(),d.entries["day"])
		self.event(d.today_button,wx.EVT_BUTTON)
		self.assertEqual(d.values(),dict(day="1",month="4",year="1448"))

	def test_today_failure_on_source_change_never_reinterprets_old_values(self):
		d=self.dialog
		d.model.today=lambda:date(1800,1,1)
		d.source.SetSelection(1);self.event(d.source,wx.EVT_CHOICE)
		self.assertEqual(d.values(),dict(day="",month="",year=""))
		self.assertTrue(self.errors)

	def test_arabic_labels_month_name_and_temporary_result_translation(self):
		d=self.dialog;d.Destroy();wx.Yield()
		self.dialog=d=CalendarConverterDialog(None,*self.dependencies,language="ar",announce=self.messages.append,
			show_result=lambda parent,result:self.results.append(result),show_error=lambda *args:None)
		d.Show();wx.Yield()
		self.assertEqual(d.GetTitle(),"محوّل التاريخ")
		self.assertEqual(d.info.GetLabel(),"المرجع الهجري: أم القرى. المرجع الميلادي: الغريغوري")
		self.fill(month="٩")
		self.assertIn("رمضان",d.entries["month"].GetName())
		self.fill(month="4")
		self.event(d.convert_button,wx.EVT_BUTTON)
		self.assertIn("12 سبتمبر 2026",d.texts.result(self.results[-1]))

	def test_escape_destroys_modeless_dialog_and_releases_window(self):
		d=self.dialog
		self.event(d,wx.EVT_CHAR_HOOK,wx.WXK_ESCAPE)
		wx.Yield()
		self.assertFalse(bool(d))
		self.dialog=None

	def test_native_message_configuration_localizes_only_existing_ok_button(self):
		# Construct real wx.MessageDialog instances. Native rendered/MSAA labels
		# are checked separately by the live NVDA probe and visible UI review.
		observed=[]
		class CheckedMessage(wx.MessageDialog):
			def ShowModal(message):
				observed.append(dict(label=message.GetOKLabel(),style=message.GetMessageDialogStyle(),
					message=message.GetMessage(),destroyed=False))
				return wx.ID_OK
			def Destroy(message):
				observed[-1]["destroyed"]=True
				return super().Destroy()
		for language,expected in (("ar","موافق"),("en","OK")):
			self.dialog.Destroy();wx.Yield()
			self.dialog=d=CalendarConverterDialog(None,*self.dependencies,language=language,announce=lambda text:None)
			d.Show();wx.Yield()
			result=d.model.convert(d.values())
			before=d.values()
			with patch("awqati.nvda_adapter.calendar_converter_dialog.wx.MessageDialog",CheckedMessage), patch("awqati.nvda_adapter.conversion_result_dialog.show_conversion_result", lambda parent, result, **options: result):
				d.entries["year"].SetFocus();wx.Yield()
				d._convert()
				self.assertIs(wx.Window.FindFocus(),d.entries["year"])
				self.assertEqual(d.values(),before)
				d.entries["year"].ChangeValue("365")
				d._convert()
				self.assertIs(wx.Window.FindFocus(),d.entries["year"])
				self.assertEqual(d.entries["year"].GetStringSelection(),"365")
			for row in observed[-1:]:
				self.assertEqual(row["label"],expected)
				self.assertTrue(row["style"] & wx.OK)
				self.assertFalse(row["style"] & wx.CANCEL)
				self.assertTrue(row["destroyed"])
			self.assertIn("Umm" if language == "en" else "أم القرى",observed[-1]["message"])


if __name__=="__main__":unittest.main()
