"""Basic converter and advanced launcher; the shared shell has no dialog cycle."""
import wx
from .converter_dialog_base import ConverterDialogBase, DateNumberEntry


class CalendarConverterDialog(ConverterDialogBase):
	def _open_advanced(self, parent):
		from .advanced_converter_dialog import show_advanced_converter
		show_advanced_converter(parent, self.model.service, self.model.lunar, self.model.today,
			language="ar" if self.texts.arabic else "en", announce=self.announce)


def show_calendar_converter(parent, service, lunar, today, **options):
	"""Future integration seam; caller owns popup preparation and active provider."""
	previous = wx.Window.FindFocus()
	dialog = CalendarConverterDialog(parent, service, lunar, today, **options)
	try:
		return dialog.ShowModal()
	finally:
		dialog.Destroy()
		if previous and not previous.IsBeingDeleted():
			previous.SetFocus()
