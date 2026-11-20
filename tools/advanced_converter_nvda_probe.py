"""Task-4 scratchpad acceptance in a synthetic NVDA profile/private desktop.

Real NVDA objects and speech. Native posted keys and wx navigation are test
input, not human listening. Clipboard UI uses an injected port; the separate
clipboard probe verifies the real clipboard in its own Windows window station.
"""
from pathlib import Path
import sys
import ctypes
from ctypes import wintypes
import globalVars
import wx
import speech
import controlTypes
import textInfos
import json
import traceback

PROFILE=Path(globalVars.appArgs.configPath)
ROOT=Path((PROFILE/'source-root.txt').read_text(encoding='utf-8'))
sys.path.insert(0,str(ROOT/'tools'))
from calendar_converter_button_probe import GlobalPlugin as ButtonProbe


class GlobalPlugin(ButtonProbe):
	def guard(self, callback):
		if self.result.get('error'):
			return
		try:
			callback()
		except Exception:
			self.result['error']=traceback.format_exc()
			(self.profile/'live-result.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2),encoding='utf-8')
			for w in reversed(wx.GetTopLevelWindows()):
				if isinstance(w,wx.Dialog) and w.IsModal():w.EndModal(wx.ID_CANCEL)
			wx.CallAfter(self.finish)

	def inspect(self):
		from awqati.nvda_adapter.advanced_converter_dialog import AdvancedConverterDialog
		d=self.dialog
		self.require(d.advanced_button.IsEnabled(),'basic advanced action enabled')
		self.require(self.obj(d.advanced_button).name==d.texts.gettext('Advanced...'),'NVDA advanced button localized')
		self.result['nativeMessages']=[]
		self.result['clipboardScope']='Injected port only; real clipboard checked separately in isolated window station'
		d.advanced_button.SetFocus()
		wx.CallLater(180,lambda:self.guard(self.inspect_advanced))
		d._advanced(None)
		self.require(wx.Window.FindFocus() is d.advanced_button,'closing advanced restores basic advanced button focus')
		self.require(self.advanced._closed if self.advanced else True,'advanced modal closed')
		d.entries['year'].ChangeValue('1448')
		d.show_result=d._message_result
		d.convert_button.SetFocus()
		wx.CallLater(150,lambda:self.guard(self.inspect_simple_result))
		d._convert()
		self.require(wx.Window.FindFocus() is d.convert_button,'simple result restores converter focus')
		self.require(d.model.source.value=='GREGORIAN_PROLEPTIC','simple parent synchronized after reverse')
		# Existing native error only has OK, localized explicitly by the converter.
		d.show_error=d._message_error
		for index,key in enumerate(('Enter','Escape')):
			d.entries['year'].ChangeValue('0');d.entries['year'].SetFocus()
			self.active_case=index;self.key_timed_out=False
			wx.CallLater(180,lambda key=key:self.guard(lambda:self.inspect_native(d.texts.gettext('Check the date'),key)))
			d._convert();self.active_case=None
			self.require(not self.key_timed_out,'native error '+key+' dismisses')
			self.require(wx.Window.FindFocus() is d.entries['year'],'native error '+key+' restores invalid field')
		d._close();self.dialog=None
		self.opener.SetFocus()
		wx.CallLater(250,lambda:self.guard(self.closed))

	def tab_order(self,controls,label):
		controls[0].SetFocus()
		for control in controls[1:]:
			wx.Window.FindFocus().Navigate()
			self.require(wx.Window.FindFocus() is control,label+' forward Tab '+control.GetName())
		for control in reversed(controls[:-1]):
			wx.Window.FindFocus().Navigate(wx.NavigationKeyEvent.IsBackward)
			self.require(wx.Window.FindFocus() is control,label+' backward Tab '+control.GetName())

	def inspect_advanced(self):
		from awqati.nvda_adapter.advanced_converter_dialog import AdvancedConverterDialog
		from awqati.application.historical_conversion import ConversionCalendar as C, HijriMethod as M
		found=[w for w in wx.GetTopLevelWindows() if isinstance(w,AdvancedConverterDialog) and w.IsModal()]
		self.require(len(found)==1,'one independent advanced modal')
		d=self.advanced=found[0]
		self.require(d.GetTitle()==d.texts.gettext('Advanced conversion'),'advanced title localized')
		self.require(wx.Window.FindFocus() is d.source,'advanced initial source focus')
		for control in (d.source,d.target,d.method,*d.entries.values(),d.today_button,d.convert_button,d.close_button):
			obj=self.obj(control)
			self.require(bool(obj.name),'advanced native accessible name '+control.GetName())
		for field in ('day','month','year'):
			self.require(self.obj(d.entries[field]).value==d.entries[field].GetValue(),'advanced native '+field+' value')
		self.tab_order([d.source,d.target,d.method,*d.entries.values(),d.today_button,d.convert_button,d.close_button],'advanced')
		for field,value in dict(day='12',month='9',year='365').items():d.entries[field].ChangeValue(value)
		d._changed('month');before=d.values()
		d.target.SetSelection(2);d._target_changed(None)
		self.require(d.values()==before,'target change preserves historical input')
		d.method.SetSelection(1);d._method_changed(None)
		self.require(d.values()==before,'method change preserves historical input')
		d.method.SetSelection(0);d._method_changed(None)
		d.convert_button.SetFocus();wx.CallLater(150,lambda:self.guard(self.inspect_historical_result))
		d._convert()
		self.require(wx.Window.FindFocus() is d.convert_button,'advanced result restores converter focus')
		self.require(d.model.source is C.JULIAN and d.model.target is C.HIJRI,'advanced parent follows final reversed direction')
		self.require(d.values()==dict(day='14',month='5',year='976'),'advanced parent follows final reversed date')
		self.require(d.model.method is M.IIC,'advanced parent keeps method')
		d.source.SetSelection(1);d._source_changed(None)
		d.target.SetSelection(2);d._target_changed(None)
		self.require(not d.method.IsEnabled(),'civil-only method disabled')
		self.require(d.model.effective_method is None,'civil-only request omits Hijri method')
		self.require(d.values()==dict(day='12',month='9',year='2026'),'source change resets today')
		d._close()
		self.advanced=None

	def inspect_historical_result(self):
		from awqati.nvda_adapter.conversion_result_dialog import ConversionResultDialog
		found=[w for w in wx.GetTopLevelWindows() if isinstance(w,ConversionResultDialog) and w.IsModal()]
		self.require(len(found)==1,'one shared historical result modal')
		r=self.result_dialog=found[0]
		self.require(wx.Window.FindFocus() is r.output,'result initially focuses readable text')
		obj=self.obj(r.output)
		self.require(obj.role is controlTypes.Role.EDITABLETEXT,'result native text role')
		self.require(not r.output.IsEditable(),'result text readonly')
		self.require('365' in obj.value and '976' in obj.value and 'IIc' in obj.value,'NVDA reads both dates and reference')
		self.require(not r.FindWindowById(wx.ID_OK,r),'result has no OK button')
		for control in (r.copy_button,r.reverse_button,r.close_button):
			self.require(self.obj(control).name==control.GetLabel(),'result actual NVDA localized button '+control.GetLabel())
		self.tab_order([r.output,r.copy_button,r.reverse_button,r.close_button],'result')
		self.copied=[];r.copy_text=lambda t:self.copied.append(t) or True
		r.copy_button.SetFocus();r._copy()
		expected='14 مايو أيار 976 م (يولياني)' if r.texts.arabic else '14 May 976 CE (Julian)'
		self.require(self.copied[-1]==expected,'Julian clipboard text approved format')
		reference=r.result.reference;initial=r.result
		r.reverse_button.SetFocus()
		for i in range(11):r._reverse()
		self.require(wx.Window.FindFocus() is r.reverse_button,'repeated reverse retains button focus')
		self.require(r.result.reference is reference,'repeated reverse pins reference object and version')
		r._copy()
		expected='12 رمضان 365 هـ' if r.texts.arabic else '12 Ramadan 365 AH'
		self.require(self.copied[-1]==expected,'Hijri clipboard text approved format')
		self.result['speechBeforeRead']=len(self.result['speech'])
		obj=self.obj(r.output)
		speech.speakTextInfo(obj.makeTextInfo(textInfos.POSITION_ALL),reason=controlTypes.OutputReason.CARET)
		wx.CallLater(300,lambda:self.guard(self.finish_historical_result))

	def finish_historical_result(self):
		segment=self.result['speech'][self.result['speechBeforeRead']:]
		self.result['readResultSpeech']=segment
		self.require(any('976' in ' '.join(line) and '365' in ' '.join(line) for line in segment),'full result text enters real NVDA speech pipeline')
		r=self.result_dialog
		r.output.SetFocus()
		self.post_key(r.output,wx.WXK_ESCAPE)

	def inspect_simple_result(self):
		from awqati.nvda_adapter.conversion_result_dialog import ConversionResultDialog
		r=next(w for w in wx.GetTopLevelWindows() if isinstance(w,ConversionResultDialog) and w.IsModal())
		self.require('1448' in self.obj(r.output).value,'simple uses shared readable result')
		r.copy_text=lambda t:self.copied.append(t) or True
		r._copy()
		expected='12 سبتمبر أيلول 2026 م' if r.texts.arabic else '12 September 2026 CE (Gregorian)'
		self.require(self.copied[-1]==expected,'Gregorian clipboard text approved format')
		r._reverse()
		self.post_key(r.output,wx.WXK_RETURN)

	def post_key(self,control,key):
		# A private desktop has no active keyboard queue. Use wx key dispatch for
		# these dialogs, and separately verify injected keyboard input visibly.
		event=wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId);event.KeyCode=key
		control.GetParent().GetEventHandler().ProcessEvent(event)
