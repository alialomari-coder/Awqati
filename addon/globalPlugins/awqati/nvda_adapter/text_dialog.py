"""One keyboard-first selectable text window for Awqati reports."""

from __future__ import annotations

from typing import Callable
import addonHandler
import languageHandler

from .settings_sections import is_rtl_language

addonHandler.initTranslation()
_: Callable[[str], str]


class SelectableTextDialog:
	_instance = None

	@classmethod
	def show(cls, parent, title: str, content: str) -> None:
		import wx
		if cls._instance is not None:
			cls._instance.Raise()
			cls._instance.text.SetFocus()
			return
		opener = wx.Window.FindFocus()
		dialog = cls._instance = wx.Dialog(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		dialog.SetLayoutDirection(wx.Layout_RightToLeft
			if is_rtl_language(languageHandler.getLanguage()) else wx.Layout_LeftToRight)
		# Native MSAA edit names come from the preceding static label on Windows;
		# wx's name argument alone does not expose an accessible name to NVDA.
		label = wx.StaticText(dialog, label=title)
		dialog.text = wx.TextCtrl(dialog, value=content, style=wx.TE_MULTILINE | wx.TE_READONLY,
			name=title)
		close = wx.Button(dialog, wx.ID_CLOSE, label=_("Close"))
		if getattr(cls, "copy_report", False):
			arabic = languageHandler.getLanguage().startswith("ar")
			copy = dialog.copy_button = wx.Button(dialog, label="نسخ التقرير" if arabic else "Copy report")
			copy.MoveBeforeInTabOrder(close)
			def copy_text(event):
				if not wx.TheClipboard.Open():
					wx.MessageBox("تعذر فتح الحافظة؛ يرجى المحاولة مجددًا." if arabic else "Could not open the clipboard; please try again.", dialog.GetTitle(), wx.OK | wx.ICON_ERROR, dialog)
					return
				try:
					success = wx.TheClipboard.SetData(wx.TextDataObject(dialog.text.GetValue()))
					if success: wx.TheClipboard.Flush()
				finally:
					wx.TheClipboard.Close()
				if not success:
					wx.MessageBox("تعذر نسخ التقرير؛ يرجى المحاولة مجددًا." if arabic else "Could not copy the report; please try again.", dialog.GetTitle(), wx.OK | wx.ICON_ERROR, dialog)
			copy.Bind(wx.EVT_BUTTON, copy_text)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
		sizer.Add(dialog.text, 1, wx.ALL | wx.EXPAND, 12)
		if getattr(cls, "copy_report", False):
			sizer.Add(copy, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT, 12)
		sizer.Add(close, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT, 12)
		dialog.SetSizer(sizer)
		dialog.SetSize((620, 480))
		def finish(event=None):
			if cls._instance is dialog:
				cls._instance = None
			dialog.Destroy()
			def restore_focus():
				if opener and not opener.IsBeingDeleted() and opener.IsShownOnScreen():
					opener.GetTopLevelParent().Raise()
					opener.SetFocus()
			wx.CallAfter(restore_focus)
		close.Bind(wx.EVT_BUTTON, finish)
		dialog.Bind(wx.EVT_CLOSE, finish)
		dialog.Bind(wx.EVT_CHAR_HOOK, lambda event: finish() if event.GetKeyCode() == wx.WXK_ESCAPE else event.Skip())
		dialog.Show()
		dialog.text.SetFocus()
