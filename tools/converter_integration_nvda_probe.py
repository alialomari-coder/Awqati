"""Actual source-loaded NVDA integration on an owned private desktop.

InputManager dispatch is real; gestures are constructed programmatically.
MSAA objects are real. This does not claim physical keys or human listening.
"""
import ctypes
from ctypes import wintypes
import importlib
import json
from pathlib import Path
import time
import traceback
import core
import globalPluginHandler
import globalVars
import inputCore
import keyboardHandler
import languageHandler
import scriptHandler
import versionInfo
import wx


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self.profile = Path(globalVars.appArgs.configPath)
		if not self.profile.name.startswith('task3-live-task5-'):
			raise RuntimeError('Task5 private profile required')
		self.result = dict(version=versionInfo.version, language=languageHandler.getLanguage(), checks=[], objects=[],
			openings=[], timings=[], layouts=[], passed=False, scope='Real NVDA InputManager, wx modal and MSAA on private desktop; programmatic gestures, no physical keys or human listening')
		self.frame = self.host = None
		self.originals = {}
		wx.CallLater(3000, lambda: self.guard(self.begin))

	def require(self, value, label):
		if not value:
			raise AssertionError(label)
		self.result['checks'].append(label)

	def guard(self, callback):
		if self.result.get('error'):
			return
		try:
			callback()
		except Exception:
			self.result['error'] = traceback.format_exc()
			self.finish()

	def obj(self, control):
		from NVDAObjects.IAccessible import getNVDAObjectFromEvent
		obj = getNVDAObjectFromEvent(control.GetHandle(), -4, 0)
		self.require(obj is not None, 'real NVDA object exists')
		self.result['objects'].append(dict(name=obj.name, value=obj.value, role=obj.role.name))
		return obj

	def begin(self):
		import systemUtils
		self.require(systemUtils._getDesktopName().startswith('AwqatiTask3_'), 'private desktop verified before input')
		self.plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
		self.control = self.plugin._converter
		self.require(self.control is not None and self.plugin._runtime is not None, 'real Awqati composition loaded')
		self.module = self.plugin.__module__
		self.prefix = self.module.rsplit('.nvda_adapter.', 1)[0]
		self.adapter = importlib.import_module(self.prefix + '.nvda_adapter.calendar_converter_control')
		for name in ('CalendarConverterDialog', 'AdvancedConverterDialog'):
			kind = getattr(self.adapter, name)
			self.originals[name] = kind
			def factory(*args, _kind=kind, _name=name, **kwargs):
				self.result['openings'].append(dict(kind=_name, at=time.perf_counter()))
				return _kind(*args, **kwargs)
			setattr(self.adapter, name, factory)
		self.frame = wx.Frame(None, title='Awqati task5 private integration')
		self.opener = wx.Button(self.frame, label='Return focus here')
		self.frame.Show()
		self.opener.SetFocus()
		self.flow = self.scenarios()
		self.advance()

	def advance(self):
		try:
			delay = next(self.flow)
		except StopIteration:
			self.result['passed'] = True
			self.finish()
			return
		wx.CallLater(delay, lambda: self.guard(self.advance))

	def bind(self, key):
		identifier = 'kb:' + key
		inputCore.manager.userGestureMap.add(identifier, self.module, 'GlobalPlugin', 'openDateConverter')

	def unbind(self, key):
		inputCore.manager.userGestureMap.remove('kb:' + key, self.module, 'GlobalPlugin', 'openDateConverter')

	def send(self, key):
		gesture = keyboardHandler.KeyboardInputGesture.fromName(key)
		self.require(scriptHandler.findScript(gesture) == self.plugin.script_openDateConverter, 'current InputManager binding ' + key)
		inputCore.manager.executeGesture(gesture)

	def inspect_dialog(self, advanced, label):
		self.require(len(self.control.dialogs) == 1, label + ': exactly one root modal')
		d = self.control.dialogs[0]
		self.require(isinstance(d, self.originals['AdvancedConverterDialog' if advanced else 'CalendarConverterDialog']), label + ': correct mode')
		self.require(wx.Window.FindFocus() is d.source, label + ': initial source focus')
		for control in (d.source, d.target, *d.entries.values(), d.today_button, d.convert_button, d.close_button):
			self.require(bool(self.obj(control).name), label + ': actual accessible name ' + control.GetName())
		self.require(self.obj(d.close_button).name == d.texts.gettext('Close'), label + ': localized close')
		controls = [d.source, d.target] + ([d.method] if advanced else []) + list(d.entries.values()) + [d.today_button, d.convert_button] + ([] if advanced else [d.advanced_button]) + [d.close_button]
		controls[0].SetFocus()
		for control in controls[1:]:
			wx.Window.FindFocus().Navigate()
			self.require(wx.Window.FindFocus() is control, label + ': Tab ' + control.GetName())
		for control in reversed(controls[:-1]):
			wx.Window.FindFocus().Navigate(wx.NavigationKeyEvent.IsBackward)
			self.require(wx.Window.FindFocus() is control, label + ': Shift Tab ' + control.GetName())
		before = d.values()
		self.control.show(not advanced)
		self.require(len(self.control.dialogs) == 1 and d.values() == before, label + ': open request keeps existing mode and fields')
		d._close()

	def case(self, key, count, label):
		scriptHandler.clearLastScript()
		start = len(self.result['openings'])
		stamp = time.perf_counter()
		for index in range(count):
			self.send(key)
			yield 80
			self.require(not self.control.dialogs and len(self.result['openings']) == start, label + ': no premature dialog ' + str(index))
		yield 500
		self.require(len(self.result['openings']) == start + 1, label + ': only one window created')
		opened = self.result['openings'][-1]
		self.result['timings'].append(dict(case=label, fromFirstMs=round((opened['at'] - stamp) * 1000), count=count))
		self.inspect_dialog(count > 1, label)
		yield 180
		self.require(wx.Window.FindFocus() is self.opener, label + ': focus restored to opener')

	def scenarios(self):
		yield 300
		self.require(self.plugin.script_openDateConverter.__doc__ == ('فتح محوّل التاريخ' if self.result['language'].startswith('ar') else 'Open date converter'), 'localized Input Gestures command name')
		self.require(self.plugin.script_openDateConverter.category == ('أوقاتي' if self.result['language'].startswith('ar') else 'Awqati'), 'localized Input Gestures category')
		all_bindings = list(self.plugin.getScriptGestureMap().get(self.plugin.script_openDateConverter, [])) if hasattr(self.plugin, 'getScriptGestureMap') else []
		self.require(not all_bindings, 'converter has no default gesture')
		key = 'NVDA+shift+f9'
		self.bind(key)
		yield from self.case(key, 1, 'single')
		yield from self.case(key, 2, 'double')
		yield from self.case(key, 6, 'rapid six presses')
		yield from self.case(key, 1, 'separated single')
		# Remove while a single is pending: the delayed callback must re-resolve.
		start = len(self.result['openings'])
		self.send(key)
		yield 80
		self.unbind(key)
		yield 600
		self.require(len(self.result['openings']) == start, 'removing assigned shortcut cancels pending open')
		self.require(scriptHandler.findScript(keyboardHandler.KeyboardInputGesture.fromName(key)) != self.plugin.script_openDateConverter, 'removed shortcut no longer resolves to converter')
		key = 'NVDA+control+shift+f10'
		self.bind(key)
		yield from self.case(key, 2, 'reassigned shortcut')
		# Thread-only HKL changes on the test desktop, restored in finally.
		user = ctypes.WinDLL('user32')
		user.GetKeyboardLayout.restype = wintypes.HANDLE
		user.ActivateKeyboardLayout.argtypes = [wintypes.HANDLE, wintypes.UINT]
		user.ActivateKeyboardLayout.restype = wintypes.HANDLE
		user.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(wintypes.HANDLE)]
		layouts = (wintypes.HANDLE * 32)()
		count = user.GetKeyboardLayoutList(32, layouts)
		original = user.GetKeyboardLayout(0)
		try:
			for layout in list(layouts)[:count]:
				lang = int(layout) & 0xffff
				if lang & 0x3ff not in (1, 9):
					continue
				user.ActivateKeyboardLayout(layout, 0)
				self.result['layouts'].append(hex(lang))
				yield from self.case(key, 2, 'layout ' + hex(lang))
		finally:
			user.ActivateKeyboardLayout(original, 0)
		self.test_key = key
		wx.CallLater(180, lambda: self.guard(self.family_basic))
		self.control.show(False, self.frame)
		self.require(not self.control.dialogs, 'closing converter family releases all tracked dialogs')
		focus = wx.Window.FindFocus()
		self.result['familyFocusAtModalReturn'] = focus.GetName() if focus else None
		# Let wx finish queued native modal-destruction/focus events before
		# inspecting the final focus, as the other close scenarios already do.
		yield 180
		self.require(wx.Window.FindFocus() is self.opener, 'converter family restores external opener')
		# Real settings panel, its buttons and unsaved calendar draft.
		panel_module = importlib.import_module(self.prefix + '.nvda_adapter.settings_panel')
		self.host = wx.Dialog(self.frame, title='Task5 settings host')
		self.panel = panel_module.AwqatiSettingsPanel(self.host)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.panel, 1, wx.EXPAND)
		self.host.SetSizerAndFit(sizer)
		self.panel.section_choice.SetSelection(2)
		self.panel._on_section(wx.CommandEvent())
		self.host.Show()
		yield 300
		self.require(self.panel.section_choice.GetString(2) == ('التقويم' if self.result['language'].startswith('ar') else 'Calendar'), 'calendar section renamed without changing identity')
		self.require(self.panel._draft.settings.calendar.hijri_adjustment_days == 2, 'existing personal correction preserved in settings')
		for advanced, name in ((False, 'calendar.converter'), (True, 'calendar.advancedConverter')):
			button = self.panel._controls[name]
			self.require(self.obj(button).name == button.GetLabel(), 'actual localized settings button ' + name)
			button.SetFocus()
			wx.CallLater(220, lambda mode=advanced: self.guard(lambda: self.inspect_dialog(mode, 'settings ' + str(mode))))
			event = wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId())
			event.SetEventObject(button)
			button.GetEventHandler().ProcessEvent(event)
			self.require(wx.Window.FindFocus() is button, 'settings button focus restored')
		self.panel.onDiscard()
		self.host.Destroy()
		self.host = None
		self.opener.SetFocus()
		# Real composition's provider is shared and no adjustment enters service.
		self.require(self.control.service._ummalqura is self.control.lunar if hasattr(self.control.service, '_ummalqura') else self.control.service.ummalqura is self.control.lunar, 'service uses active lunar provider')
		from datetime import date
		service_module = importlib.import_module(self.prefix + '.application.historical_conversion')
		converted = self.control.service.convert(service_module.ConversionCalendar.GREGORIAN, service_module.ConversionCalendar.HIJRI,
			year=2026, month=9, day=12, hijri_method=service_module.HijriMethod.UMM_AL_QURA)
		self.require(converted.converted.day == 1 and converted.converted.month == 4, 'personal +2 correction is absent from actual integrated service')
		self.send(key)
		yield 80
		start = len(self.result['openings'])
		self.control.close()
		yield 650
		self.require(len(self.result['openings']) == start, 'termination cancels pending shortcut')
		self.require(self.plugin._content.primary_date(self.plugin._language()), 'other Awqati date command remains usable')

	def family_basic(self):
		d = self.control.dialogs[0]
		d.convert_button.SetFocus()
		wx.CallLater(150, lambda: self.guard(self.family_result))
		d._convert()
		self.require(wx.Window.FindFocus() is d.convert_button, 'shared result restores basic convert button')
		d.advanced_button.SetFocus()
		wx.CallLater(180, lambda: self.guard(self.family_advanced))
		d._advanced(None)
		self.require(wx.Window.FindFocus() is d.advanced_button, 'nested advanced restores basic advanced button')
		self.require(len(self.control.dialogs) == 1, 'nested advanced fully released')
		d._close()

	def family_result(self):
		kind = importlib.import_module(self.prefix + '.nvda_adapter.conversion_result_dialog').ConversionResultDialog
		r = next(w for w in wx.GetTopLevelWindows() if isinstance(w, kind) and w.IsModal())
		self.require(wx.Window.FindFocus() is r.output, 'integrated result focuses accessible text')
		self.require(bool(self.obj(r.output).value), 'integrated result actual NVDA text value')
		self.active_result = r
		self.opening_count = len(self.result['openings'])
		scriptHandler.clearLastScript()
		self.send(self.test_key)
		wx.CallLater(700, lambda: self.guard(self.family_result_after_gesture))

	def family_result_after_gesture(self):
		self.require(len(self.result['openings']) == self.opening_count, 'shortcut during result creates no extra converter')
		self.require(wx.Window.FindFocus() is self.active_result.output, 'shortcut preserves active result focus')
		self.active_result._close()

	def family_advanced(self):
		self.require(len(self.control.dialogs) == 2, 'basic button opens one owned advanced child')
		d = self.control.dialogs[-1]
		before = d.values()
		self.control.show(False)
		self.require(len(self.control.dialogs) == 2 and d.values() == before, 'open request during nested advanced preserves family and date')
		self.require(wx.Window.FindFocus() is d.source, 'nested advanced remains focused')
		d._close()

	def finish(self):
		if hasattr(self, 'control'):
			self.control.close()
		if hasattr(self, 'adapter'):
			for name, original in self.originals.items():
				setattr(self.adapter, name, original)
		for window in (self.host, self.frame):
			if window and not window.IsBeingDeleted():
				window.Destroy()
		(self.profile / 'live-result.json').write_text(json.dumps(self.result, ensure_ascii=False, indent=2), encoding='utf-8')
		wx.CallLater(300, core.triggerNVDAExit)
