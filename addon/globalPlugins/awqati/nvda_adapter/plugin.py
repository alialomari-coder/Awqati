"""Thin NVDA composition, lifecycle and command adapter for Awqati."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

import addonHandler
import globalPluginHandler
import globalVars
import gui
from gui.settingsDialogs import NVDASettingsDialog
import languageHandler
import logHandler
import scriptHandler
import ui
import wx

from ..application import (
	ArabianCalendarService, AstronomyService, CalendarService, ClockService, DailyInfoService,
	LocationSetupService, PrayerService, SettingsService, first_run_location_required,
)
from ..domain import (
	AfghanSolarHijriProvider, CalendarId, ClockType, GregorianProvider, PersianSolarHijriProvider,
	PrayerCalculationRequest, PrayerCorrections, PrayerEventName, PrayerName,
	SaudiSolarHijriProvider, SettingsValidationError,
)
from ..infrastructure import (
	BundledArabianCalendarRepository, BundledCalculationMethodRepository,
	BundledLocationRepository, BundledTimezoneProvider, JsonSettingsRepository,
	SettingsRepositoryError, SystemNowProvider, UmmAlQuraProvider, WindowsLocationAdapter,
)
from . import compat
from .commands import CommandContent
from .runtime import AwqatiRuntime
from .settings_panel import AwqatiSettingsPanel
from .settings_sections import supported_language
from .text_dialog import SelectableTextDialog
from .ui import FirstRunLocationDialog, NvdaUiContext, configure

addonHandler.initTranslation()
_: Callable[[str], str]

CATEGORY = _("Awqati")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Compose existing services and delegate every product operation."""

	def __init__(self) -> None:
		super().__init__()
		self._context = self._runtime = self._content = self._monitor = None
		self._terminated = False
		try:
			self._compose()
		except (SettingsRepositoryError, SettingsValidationError) as error:
			logHandler.log.error("Awqati settings could not be loaded: %s", error)
			wx.CallAfter(wx.MessageBox,
				_("Awqati settings could not be loaded. The existing file was not replaced."),
				_("Awqati settings error"), wx.OK | wx.ICON_ERROR, gui.mainFrame)

	def _compose(self) -> None:
		locations, zones, now = BundledLocationRepository(), BundledTimezoneProvider(), SystemNowProvider()
		settings_path = Path(globalVars.appArgs.configPath) / "awqati" / "settings.json"
		settings = SettingsService(JsonSettingsRepository(settings_path), now,
			valid_timezone_ids=frozenset(zones.timezone_ids()))
		location_setup = LocationSetupService(locations, zones,
			WindowsLocationAdapter(parent_window_handle=gui.mainFrame.GetHandle()))
		self._context = NvdaUiContext(settings, location_setup)
		configure(self._context)
		if AwqatiSettingsPanel not in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.append(AwqatiSettingsPanel)
		lunar = UmmAlQuraProvider()
		prayers = PrayerService(BundledCalculationMethodRepository(), zones, lunar_calendar=lunar)
		def request(day: date, location):
			s = settings.runtime_settings
			return PrayerCalculationRequest(day, location.latitude, location.longitude, location.timezone_id,
				s.prayer.calculation_method, s.prayer.asr_method, s.prayer.high_latitude_rule,
				country_code=s.location.country_code, corrections=PrayerCorrections(**{
					name.value: s.prayer.corrections_minutes[PrayerEventName(name.value)] for name in PrayerName}))
		clock = ClockService(now, zones, prayers, request)
		calendars = CalendarService(now, zones, (GregorianProvider(), lunar, SaudiSolarHijriProvider(),
			AfghanSolarHijriProvider(), PersianSolarHijriProvider()))
		arabian = ArabianCalendarService(BundledArabianCalendarRepository(), now, zones)
		daily = DailyInfoService(AstronomyService(now, zones), arabian)
		self._content = CommandContent(settings, now, zones, prayers, clock, calendars, daily, arabian)
		root = Path(globalVars.appArgs.configPath) / "awqati"
		self._runtime = AwqatiRuntime(settings, now, zones, prayers, user_data_root=root,
			addon_root=Path(__file__).resolve().parents[1], language_provider=self._language,
			on_error=lambda error: logHandler.log.error("Awqati runtime error: %s", error))
		self._monitor = compat.SystemEventMonitor(gui.mainFrame, self._on_resume, self._on_time_changed)
		if first_run_location_required(settings.runtime_settings):
			wx.CallAfter(self._show_first_run)

	@staticmethod
	def _language() -> str:
		return supported_language(languageHandler.getLanguage())

	def _say(self, producer) -> None:
		try:
			ui.message(producer())
		except Exception as error:
			logHandler.log.error("Awqati command failed: %s", error)
			ui.message(_("This Awqati command is unavailable until a valid location is assigned."))

	def _press(self, handlers) -> None:
		"""Dispatch immediately using NVDA's native zero-based repeat count."""
		compat.dispatch_repeated_script(handlers)

	def _show_first_run(self) -> None:
		if self._terminated or self._context is None or not first_run_location_required(self._context.settings.runtime_settings):
			return
		dialog = FirstRunLocationDialog(gui.mainFrame)
		try: dialog.ShowModal()
		finally: dialog.Destroy()

	def _on_resume(self, event=None) -> None:
		if self._runtime: self._runtime.resume()
		if event is not None: event.Skip()

	def _on_time_changed(self, event=None) -> None:
		if self._runtime: self._runtime.system_time_changed()
		if event is not None: event.Skip()

	@scriptHandler.script(description=_("Open Awqati settings."), category=CATEGORY, gesture="kb:NVDA+alt+a")
	def script_openSettings(self, gesture):
		compat.open_awqati_settings(AwqatiSettingsPanel)

	@scriptHandler.script(description=_("Press once to announce current time details, twice to announce the previous time, or three times to announce today's prayer times."), category=CATEGORY, gesture="kb:NVDA+f11")
	def script_prayerInfo(self, gesture):
		self._press((
			lambda: self._say(lambda: self._content.current_details(_)),
			lambda: self._say(lambda: self._content.previous_details(_)),
			lambda: self._say(lambda: self._content.daily_prayer_times(_)),
		))

	@scriptHandler.script(description=_("Toggle all automatic alerts."), category=CATEGORY, gesture="kb:NVDA+control+shift+f11")
	def script_toggleAllAlerts(self, gesture):
		enabled = self._content.toggle("general.all_automatic_alerts_enabled")
		ui.message(_("All automatic Awqati alerts have been enabled.") if enabled else _("All automatic Awqati alerts have been disabled."))

	@scriptHandler.script(description=_("Press once to announce the time, twice to announce the date, or three times to announce daily information."), category=CATEGORY, gesture="kb:NVDA+f12")
	def script_timeDateInfo(self, gesture):
		self._press((
			lambda: self._say(lambda: self._content.clock_text(ClockType.ZAWALI, self._language())),
			lambda: self._say(lambda: self._content.primary_date(self._language())),
			lambda: self._say(lambda: self._content.daily_info_text(self._language())),
		))

	@scriptHandler.script(description=_("Repeat the last spoken alert."), category=CATEGORY, gesture="kb:NVDA+shift+f12")
	def script_repeatLastAlert(self, gesture):
		if not self._runtime.presenter.replay_last(): ui.message(_("No Awqati alert has been presented yet."))

	@scriptHandler.script(description=_("Announce alert status."), category=CATEGORY, gesture="kb:NVDA+alt+f12")
	def script_alertStatus(self, gesture):
		self._say(lambda: self._content.alert_status(_))

	@scriptHandler.script(description=_("Press once to announce Ghurubi time, twice to announce the Qibla direction, or three times to announce the assigned location."), category=CATEGORY, gesture="kb:NVDA+g")
	def script_ghurubiQibla(self, gesture):
		self._press((lambda: self._say(lambda: self._content.clock_text(ClockType.GHURUBI, self._language())),
			lambda: self._say(lambda: self._content.qibla_text(self._language())),
			lambda: self._say(lambda: self._content.location_text(_))))

	@scriptHandler.script(description=_("Press once to announce the Lunar Hijri date, twice to announce the Saudi Solar Hijri date, or three times to announce the Arabian calendar summary."), category=CATEGORY, gesture="kb:NVDA+h")
	def script_hijriCalendars(self, gesture):
		self._press((lambda: self._say(lambda: self._content.date_text(CalendarId.HIJRI_UMM_AL_QURA, self._language())),
			lambda: self._say(lambda: self._content.date_text(CalendarId.SAUDI_SOLAR_HIJRI, self._language())),
			lambda: self._say(lambda: self._content.arabian_short(self._language()))))

	@scriptHandler.script(description=_("Press once to announce the Afghan Solar Hijri date or twice to announce the Persian Solar Hijri date."), category=CATEGORY, gesture="kb:NVDA+shift+h")
	def script_otherSolarCalendars(self, gesture):
		self._press((lambda: self._say(lambda: self._content.date_text(CalendarId.AFGHAN_SOLAR_HIJRI, self._language())),
			lambda: self._say(lambda: self._content.date_text(CalendarId.PERSIAN_SOLAR_HIJRI, self._language()))))

	@scriptHandler.script(description=_("Press once to announce astronomical daily information, twice to announce Arabian calendar daily information, or three times to open the daily information window."), category=CATEGORY, gesture="kb:NVDA+control+h")
	def script_dailyInformation(self, gesture):
		self._press((
			lambda: self._say(lambda: self._content.scientific_info_text(self._language())),
			lambda: self._say(lambda: self._content.arabian_detailed(self._language())),
			self._showDailyInfo,
		))

	@scriptHandler.script(description=_("Press once to verify today's prayer times online or twice to open today's prayer times window."), category=CATEGORY, gesture="kb:NVDA+shift+p")
	def script_prayerVerification(self, gesture):
		self._press((self._deferred, self._showPrayerTimes))

	@scriptHandler.script(description=_("Announce the Gregorian date."), category=CATEGORY)
	def script_gregorianDate(self, gesture): self._say(lambda: self._content.date_text(CalendarId.GREGORIAN, self._language()))

	@scriptHandler.script(description=_("Toggle the primary calendar between Lunar Hijri and Gregorian."), category=CATEGORY)
	def script_togglePrimaryCalendar(self, gesture):
		value = self._content.toggle_primary_calendar()
		ui.message(_("The primary calendar is now {calendar}.").format(calendar=_("Gregorian") if value is CalendarId.GREGORIAN else _("Lunar Hijri")))

	@scriptHandler.script(description=_("Announce Zawali time."), category=CATEGORY)
	def script_zawaliTime(self, gesture): self._say(lambda: self._content.clock_text(ClockType.ZAWALI, self._language()))

	def _toggle(self, path, enabled_text, disabled_text):
		ui.message(enabled_text if self._content.toggle(path) else disabled_text)

	@scriptHandler.script(description=_("Toggle recurring dhikr."), category=CATEGORY, gesture="kb:NVDA+shift+f11")
	def script_toggleRecurringDhikr(self, gesture): self._toggle("adhkar.recurring.enabled", _("Recurring dhikr has been enabled."), _("Recurring dhikr has been disabled."))

	@scriptHandler.script(description=_("Toggle dhikr alerts."), category=CATEGORY)
	def script_toggleDhikrAlerts(self, gesture): self._toggle("adhkar.alerts_enabled", _("Dhikr alerts have been enabled."), _("Dhikr alerts have been disabled."))

	@scriptHandler.script(description=_("Toggle prayer-time alerts."), category=CATEGORY)
	def script_togglePrayerAlerts(self, gesture): self._toggle("prayer.alerts_enabled", _("Prayer-time alerts have been enabled."), _("Prayer-time alerts have been disabled."))

	@scriptHandler.script(description=_("Toggle the automatic clock alert."), category=CATEGORY)
	def script_toggleClockAlert(self, gesture): self._toggle("clock.automatic_alert_enabled", _("The automatic clock alert has been enabled."), _("The automatic clock alert has been disabled."))

	@scriptHandler.script(description=_("Toggle quiet hours."), category=CATEGORY)
	def script_toggleQuietHours(self, gesture): self._toggle("general.quiet_hours.enabled", _("Quiet hours have been enabled."), _("Quiet hours have been disabled."))

	def _showDailyInfo(self):
		self._show_text(_("Daily information"), self._content.daily_info_text(self._language()))

	def _showPrayerTimes(self):
		self._show_text(_("Today's prayer times"), self._content.daily_prayer_times(_))

	def _show_text(self, title, content):
		SelectableTextDialog.show(gui.mainFrame, title, content)

	def _deferred(self): ui.message(_("This command will be available in Awqati task 5.3."))

	@scriptHandler.script(description=_("Copy diagnostic information."), category=CATEGORY)
	def script_diagnostics(self, gesture): self._deferred()

	@scriptHandler.script(description=_("Check for data updates."), category=CATEGORY)
	def script_dataUpdates(self, gesture): self._deferred()


	def terminate(self) -> None:
		if self._terminated:
			return
		self._terminated = True
		if self._monitor: self._monitor.close()
		if self._runtime: self._runtime.close()
		while AwqatiSettingsPanel in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.remove(AwqatiSettingsPanel)
		configure(None)
		self._context = self._runtime = self._content = self._monitor = None
		super().terminate()
