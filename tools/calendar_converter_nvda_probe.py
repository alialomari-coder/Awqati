"""Scratchpad probe for an isolated NVDA process, never the personal profile.

Real NVDA objects and speech pipeline; programmatic wx events. No claim of
human listening or physical keystrokes. Refuses any non-task3 profile/desktop.
"""
import json
from pathlib import Path
import sys
import traceback
import core
import controlTypes
import globalPluginHandler
import globalVars
import languageHandler
import speech
import versionInfo
import wx


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self.profile=Path(globalVars.appArgs.configPath)
		if not self.profile.name.startswith("task3-live-"):
			raise RuntimeError("Private task3 test profile required")
		self.result=dict(version=versionInfo.version,language=languageHandler.getLanguage(),
			checks=[],objects=[],speech=[],passed=False,
			scope="Real NVDA/MSAA/wx/synth on private desktop; programmatic events, no human listening or physical-key claim")
		self.frame=self.dialog=None
		self.recording=False
		wx.CallLater(3000,lambda:self.guard(self.begin))

	def require(self,value,label):
		if not value:raise AssertionError(label)
		self.result["checks"].append(label)

	def guard(self,callback):
		try:callback()
		except Exception:
			self.result["error"]=traceback.format_exc();self.finish()

	def record(self,speechSequence,**kwargs):
		self.result["speech"].append([item for item in speechSequence if isinstance(item,str)])

	def begin(self):
		import systemUtils
		self.require(systemUtils._getDesktopName().startswith("AwqatiTask3_"),"private desktop verified")
		root=Path((self.profile/"source-root.txt").read_text(encoding="utf-8"))
		package_root_file = self.profile / "package-root.txt"
		addon = Path(package_root_file.read_text(encoding="utf-8")) if package_root_file.exists() else root / "addon"
		sys.path.insert(0,str(addon/"globalPlugins"))
		from awqati.application.historical_conversion import HistoricalConversionService
		from awqati.infrastructure.ummalqura_provider import UmmAlQuraProvider
		from awqati.nvda_adapter.calendar_converter_dialog import CalendarConverterDialog
		from datetime import date
		from speech.extensions import pre_speech
		pre_speech.register(self.record);self.recording=True
		self.lunar=UmmAlQuraProvider(addon/"globalPlugins/awqati/data/calendars/ummalqura")
		if package_root_file.exists():
			import awqati.nvda_adapter.calendar_converter_dialog as loaded
			self.require(Path(loaded.__file__).is_relative_to(addon), "UI regression imports installed package only")
			self.result['loadedModule'] = loaded.__file__
		self.service=HistoricalConversionService(self.lunar)
		self.frame=wx.Frame(None,title="Awqati task3 private accessibility host")
		self.opener=wx.Button(self.frame,label="Open test converter")
		self.frame.Show();self.opener.SetFocus()
		self.results=[];self.errors=[]
		self.dialog=CalendarConverterDialog(self.frame,self.service,self.lunar,lambda:date(2026,9,12),
			language=languageHandler.getLanguage(),
			show_result=lambda parent,result:self.results.append(result),show_error=lambda parent,message:self.errors.append(message))
		self.dialog.Show()
		wx.CallLater(700,lambda:self.guard(self.inspect))

	def obj(self,control):
		from NVDAObjects.IAccessible import getNVDAObjectFromEvent
		obj=getNVDAObjectFromEvent(control.GetHandle(),-4,0)
		self.require(obj is not None,"real NVDA object available")
		self.result["objects"].append(dict(name=obj.name,value=obj.value,role=obj.role.name))
		return obj

	def inspect(self):
		d=self.dialog
		self.require(wx.Window.FindFocus() is d.source,"initial source focus")
		for field in ("day","month","year"):
			obj=self.obj(d.entries[field])
			self.require(bool(obj.name),field+" has native accessible name")
			self.require(obj.value==d.entries[field].GetValue(),field+" has native numeric value")
			self.require(obj.role is controlTypes.Role.EDITABLETEXT,field+" native editable role")
		self.require(not d.info.AcceptsFocus(),"reference text has no tab stop")
		self.require(not d.advanced_button.IsEnabled(),"advanced action disabled")
		d.entries["month"].SetValue("9")
		self.require(d.texts.month(d.model.source,9) in self.obj(d.entries["month"]).name,
			"month name exposed in native MSAA")
		d.entries["month"].SetValue("4")
		d.entries["day"].SetFocus()
		wx.CallLater(400,lambda:self.guard(self.navigation))

	def navigation(self):
		self.result["speechBeforeArrow"]=len(self.result["speech"])
		entry=self.dialog.entries["day"]
		event=wx.KeyEvent(wx.wxEVT_KEY_DOWN);event.KeyCode=wx.WXK_UP;event.SetEventObject(entry)
		entry.GetEventHandler().ProcessEvent(event)
		self.require(entry.GetValue()=="2","native field increments without changing focus")
		self.require(wx.Window.FindFocus() is entry,"arrow preserves focus")
		wx.CallLater(700,lambda:self.guard(self.after_navigation))

	def after_navigation(self):
		segment=self.result["speech"][self.result["speechBeforeArrow"]:]
		self.result["arrowSpeech"]=segment
		self.require(any("2" in " ".join(line) for line in segment),"new value submitted to real speech pipeline")
		self.require(sum(1 for line in segment if " ".join(line).strip()=="2")==1,
			"one explicit value utterance per arrow")
		d=self.dialog
		d._fill_today()
		d._convert()
		self.require(len(self.results)==1,"real conversion service reached from dialog")
		r=self.results[0].converted
		self.require((r.year,r.month,r.day)==(2026,9,12),"reference result correct")
		d.entries["year"].SetValue("365");d._convert()
		self.require(bool(self.errors),"old year produces accessible translated error")
		self.require(wx.Window.FindFocus() is d.entries["year"],"error restores year focus")
		self.require(d.entries["year"].GetStringSelection()=="365","error selects invalid input")
		d.source.SetSelection(1);d._source_changed(None)
		self.require(d.target.GetStringSelection()==d.texts.gettext("Hijri"),"target synchronized")
		self.require(d.values()==dict(day="12",month="9",year="2026"),"source reset uses today")
		self.result["monthAfterSourceChange"]=self.obj(d.entries["month"]).name
		self.require(d.texts.month(d.model.source,9) in self.result["monthAfterSourceChange"],"civil month name updated")
		d._convert()
		self.require(self.results[-1].converted.year==1448,"inverse conversion correct")
		d._close();self.dialog=None
		self.opener.SetFocus()
		wx.CallLater(400,lambda:self.guard(self.closed))

	def closed(self):
		self.require(wx.Window.FindFocus() is self.opener,"opener can regain focus")
		self.result["passed"]=True
		self.finish()

	def finish(self):
		if self.recording:
			from speech.extensions import pre_speech
			pre_speech.unregister(self.record);self.recording=False
		for window in (self.dialog,self.frame):
			if window and not window.IsBeingDeleted():window.Destroy()
		(self.profile/"live-result.json").write_text(json.dumps(self.result,ensure_ascii=False,indent=2),encoding="utf-8")
		wx.CallLater(300,core.triggerNVDAExit)
