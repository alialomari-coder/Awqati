"""Shared result snapshot, accessible text and explicit clipboard ownership."""
import wx

from .advanced_converter_model import reversed_result
from .converter_announce import _nvda_announce


def copy_to_clipboard(text, clipboard=None):
	"""The caller may inject an isolated clipboard; never fall back after failure."""
	clipboard = wx.TheClipboard if clipboard is None else clipboard
	if not clipboard.Open():
		return False
	try:
		return bool(clipboard.SetData(wx.TextDataObject(text)))
	finally:
		clipboard.Close()


class ConversionResultDialog(wx.Dialog):
	def __init__(self, parent, result, *, texts, announce=None, copy_text=None):
		self.result, self.texts = result, texts
		self.announce = announce or _nvda_announce
		self.copy_text = copy_text or copy_to_clipboard
		self._closed = False
		_ = texts.gettext
		super().__init__(parent, title=_("Conversion result"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.SetLayoutDirection(wx.Layout_RightToLeft if texts.arabic else wx.Layout_LeftToRight)
		outer = wx.BoxSizer(wx.VERTICAL)
		self.output = wx.TextCtrl(self, value=texts.result(result), name=_("Conversion result"),
			style=wx.TE_MULTILINE | wx.TE_READONLY, size=(570, 180))
		outer.Add(self.output, 1, wx.ALL | wx.EXPAND, 10)
		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.copy_button = wx.Button(self, label=_("Copy result"))
		self.reverse_button = wx.Button(self, label=_("Reverse conversion"))
		self.close_button = wx.Button(self, wx.ID_CANCEL, label=_("Close"))
		for button in (self.copy_button, self.reverse_button, self.close_button):
			buttons.Add(button, 0, wx.ALL, 5)
		outer.Add(buttons, 0, wx.ALIGN_CENTER | wx.ALL, 5)
		self.SetSizerAndFit(outer)
		self.close_button.SetDefault()
		self.copy_button.Bind(wx.EVT_BUTTON, self._copy)
		self.reverse_button.Bind(wx.EVT_BUTTON, self._reverse)
		self.close_button.Bind(wx.EVT_BUTTON, self._close)
		self.Bind(wx.EVT_CLOSE, self._close)
		self.Bind(wx.EVT_CHAR_HOOK, self._key)
		self.Bind(wx.EVT_SHOW, self._shown)
		self.CentreOnParent()

	def _shown(self, event):
		event.Skip()
		if event.IsShown():
			wx.CallAfter(self._focus_text)

	def _focus_text(self):
		if not self._closed:
			self.output.SetInsertionPoint(0)
			self.output.SetFocus()

	def _copy(self, event=None):
		try:
			success = self.copy_text(self.texts.clipboard_date(self.result.converted))
		except Exception:
			success = False
		self.announce(self.texts.gettext("Result copied." if success else "The result could not be copied. Try again."))

	def _reverse(self, event=None):
		self.result = reversed_result(self.result)
		self.output.ChangeValue(self.texts.result(self.result))
		self.output.SetInsertionPoint(0)
		# Keep button focus for repeated reversal; announce the refreshed result once.
		self.announce(self.output.GetValue())

	def _key(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
			self._close()
		elif event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.HasAnyModifiers() and wx.Window.FindFocus() is self.output:
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


def show_conversion_result(parent, result, **options):
	previous = wx.Window.FindFocus()
	dialog = ConversionResultDialog(parent, result, **options)
	try:
		dialog.ShowModal()
		return dialog.result
	finally:
		dialog.Destroy()
		if previous and not previous.IsBeingDeleted():
			previous.SetFocus()
