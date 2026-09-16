"""One keyboard-first selectable text window for Awqati reports."""

from __future__ import annotations

from typing import Callable
import addonHandler

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
		dialog = cls._instance = wx.Dialog(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		dialog.text = wx.TextCtrl(dialog, value=content, style=wx.TE_MULTILINE | wx.TE_READONLY,
			name=title)
		close = wx.Button(dialog, wx.ID_CLOSE, label=_("Close"))
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(dialog.text, 1, wx.ALL | wx.EXPAND, 12)
		sizer.Add(close, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT, 12)
		dialog.SetSizer(sizer)
		dialog.SetSize((620, 480))
		def finish(event=None):
			if cls._instance is dialog:
				cls._instance = None
			dialog.Destroy()
		close.Bind(wx.EVT_BUTTON, finish)
		dialog.Bind(wx.EVT_CLOSE, finish)
		dialog.Bind(wx.EVT_CHAR_HOOK, lambda event: finish() if event.GetKeyCode() == wx.WXK_ESCAPE else event.Skip())
		dialog.Show()
		dialog.text.SetFocus()
