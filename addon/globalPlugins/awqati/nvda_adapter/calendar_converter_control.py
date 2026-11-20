"""NVDA integration only: deferred gestures and one owned converter family."""
import wx

from ..application.historical_conversion import HistoricalConversionService
from .calendar_converter_dialog import CalendarConverterDialog
from .advanced_converter_dialog import AdvancedConverterDialog


class ConverterPresses:
	"""Settle a native NVDA repeat sequence before entering any modal loop.

	Keep only immutable gesture identifiers. Re-resolve the binding at expiry,
	so removal/reassignment in Input Gestures invalidates a pending request.
	"""
	def __init__(self, schedule, timeout, resolve, open_window):
		self.schedule, self.timeout = schedule, timeout
		self.resolve, self.open_window = resolve, open_window
		self.pending = None
		self.generation = 0
		self.closed = False

	def cancel(self):
		self.generation += 1
		if self.pending:
			self.pending[0].Stop()
		self.pending = None

	def press(self, identifiers, repeat):
		if self.closed:
			return
		identifiers = tuple(identifiers)
		advanced = bool(self.pending and self.pending[1] == identifiers and repeat > 0)
		self.cancel()
		generation = self.generation
		def settled():
			if self.closed or generation != self.generation:
				return
			self.pending = None
			if self.resolve(identifiers):
				self.open_window(advanced)
		# Honor NVDA's own configured timeout; default is short. The guard lets
		# queued script callbacks finish before a modal steals keyboard focus.
		timer = self.schedule(max(1, int(self.timeout())) + 30, settled)
		self.pending = (timer, identifiers)

	def close(self):
		self.closed = True
		self.cancel()


class CalendarConverterControl:
	def __init__(self, settings, now, zones, lunar, language, announce, main_frame):
		self.settings, self.now, self.zones = settings, now, zones
		self.lunar = lunar
		self.service = HistoricalConversionService(lunar)
		self.language, self.announce, self.main_frame = language, announce, main_frame
		self.dialogs = []
		self.closed = False
		self.presses = None

	def today(self):
		# Read saved runtime settings each time, never the unsaved settings draft.
		stored = self.settings.runtime_settings.location
		instant = self.now.now().value
		if stored is None:
			return instant.astimezone().date()
		return instant.astimezone(self.zones.get_timezone(stored.location.timezone_id)).date()

	def _owned_modals(self):
		def owned(window):
			while window:
				if window in self.dialogs:
					return True
				window = window.GetParent()
			return False
		return [w for w in wx.GetTopLevelWindows()
			if isinstance(w, wx.Dialog) and w.IsModal() and owned(w)]

	def show(self, advanced=False, parent=None, *, nested=False):
		if self.closed:
			return
		if self.presses:
			self.presses.cancel()
		if self.dialogs and not nested:
			# A result or native error may own the active modal. Never focus its
			# disabled parent and never switch modes while a date is being edited.
			modals = self._owned_modals()
			window = next((w for w in reversed(modals) if w.IsEnabled()), self.dialogs[-1])
			window.Raise()
			if not wx.Window.FindFocus() or not wx.Window.FindFocus().IsEnabled():
				window.SetFocus()
			return
		previous = wx.Window.FindFocus()
		parent = parent or (wx.GetTopLevelParent(previous) if previous else self.main_frame)
		popup = parent is self.main_frame
		if popup:
			self.main_frame.prePopup()
		dialog = None
		try:
			kind = AdvancedConverterDialog if advanced else CalendarConverterDialog
			options = dict(language=self.language(), announce=self.announce)
			if not advanced:
				options['on_advanced'] = lambda owner: self.show(True, owner, nested=True)
			dialog = kind(parent, self.service, self.lunar, self.today, **options)
			self.dialogs.append(dialog)
			dialog.ShowModal()
		finally:
			if dialog:
				self.dialogs.remove(dialog)
				dialog.Destroy()
			if popup:
				self.main_frame.postPopup()
			if not self.closed and previous and not previous.IsBeingDeleted() and previous.IsEnabled():
				previous.SetFocus()

	def close(self):
		self.closed = True
		if self.presses:
			self.presses.close()
		# End children before their parents; modal finally blocks own destruction.
		modals = self._owned_modals()
		def depth(window):
			count = 0
			while window:
				count += 1
				window = window.GetParent()
			return count
		for dialog in sorted(modals, key=depth, reverse=True):
			dialog.EndModal(wx.ID_CANCEL)
