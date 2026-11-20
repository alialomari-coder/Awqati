"""Independent advanced dialog; no registration or global gesture side effects."""
import wx

from .converter_dialog_base import ConverterDialogBase
from ..application.historical_conversion import ConversionCalendar as C, HijriMethod


class AdvancedConverterDialog(ConverterDialogBase):
	advanced_mode = True

	def _enable_method(self):
		self.method.Enable(C.HIJRI in (self.model.source, self.model.target))

	def _source_changed(self, event):
		self.model.source = self.calendars[self.source.GetSelection()]
		if self.model.target is self.model.source:
			self.model.target = next(c for c in self.calendars if c is not self.model.source)
			self.target.SetSelection(self.targets.index(self.model.target))
		self._enable_method()
		for entry in self.entries.values():
			entry.ChangeValue("")
		self._changed("month")
		if self._fill_today():
			self.announce(self.texts.gettext("Convert to: {calendar}. The date fields have been reset to today.").format(
				calendar=self.target.GetStringSelection()))

	def _target_changed(self, event):
		selected = self.targets[self.target.GetSelection()]
		if selected is self.model.source:
			self.target.SetSelection(self.targets.index(self.model.target))
			self.announce(self.texts.gettext("The target must differ from the source: {calendar}.").format(
				calendar=self.target.GetStringSelection()))
		else:
			self.model.target = selected
		self._enable_method()

	def _method_changed(self, event):
		self.model.method = HijriMethod.IIC if self.method.GetSelection() == 0 else HijriMethod.UMM_AL_QURA
		# Keep typed dates intact. Only Today/source changes repopulate them.


def show_advanced_converter(parent, service, lunar, today, **options):
	previous = wx.Window.FindFocus()
	dialog = AdvancedConverterDialog(parent, service, lunar, today, **options)
	try:
		return dialog.ShowModal()
	finally:
		dialog.Destroy()
		if previous and not previous.IsBeingDeleted():
			previous.SetFocus()
