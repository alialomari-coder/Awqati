"""Keyboard-accessible task 3.2 dialogs and the static Awqati settings area."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable

import languageHandler
import addonHandler
import wx

from ..application import (
	CustomLocationValidationError,
	LocationSelectionResult,
	LocationSetupService,
	SettingsService,
)
from .settings_sections import is_rtl_language

from ..domain import ClockTime, LocationDetectionFailure, StoredLocation

addonHandler.initTranslation()
_: Callable[[str], str]


@dataclass(slots=True)
class NvdaUiContext:
	settings: SettingsService
	location_setup: LocationSetupService


_context: NvdaUiContext | None = None


def configure(context: NvdaUiContext | None) -> None:
	global _context
	_context = context


def _context_or_raise() -> NvdaUiContext:
	if _context is None:
		raise RuntimeError("Awqati UI has not been configured")
	return _context


def _location_summary(stored: StoredLocation | None) -> str:
	if stored is None:
		return _("No location has been assigned")
	return _("Assigned location: {name}; time zone: {timezone}").format(
		name=stored.location.name,
		timezone=stored.location.timezone_id,
	)


def _detection_message(failure: LocationDetectionFailure | None) -> str:
	return {
		LocationDetectionFailure.DENIED: _("Windows location permission was denied. You can still choose a city or enter a custom location."),
		LocationDetectionFailure.UNAVAILABLE: _("Windows Location is unavailable. You can still choose a city or enter a custom location."),
		LocationDetectionFailure.TIMEOUT: _("Location detection timed out. You can still choose a city or enter a custom location."),
		LocationDetectionFailure.INVALID_COORDINATES: _("Windows returned invalid coordinates. Your previous location was not changed."),
	}.get(failure, _("Location detection failed. Your previous location was not changed."))


class CustomLocationDialog(wx.Dialog):
	def __init__(self, parent: wx.Window, service: LocationSetupService) -> None:
		super().__init__(parent, title=_("Enter a custom location"))
		self.SetLayoutDirection(wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage()) else wx.Layout_LeftToRight)
		self._service = service
		self.location: StoredLocation | None = None
		outer = wx.BoxSizer(wx.VERTICAL)
		grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
		grid.AddGrowableCol(1, 1)
		self.name = wx.TextCtrl(self, name=_("Location name"))
		self.latitude = wx.TextCtrl(self, name=_("Latitude"))
		self.longitude = wx.TextCtrl(self, name=_("Longitude"))
		self.timezone = wx.ComboBox(self, choices=list(service.timezone_ids()), name=_("IANA time zone"))
		for label, control in (
			(_("Location name:"), self.name),
			(_("Latitude:"), self.latitude),
			(_("Longitude:"), self.longitude),
			(_("Time zone:"), self.timezone),
		):
			grid.Add(wx.StaticText(self, label=label), flag=wx.ALIGN_CENTER_VERTICAL)
			grid.Add(control, flag=wx.EXPAND)
		outer.Add(grid, proportion=1, flag=wx.ALL | wx.EXPAND, border=12)
		buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
		if buttons:
			outer.Add(buttons, flag=wx.ALL | wx.EXPAND, border=12)
		self.SetSizerAndFit(outer)
		self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
		self.name.SetFocus()

	def _on_ok(self, event: wx.CommandEvent) -> None:
		try:
			self.location = self._service.custom(
				self.name.GetValue(),
				self.latitude.GetValue(),
				self.longitude.GetValue(),
				self.timezone.GetValue(),
			)
		except CustomLocationValidationError as error:
			wx.MessageBox(
				_("Check this location field and try again."),
				_("Invalid custom location"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			{
				"name": self.name,
				"latitude": self.latitude,
				"longitude": self.longitude,
				"timezone": self.timezone,
			}[error.field].SetFocus()
			return
		self.EndModal(wx.ID_OK)


class LocationControls:
	"""Reusable static location controls; all choices remain pending until save."""

	def __init__(self, parent: wx.Window, sizer: wx.Sizer, service: LocationSetupService,
			current: StoredLocation | None) -> None:
		self.parent = parent
		self.service = service
		self.pending = current
		self.matches = ()
		self._search_generation = 0
		self._search_lock = threading.Lock()
		self.countries = service.countries()
		grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
		grid.AddGrowableCol(1, 1)
		grid.Add(wx.StaticText(parent, label=_("Country:")), flag=wx.ALIGN_CENTER_VERTICAL)
		self.country = wx.Choice(parent, choices=[_(item.name) for item in self.countries], name=_("Country"))
		grid.Add(self.country, flag=wx.EXPAND)
		grid.Add(wx.StaticText(parent, label=_("Search for a city:")), flag=wx.ALIGN_CENTER_VERTICAL)
		self.city_search = wx.TextCtrl(parent, name=_("Search for a city in the selected country"))
		grid.Add(self.city_search, flag=wx.EXPAND)
		grid.Add(wx.StaticText(parent, label=_("City results:")), flag=wx.ALIGN_TOP)
		self.city_results = wx.ListBox(parent, name=_("City search results"))
		grid.Add(self.city_results, flag=wx.EXPAND)
		sizer.Add(grid, proportion=1, flag=wx.ALL | wx.EXPAND, border=8)
		button_row = wx.BoxSizer(wx.HORIZONTAL)
		self.detect_button = wx.Button(parent, label=_("Detect location automatically"))
		self.custom_button = wx.Button(parent, label=_("Enter a custom location"))
		button_row.Add(self.detect_button, flag=wx.RIGHT, border=8)
		button_row.Add(self.custom_button)
		sizer.Add(button_row, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
		sizer.Add(wx.StaticText(parent, label=_("Current assigned location:")), flag=wx.LEFT | wx.RIGHT, border=8)
		self.summary = wx.TextCtrl(parent, value=_location_summary(current), style=wx.TE_READONLY,
			name=_("Current assigned location and time zone"))
		sizer.Add(self.summary, flag=wx.ALL | wx.EXPAND, border=8)
		self.country.Bind(wx.EVT_CHOICE, self._on_country)
		self.city_search.Bind(wx.EVT_TEXT, self._on_search)
		self.city_results.Bind(wx.EVT_LISTBOX, self._on_city)
		self.detect_button.Bind(wx.EVT_BUTTON, self._on_detect)
		self.custom_button.Bind(wx.EVT_BUTTON, self._on_custom)
		selection = 0
		if current is not None and current.country_code:
			selection = next((index for index, item in enumerate(self.countries)
				if item.code == current.country_code), 0)
		self.country.SetSelection(selection if self.countries else wx.NOT_FOUND)

	def _on_country(self, event: wx.CommandEvent) -> None:
		self.city_results.Clear()
		self.matches = ()
		self._search()
		event.Skip()

	def _on_search(self, event: wx.CommandEvent) -> None:
		self._search()
		event.Skip()

	def _search(self) -> None:
		index = self.country.GetSelection()
		query = self.city_search.GetValue().strip()
		self._search_generation += 1
		generation = self._search_generation
		if index == wx.NOT_FOUND or not query:
			self.matches = ()
			self.city_results.Clear()
			return
		code = self.countries[index].code
		threading.Thread(target=self._search_worker, args=(code, query, generation),
			name="AwqatiCitySearch", daemon=True).start()

	def _search_worker(self, country_code: str, query: str, generation: int) -> None:
		with self._search_lock:
			matches = self.service.search(country_code, query)
		wx.CallAfter(self._finish_search, generation, matches)

	def _finish_search(self, generation: int, matches: tuple) -> None:
		if generation != self._search_generation or not self.parent:
			return
		self.matches = matches
		labels = []
		for match in self.matches:
			details = ", ".join(match.subdivisions)
			labels.append(f"{match.location.name} — {details} — {match.location.timezone_id}" if details
				else f"{match.location.name} — {match.location.timezone_id}")
		self.city_results.Set(labels)

	def _on_city(self, event: wx.CommandEvent) -> None:
		index = self.city_results.GetSelection()
		if index != wx.NOT_FOUND:
			match = self.matches[index]
			self.pending = self.service.selected(match.country_code, match.location.location_id)
			self.summary.SetValue(_location_summary(self.pending))
		event.Skip()

	def _on_custom(self, event: wx.CommandEvent) -> None:
		dialog = CustomLocationDialog(self.parent, self.service)
		try:
			if dialog.ShowModal() == wx.ID_OK and dialog.location is not None:
				self.pending = dialog.location
				self.summary.SetValue(_location_summary(self.pending))
		finally:
			dialog.Destroy()
		self.custom_button.SetFocus()
		event.Skip()

	def _on_detect(self, event: wx.CommandEvent) -> None:
		self.detect_button.Disable()
		self.detect_button.SetLabel(_("Detecting location…"))
		threading.Thread(target=self._detect_worker, name="AwqatiLocation", daemon=True).start()
		event.Skip()

	def _detect_worker(self) -> None:
		result = self.service.detect()
		wx.CallAfter(self._finish_detection, result)

	def _finish_detection(self, result: LocationSelectionResult) -> None:
		if not self.parent:
			return
		self.detect_button.Enable()
		self.detect_button.SetLabel(_("Detect location automatically"))
		if result.location is not None:
			self.pending = result.location
			self.summary.SetValue(_location_summary(self.pending))
			wx.MessageBox(_("The detected location is ready. Choose OK or Apply to save it."),
				_("Location detected"), wx.OK | wx.ICON_INFORMATION, self.parent)
		else:
			wx.MessageBox(_detection_message(result.failure), _("Location detection"),
				wx.OK | wx.ICON_WARNING, self.parent)
		self.detect_button.SetFocus()


class FirstRunLocationDialog(wx.Dialog):
	def __init__(self, parent: wx.Window) -> None:
		super().__init__(parent, title=_("Set up the Awqati location"))
		self.SetLayoutDirection(wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage()) else wx.Layout_LeftToRight)
		context = _context_or_raise()
		self._settings = context.settings
		self._draft = context.settings.open_draft()
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(wx.StaticText(self, label=_("Choose a country and city, detect your location explicitly, or enter a custom location. You may cancel without assigning a location.")),
			flag=wx.ALL | wx.EXPAND, border=8)
		self.location_controls = LocationControls(self, outer, context.location_setup, None)
		buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
		if buttons:
			outer.Add(buttons, flag=wx.ALL | wx.EXPAND, border=8)
		self.SetSizerAndFit(outer)
		self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)
		self.location_controls.country.SetFocus()

	def _on_ok(self, event: wx.CommandEvent) -> None:
		if self.location_controls.pending is None:
			wx.MessageBox(_("Choose a city, detect a location, or enter a custom location before continuing."),
				_("Location is required"), wx.OK | wx.ICON_WARNING, self)
			return
		self._draft.settings.location = self.location_controls.pending
		try:
			self._settings.apply(self._draft)
		except Exception as error:
			wx.MessageBox(_("Awqati could not save the location. Your previous settings were preserved."),
				_("Could not save settings"), wx.OK | wx.ICON_ERROR, self)
			return
		self.EndModal(wx.ID_OK)

	def _on_cancel(self, event: wx.CommandEvent) -> None:
		self._draft.discard()
		self.EndModal(wx.ID_CANCEL)


def _parse_clock(value: str) -> ClockTime:
	parts = value.strip().split(":")
	if len(parts) != 2:
		raise ValueError(_("Use time in 24-hour HH:MM format"))
	return ClockTime(int(parts[0]), int(parts[1]))
