"""Shared native date-entry dialog shell. Inject active provider/service/clock.

The basic mode opens the independent advanced dialog and shared result modal.
No plugin registration, settings reads or global gestures.
"""
import wx

from .calendar_converter_model import SimpleConversionModel, EntryError, parse_number
from .calendar_converter_text import ConverterText
from ..application.historical_conversion import ConversionCalendar as C


from .converter_announce import _nvda_announce


class DateNumberEntry(wx.TextCtrl):
	"""Native editable text, with narrowly scoped numeric navigation."""
	def __init__(self, parent, field, label, navigate, changed, announce):
		super().__init__(parent, name=label, style=wx.TE_PROCESS_ENTER)
		self.field = field
		self._navigate, self._changed, self._announce = navigate, changed, announce
		self.Bind(wx.EVT_KEY_DOWN, self._key)
		self.Bind(wx.EVT_SET_FOCUS, self._focus)
		self.Bind(wx.EVT_TEXT, lambda event: self._changed(self.field))

	def _focus(self, event):
		self.SelectAll()
		event.Skip()

	def _key(self, event):
		keys = {wx.WXK_UP: "up", wx.WXK_DOWN: "down", wx.WXK_PAGEUP: "pageup",
			wx.WXK_PAGEDOWN: "pagedown", wx.WXK_HOME: "home", wx.WXK_END: "end",
			wx.WXK_LEFT: "left", wx.WXK_RIGHT: "right"}
		key = keys.get(event.GetKeyCode())
		if key is None or event.HasAnyModifiers():
			event.Skip()
			return
		if key in ("left", "right"):
			return
		try:
			value = self._navigate(self.field, self.GetValue(), key)
		except EntryError as error:
			self._announce(error)
			return
		self.ChangeValue(value)
		self.SelectAll()
		self._changed(self.field)
		# Native text events communicate the edited value to NVDA. The dialog
		# supplies a single value announcement for this intercepted key.
		self._announce(self.field)


