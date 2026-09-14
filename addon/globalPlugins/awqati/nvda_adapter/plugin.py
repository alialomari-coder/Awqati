"""NVDA GlobalPlugin adapter for Awqati."""

from pathlib import Path
from typing import Callable

import addonHandler
import globalPluginHandler
import globalVars
import gui
from gui.settingsDialogs import NVDASettingsDialog
import logHandler
import wx

from ..application import LocationSetupService, SettingsService, first_run_location_required
from ..domain import SettingsValidationError
from ..infrastructure import (
	BundledLocationRepository,
	BundledTimezoneProvider,
	JsonSettingsRepository,
	SettingsRepositoryError,
	SystemNowProvider,
	WindowsLocationAdapter,
)
from .settings_panel import AwqatiSettingsPanel
from .ui import FirstRunLocationDialog, NvdaUiContext, configure

addonHandler.initTranslation()
_: Callable[[str], str]


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Load Awqati services and keep product logic outside the entry point."""

	def __init__(self) -> None:
		super().__init__()
		self._context: NvdaUiContext | None = None
		self._terminated = False
		try:
			locations = BundledLocationRepository()
			timezones = BundledTimezoneProvider()
			settings_path = Path(globalVars.appArgs.configPath) / "awqati" / "settings.json"
			settings = SettingsService(
				JsonSettingsRepository(settings_path),
				SystemNowProvider(),
				valid_timezone_ids=frozenset(timezones.timezone_ids()),
			)
			coordinates = WindowsLocationAdapter(parent_window_handle=gui.mainFrame.GetHandle())
			location_setup = LocationSetupService(locations, timezones, coordinates)
		except (SettingsRepositoryError, SettingsValidationError) as error:
			logHandler.log.error("Awqati settings could not be loaded: %s", error)
			wx.CallAfter(
				wx.MessageBox,
				_("Awqati settings could not be loaded. The existing file was not replaced."),
				_("Awqati settings error"),
				wx.OK | wx.ICON_ERROR,
				gui.mainFrame,
			)
			return
		self._context = NvdaUiContext(settings, location_setup)
		configure(self._context)
		if AwqatiSettingsPanel not in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.append(AwqatiSettingsPanel)
		if first_run_location_required(settings.runtime_settings):
			wx.CallAfter(self._show_first_run)

	def _show_first_run(self) -> None:
		if self._terminated or self._context is None:
			return
		if not first_run_location_required(self._context.settings.runtime_settings):
			return
		dialog = FirstRunLocationDialog(gui.mainFrame)
		try:
			dialog.ShowModal()
		finally:
			dialog.Destroy()

	def terminate(self) -> None:
		self._terminated = True
		while AwqatiSettingsPanel in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.remove(AwqatiSettingsPanel)
		configure(None)
		self._context = None
		super().terminate()
