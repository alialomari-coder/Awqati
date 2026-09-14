"""Keyboard-accessible task 3.2 dialogs and the static Awqati settings area."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable

import languageHandler
import addonHandler
import wx
import ui as nvda_ui

from ..application import (
	CustomLocationValidationError,
	LocationSelectionResult,
	LocationSetupService,
	SettingsService,
)
from .settings_sections import is_rtl_language
from .timezone_labels import TIMEZONE_LABELS

from ..domain import ClockTime, LocationDetectionFailure, LocationKind, StoredLocation

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
		# Native label association follows sibling creation order, not sizer position.
		for attribute, label in (("name", _("Location name:")),
				("latitude", _("Latitude:")), ("longitude", _("Longitude:"))):
			grid.Add(wx.StaticText(self, label=label), flag=wx.ALIGN_CENTER_VERTICAL)
			control = wx.TextCtrl(self, name=label.rstrip(":"))
			setattr(self, attribute, control)
			grid.Add(control, flag=wx.EXPAND)
		grid.Add(wx.StaticText(self, label=_("Time zone:")), flag=wx.ALIGN_CENTER_VERTICAL)
		self.timezone_ids = service.timezone_ids()
		self.timezone = wx.ComboBox(self, choices=[_(TIMEZONE_LABELS.get(identity, identity)) for identity in self.timezone_ids],
			style=wx.CB_READONLY, name=_("Time zone"))
		grid.Add(self.timezone, flag=wx.EXPAND)
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
				self.timezone_ids[self.timezone.GetSelection()] if self.timezone.GetSelection() != wx.NOT_FOUND else "",
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
		self._country_matches = self.countries
		self._country_code = None
		self._updating = False
		self._detecting = False
		self.country = wx.ComboBox(parent, choices=[_(item.name) for item in self.countries], name=_("Country"))
		grid.Add(self.country, flag=wx.EXPAND)
		grid.Add(wx.StaticText(parent, label=_("City:")), flag=wx.ALIGN_CENTER_VERTICAL)
		self.city = wx.ComboBox(parent, name=_("City"))
		grid.Add(self.city, flag=wx.EXPAND)
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
		self.country.Bind(wx.EVT_COMBOBOX, self._on_country)
		self.country.Bind(wx.EVT_TEXT, self._on_country_text)
		self.city.Bind(wx.EVT_TEXT, self._on_search)
		self.city.Bind(wx.EVT_COMBOBOX, self._on_city)
		self.detect_button.Bind(wx.EVT_BUTTON, self._on_detect)
		self.custom_button.Bind(wx.EVT_BUTTON, self._on_custom)
		self._set_pending_display(current)

	def _replace_items(self, control, labels):
		# Keep the native editable control, its text, caret and keyboard focus.
		value = control.GetValue()
		selection = control.GetTextSelection()
		self._updating = True
		try:
			control.SetItems(labels)
			control.ChangeValue(value)
			control.SetTextSelection(*selection)
		finally:
			self._updating = False

	def _set_pending_display(self, stored):
		self._search_generation += 1
		self._updating = True
		try:
			self._country_matches = self.countries
			self.country.SetItems([_(item.name) for item in self.countries])
			self._country_code = stored.country_code if stored else None
			index = next((i for i, item in enumerate(self.countries) if item.code == self._country_code), wx.NOT_FOUND)
			self.country.SetSelection(index)
			self.city.SetItems([])
			self.city.ChangeValue(stored.location.name if stored else "")
			self.matches = ()
			self.summary.ChangeValue(_location_summary(stored))
		finally:
			self._updating = False
		if self._country_code:
			self._search()

	def _on_country_text(self, event):
		if not self._updating and self.country.GetSelection() == wx.NOT_FOUND:
			query = self.country.GetValue().casefold().strip()
			self._country_matches = tuple(item for item in self.countries if query in _(item.name).casefold())
			self._replace_items(self.country, [_(item.name) for item in self._country_matches])
			self._country_code = None
			self._clear_city()
		event.Skip()

	def _clear_city(self):
		self._search_generation += 1
		self.pending = None
		self.matches = ()
		self.city.SetItems([])
		self.city.ChangeValue("")
		self.summary.ChangeValue(_location_summary(None))

	def _on_country(self, event):
		index = self.country.GetSelection()
		if index != wx.NOT_FOUND:
			code = self._country_matches[index].code
			if code != self._country_code:
				self._country_code = code
				self._clear_city()
				self._search()
		event.Skip()

	def _on_search(self, event):
		if not self._updating and self.city.GetSelection() == wx.NOT_FOUND:
			self._search()
		event.Skip()

	def _search(self):
		self._search_generation += 1
		generation = self._search_generation
		if self._country_code is None:
			return
		threading.Thread(target=self._search_worker,
			args=(self._country_code, self.city.GetValue().strip(), generation),
			name="AwqatiCitySearch", daemon=True).start()

	def _search_worker(self, country_code, query, generation):
		try:
			with self._search_lock:
				if generation != self._search_generation:
					return
				matches = self.service.search(country_code, query, 40) if query else self.service.browse(country_code, 40)
		except Exception:
			matches = ()
		wx.CallAfter(self._finish_search, generation, matches)

	def _finish_search(self, generation, matches):
		if generation != self._search_generation or not self.parent:
			return
		self.matches = matches
		labels = []
		for match in matches:
			details = ", ".join(match.subdivisions)
			labels.append(" — ".join(part for part in (match.location.name, details,
				_(TIMEZONE_LABELS.get(match.location.timezone_id, match.location.timezone_id))) if part))
		self._replace_items(self.city, labels)

	def _on_city(self, event):
		index = self.city.GetSelection()
		if 0 <= index < len(self.matches):
			match = self.matches[index]
			# Results already contain validated bundled identity and coordinates.
			self.pending = StoredLocation(LocationKind.SELECTED, match.location, match.country_code)
			self.summary.ChangeValue(_location_summary(self.pending))
		event.Skip()

	def _on_custom(self, event: wx.CommandEvent) -> None:
		dialog = CustomLocationDialog(self.parent, self.service)
		try:
			if dialog.ShowModal() == wx.ID_OK and dialog.location is not None:
				self.pending = dialog.location
				self._set_pending_display(self.pending)
		finally:
			dialog.Destroy()
		self.custom_button.SetFocus()
		event.Skip()

	def _on_detect(self, event: wx.CommandEvent) -> None:
		if self._detecting:
			return
		self._detecting = True
		nvda_ui.message(_("Detecting location…"))
		threading.Thread(target=self._detect_worker, name="AwqatiLocation", daemon=True).start()
		event.Skip()

	def _detect_worker(self) -> None:
		with self._search_lock:
			result = self.service.detect()
		wx.CallAfter(self._finish_detection, result)

	def _finish_detection(self, result: LocationSelectionResult) -> None:
		if not self.parent:
			return
		self._detecting = False
		self.detect_button.SetLabel(_("Detect location automatically"))
		if result.location is not None:
			country = next((_(item.name) for item in self.countries if item.code == result.location.country_code), "")
			answer = wx.MessageBox(
				_("Your location was detected: {city}, {country}. Use this location?").format(
					city=result.location.location.name, country=country),
				_("Location detected"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self.parent)
			if answer == wx.YES:
				self.pending = result.location
				self._set_pending_display(self.pending)
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