class ConverterDialogBase(wx.Dialog):
	advanced_mode = False

	def __init__(self, parent, service, lunar, today, *, language=None,
			announce=None, show_result=None, show_error=None, on_advanced=None):
		if language is None:
			try:
				import languageHandler
				language = languageHandler.getLanguage()
			except ImportError:
				language = "en"
		self.texts = ConverterText(language)
		_ = self.texts.gettext
		super().__init__(parent, title=_("Advanced conversion" if self.advanced_mode else "Date converter"), style=wx.DEFAULT_DIALOG_STYLE)
		self.SetLayoutDirection(wx.Layout_RightToLeft if self.texts.arabic else wx.Layout_LeftToRight)
		if self.advanced_mode:
			from .advanced_converter_model import AdvancedConversionModel
			self.model = AdvancedConversionModel(service, lunar, today)
		else:
			self.model = SimpleConversionModel(service, lunar, today)
		self.announce = announce or _nvda_announce
		self.show_result = show_result or self._message_result
		self.show_error = show_error or self._message_error
		self.on_advanced = on_advanced or getattr(self, "_open_advanced", None)
		self._closed = False
		self._initial_error = None
		outer = wx.BoxSizer(wx.VERTICAL)
		self.labels = {}
		def label(text):
			item = wx.StaticText(self, label=text)
			outer.Add(item, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
			return item
		label(_("Convert from"))
		self.calendars = [C.HIJRI, C.GREGORIAN, C.JULIAN] if self.advanced_mode else [C.HIJRI, C.GREGORIAN]
		self.source = wx.Choice(self, choices=[self.texts.calendar(c) for c in self.calendars], name=_("Convert from"))
		self.source.SetSelection(0)
		outer.Add(self.source, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
		label(_("Convert to"))
		self.targets = self.calendars if self.advanced_mode else [C.GREGORIAN, C.HIJRI]
		self.target = wx.Choice(self, choices=[self.texts.calendar(c) for c in self.targets], name=_("Convert to"))
		self.target.SetSelection(self.targets.index(C.GREGORIAN))
		outer.Add(self.target, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
		if self.advanced_mode:
			label(_("Hijri calculation method"))
			self.method = wx.Choice(self, choices=[_("Historical calculation IIc"), _("Umm al-Qura")], name=_("Hijri calculation method"))
			self.method.SetSelection(0)
			outer.Add(self.method, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
			self.method.Bind(wx.EVT_CHOICE, self._method_changed)
		self.entries = {}
		for field, title in (("day", _("Day")), ("month", _("Month")), ("year", _("Year"))):
			self.labels[field] = label(title)
			entry = DateNumberEntry(self, field, title, self._navigate, self._changed, self._entry_announcement)
			self.entries[field] = entry
			outer.Add(entry, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)
			entry.Bind(wx.EVT_TEXT_ENTER, self._convert)
		self.info = label(_("Select the calendars and method, then convert." if self.advanced_mode else "Hijri reference: Umm al-Qura. Gregorian reference: Gregorian."))
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.today_button = wx.Button(self, label=_("Today"))
		self.convert_button = wx.Button(self, label=_("Convert"))
		self.advanced_button = None if self.advanced_mode else wx.Button(self, label=_("Advanced..."))
		self.close_button = wx.Button(self, wx.ID_CANCEL, label=_("Close"))
		for button in (self.today_button, self.convert_button, self.advanced_button, self.close_button):
			if button:
				buttons.Add(button, 0, wx.ALL, 5)
		outer.Add(buttons, 0, wx.ALL | wx.ALIGN_CENTER, 5)
		self.SetSizerAndFit(outer)
		self.convert_button.SetDefault()
		self.source.Bind(wx.EVT_CHOICE, self._source_changed)
		self.target.Bind(wx.EVT_CHOICE, self._target_changed)
		self.today_button.Bind(wx.EVT_BUTTON, self._today)
		self.convert_button.Bind(wx.EVT_BUTTON, self._convert)
		if self.advanced_button:
			self.advanced_button.Bind(wx.EVT_BUTTON, self._advanced)
		self.close_button.Bind(wx.EVT_BUTTON, self._close)
		self.Bind(wx.EVT_CLOSE, self._close)
		self.Bind(wx.EVT_CHAR_HOOK, self._char_hook)
		self._fill_today(initial=True)
		self.Bind(wx.EVT_SHOW, self._shown)
		self.CentreOnParent()

	def values(self):
		return {field: control.GetValue() for field, control in self.entries.items()}

	def _shown(self, event):
		event.Skip()
		if event.IsShown():
			wx.CallAfter(self._initial_focus)
			if self._initial_error:
				error, self._initial_error = self._initial_error, None
				wx.CallAfter(self._report_error, error)

	def _initial_focus(self):
		if not self._closed:
			self.source.SetFocus()

	def _changed(self, field):
		if field == "month":
			_ = self.texts.gettext
			try:
				month = self.texts.month(self.model.source, parse_number(self.entries["month"].GetValue(), "month"))
			except EntryError:
				month = ""
			name = _("Month") + (": " + month if month else "")
			self.labels["month"].SetLabel(name)
			self.entries["month"].SetName(name)
			self.Layout()

	def _navigate(self, field, text, key):
		return self.model.navigate(field, text, key, self.values())

	def _entry_announcement(self, value):
		if isinstance(value, EntryError):
			self.announce(self.texts.error(value))
		else:
			entry = self.entries[value]
			self.announce(entry.GetValue() + (" " + self.texts.month(self.model.source,
				parse_number(entry.GetValue(), "month")) if value == "month" else ""))

	def _fill_today(self, initial=False):
		try:
			values = self.model.current()
		except EntryError as error:
			if initial:
				self._initial_error = error
			else:
				self._report_error(error)
			return False
		for field, value in values.items():
			self.entries[field].ChangeValue(value)
		self._changed("month")
		return True

	def _today(self, event):
		if self._fill_today():
			self.announce(self.texts.gettext("The date fields have been reset to today."))

	def _source_changed(self, event):
		self.model.source = C.HIJRI if self.source.GetSelection() == 0 else C.GREGORIAN
		self.target.SetSelection(self.source.GetSelection())
		# Old numeric fields must never be reinterpreted after a failed today load.
		for entry in self.entries.values():
			entry.ChangeValue("")
		self._changed("month")
		if self._fill_today():
			self.announce(self.texts.gettext("Convert to: {calendar}. The date fields have been reset to today.").format(
				calendar=self.target.GetStringSelection()))

	def _target_changed(self, event):
		# Native choice keeps both names visible; choosing the same source is
		# rejected immediately without switching the source or losing inputs.
		if self.target.GetSelection() != self.source.GetSelection():
			self.target.SetSelection(self.source.GetSelection())
			self.announce(self.texts.gettext("The target must differ from the source: {calendar}.").format(
				calendar=self.target.GetStringSelection()))

	def _convert(self, event=None):
		try:
			result = self.model.convert(self.values())
		except EntryError as error:
			self._report_error(error)
			return
		previous = wx.Window.FindFocus()
		self.show_result(self, result)
		if previous and not self._closed:
			previous.SetFocus()

	def _report_error(self, error):
		if self._closed:
			return
		self.show_error(self, self.texts.error(error))
		entry = self.entries.get(error.field, self.entries["day"])
		entry.SetFocus()
		entry.SelectAll()

	def _message_result(self, parent, result):
		from .conversion_result_dialog import show_conversion_result
		final = show_conversion_result(parent, result, texts=self.texts, announce=self.announce)
		if final != result:
			self._apply_result(final)

	def _apply_result(self, result):
		# Match the last displayed operation, without triggering today's-date handlers.
		self.model.source = result.original.calendar
		self.source.SetSelection(self.calendars.index(self.model.source))
		self.target.SetSelection(self.targets.index(result.converted.calendar))
		if self.advanced_mode:
			self.model.target = result.converted.calendar
			if result.hijri_method is not None:
				from ..application.historical_conversion import HijriMethod
				self.model.method = result.hijri_method
				self.method.SetSelection(0 if result.hijri_method is HijriMethod.IIC else 1)
			self._enable_method()
		for field, entry in self.entries.items():
			entry.ChangeValue(str(getattr(result.original, field)))
		self._changed("month")

	def _message_error(self, parent, message):
		self._message(parent, message, self.texts.gettext("Check the date"), wx.ICON_ERROR)

	def _message(self, parent, message, title, icon):
		# Native stock labels follow the Windows locale, which can differ from
		# NVDA's language. Set the existing OK button explicitly, not globally.
		dialog = wx.MessageDialog(parent, message, title, wx.OK | icon)
		try:
			dialog.SetOKLabel(self.texts.gettext("OK"))
			dialog.ShowModal()
		finally:
			dialog.Destroy()

	def _advanced(self, event):
		if self.on_advanced:
			previous = wx.Window.FindFocus()
			self.on_advanced(self)
			if previous and not previous.IsBeingDeleted():
				previous.SetFocus()

	def _char_hook(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
			self._close()
		else:
			event.Skip()

	def _close(self, event=None):
		if self._closed:
			return
		self._closed = True
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
		else:
			self.Destroy()

