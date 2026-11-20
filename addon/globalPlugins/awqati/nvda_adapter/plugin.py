"""Thin NVDA composition, lifecycle and command adapter for Awqati."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

import config
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
	DataUpdateService, LocationSetupService, OnlinePrayerVerifier, PrayerService, SettingsService,
	first_run_location_required,
)
from ..domain import (
	AfghanSolarHijriProvider, AlertEventType, CalendarId, ClockType, GregorianProvider, PersianSolarHijriProvider,
	PrayerCalculationRequest, PrayerCorrections, PrayerEventName, PrayerName,
	SaudiSolarHijriProvider, SettingsValidationError,
)
from ..infrastructure import (
	ArabianCalendarDataError,
	BundledArabianCalendarRepository, BundledCalculationMethodRepository,
	BundledLocationRepository, BundledTimezoneProvider, JsonSettingsRepository,
	AlAdhanPrayerProvider, AtomicDataPackageInstaller, HttpsTransport,
	CalculationMethodDataError, LocationDataError, SettingsRepositoryError,
	SystemNowProvider, TimezoneDataError, UmmAlQuraDataError, UmmAlQuraProvider,
	WindowsLocationAdapter,
	active_data_path,
)
from ..application.on_this_day import OnThisDayService
from ..application.on_this_day_presentation import OnThisDayPresentation
from ..infrastructure.on_this_day_cache import DayCache
from ..infrastructure.on_this_day_wikipedia import WikipediaDayProvider
from ..infrastructure.on_this_day_pages import LocalDayPages
from .on_this_day_speech import DaySpeech
from . import compat
from .calendar_converter_control import CalendarConverterControl, ConverterPresses
from .commands import CommandContent
from .runtime import AwqatiRuntime
from .alarm_dialogs import AlarmManager, next_alarm_text
from .time_tools import TimeToolsState
from .stopwatch_control import StopwatchControl
from .countdown_control import CountdownControl
from .duration_formatter import format_minutes
from .world_clock_control import WorldClockControl
from .settings_panel import AwqatiSettingsPanel
from .settings_sections import supported_language
from .text_dialog import SelectableTextDialog
from .task53_actions import Task53Actions
from .ui import FirstRunLocationDialog, NvdaUiContext, configure, custom_calculation_method_required, choose_custom_calculation_method

addonHandler.initTranslation()
_: Callable[[str], str]

CATEGORY = _("Awqati")
DATA_UPDATE_MANIFEST_URL = (
	"https://raw.githubusercontent.com/alialomari-coder/awqati-data/main/manifest.json"
)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Compose existing services and delegate every product operation."""

	def __init__(self) -> None:
		super().__init__()
		# Preserve customized legacy commands in Input Gestures, including their
		# descriptions. Unassigned duplicates stay callable but leave the list.
		try:
			import inputCore
			from .legacy_commands import configure_legacy_visibility
			configure_legacy_visibility(type(self), (
				inputCore.manager.userGestureMap, inputCore.manager.localeGestureMap,
			))
		except Exception:
			logHandler.log.exception("Could not inspect legacy Awqati gesture bindings; command descriptions retained.")
		self._context = self._runtime = self._content = self._monitor = self._actions = None
		self._terminated = False
		self._stopwatch = None
		self._countdowns = None
		self._world_clock = None
		self._on_this_day = None
		self._converter = None
		self._weather = None
		try:
			self._compose()
		except (SettingsRepositoryError, SettingsValidationError) as error:
			logHandler.log.error("Awqati settings could not be loaded: %s", error)
			wx.CallAfter(wx.MessageBox,
				_("Awqati settings could not be loaded. The existing file was not replaced."),
				_("Awqati settings error"), wx.OK | wx.ICON_ERROR, gui.mainFrame)
		except (
			ArabianCalendarDataError,
			CalculationMethodDataError,
			LocationDataError,
			TimezoneDataError,
			UmmAlQuraDataError,
		) as error:
			logHandler.log.error("Awqati local data could not be loaded: %s", error)
			wx.CallAfter(wx.MessageBox,
				_("Awqati could not start because its local data is unavailable or invalid. "
				  "Reinstall the add-on or restore the data, then restart NVDA."),
				_("Awqati data error"), wx.OK | wx.ICON_ERROR, gui.mainFrame)

	def _compose(self) -> None:
		root = Path(globalVars.appArgs.configPath) / "awqati"
		addon_root = Path(__file__).resolve().parents[1]
		data_root = addon_root / "data"
		locations = BundledLocationRepository(active_data_path(data_root, root, "locations"))
		zones = BundledTimezoneProvider(active_data_path(data_root, root, "timezones"))
		lunar = UmmAlQuraProvider(active_data_path(data_root, root, "ummalqura"))
		methods = BundledCalculationMethodRepository(active_data_path(data_root, root, "calculationMethods"))
		arabian_repository = BundledArabianCalendarRepository(active_data_path(data_root, root, "arabianCalendar"))
		now = SystemNowProvider()
		settings_path = root / "settings.json"
		settings = SettingsService(JsonSettingsRepository(settings_path), now,
			valid_timezone_ids=frozenset(zones.timezone_ids()))
		location_setup = LocationSetupService(locations, zones,
			WindowsLocationAdapter(parent_window_handle=gui.mainFrame.GetHandle()))
		prayers = PrayerService(methods, zones, lunar_calendar=lunar)
		def request(day: date, location):
			s = settings.runtime_settings
			return PrayerCalculationRequest(day, location.latitude, location.longitude, location.timezone_id,
				s.prayer.calculation_method, s.prayer.asr_method, s.prayer.high_latitude_rule,
				country_code=s.location.country_code, corrections=PrayerCorrections(**{
					name.value: s.prayer.corrections_minutes[PrayerEventName(name.value)] for name in PrayerName}))
		clock = ClockService(now, zones, prayers, request)
		calendars = CalendarService(now, zones, (GregorianProvider(), lunar, SaudiSolarHijriProvider(),
			AfghanSolarHijriProvider(), PersianSolarHijriProvider()))
		self._converter = CalendarConverterControl(settings, now, zones, lunar,
			self._language, ui.message, gui.mainFrame)
		self._converter.presses = ConverterPresses(wx.CallLater,
			lambda: config.conf["keyboard"]["multiPressTimeout"],
			self._converter_binding_active, lambda advanced: self._converter.show(advanced))
		arabian = ArabianCalendarService(arabian_repository, now, zones)
		daily = DailyInfoService(AstronomyService(now, zones), arabian)
		self._content = CommandContent(settings, now, zones, prayers, clock, calendars, daily, arabian)
		self._runtime = AwqatiRuntime(settings, now, zones, prayers, user_data_root=root,
			addon_root=addon_root, language_provider=self._language,
			on_error=lambda error: logHandler.log.error("Awqati runtime error: %s", error),
			on_alarm_fallback=lambda: ui.message(_("A personal alarm sound is unavailable. The default sound will be used.")),
			on_alarm_data_error=lambda: ui.message(_("Personal alarm data could not be saved safely. Automatic personal alarms are paused; existing files are preserved. Other Awqati alerts remain available.")),
			on_alarm_read_error=lambda: ui.message(_("Some personal alarm data could not be read. Existing data has been preserved unchanged.")))
		updates = DataUpdateService(
			DATA_UPDATE_MANIFEST_URL,
			HttpsTransport(),
			AtomicDataPackageInstaller(root),
			{
				"locations": locations.location_data_version,
				"timezones": zones.tz_data_version,
				"ummalqura": lunar.hijri_data_version,
				"calculationMethods": methods.calculation_method_data_version,
				"arabianCalendar": arabian_repository.arabian_calendar_data_version,
			},
		)
		self._actions = Task53Actions(
			settings=settings, now=now, zones=zones, prayers=prayers, request_factory=request,
			runtime=self._runtime, locations=locations, lunar=lunar, methods=methods,
			arabian=arabian_repository, data_updates=updates,
			online_verifier=OnlinePrayerVerifier(AlAdhanPrayerProvider()),
			awqati_version=addonHandler.getCodeAddon().manifest["version"],
			show_text=self._show_text,
		)
		self._context = NvdaUiContext(
			settings, location_setup,
			show_qibla=self._announce_qibla,
			show_prayer_times=self._showPrayerTimes,
			show_daily_info=self._showDailyInfo,
			copy_diagnostics=self._actions.copy_diagnostics,
			check_data_updates=self._actions.check_data_updates,
			verify_prayer_times=self._actions.verify_online,
			show_personal_alarms=self._showAlarms,
			show_stopwatch=self._showStopwatch,
			show_countdowns=self._showCountdowns,
			show_converter=self._converter.show,
		)
		day_service = OnThisDayService(WikipediaDayProvider(), DayCache(root / "on_this_day.json"),
			language=self._language, dispatch=wx.CallAfter)
		day_speech = DaySpeech()
		day_pages = LocalDayPages(root / "on_this_day_pages")
		self._on_this_day = OnThisDayPresentation(day_service,
			language=self._language, today=date.today,
			web_mode=lambda: settings.runtime_settings.calendar.on_this_day_web_page,
			translate=_, schedule=wx.CallLater,
			settle_ms=lambda: int(config.conf["keyboard"]["multiPressTimeout"]) + 100,
			speak=day_speech.speak, stop_speech=day_speech.stop,
			message=ui.message, open_page=day_pages.open)
		self._stopwatch = StopwatchControl(root, self._runtime, addon_root)
		self._countdowns = CountdownControl(root, self._runtime)
		self._world_clock = WorldClockControl(root, self._runtime, addon_root)
		self._runtime.world_clock = self._world_clock
		self._context.time_tools = TimeToolsState(self._runtime, self._countdowns, self._stopwatch, self._world_clock)
		try:
			from .weather_control import WeatherControl
			self._weather = WeatherControl(settings, zones, self._language, ui.message,
				lambda: config.conf["keyboard"]["multiPressTimeout"], locations=locations)
			self._context.weather = self._weather
			self._content.weather_summary = self._weather.summary
		except Exception:
			logHandler.log.exception("Awqati weather could not start; other functions remain available.")
		configure(self._context)
		if AwqatiSettingsPanel not in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.append(AwqatiSettingsPanel)
		self._monitor = compat.SystemEventMonitor(gui.mainFrame, self._on_resume, self._on_time_changed)
		if first_run_location_required(settings.runtime_settings):
			wx.CallAfter(self._show_first_run)
		elif custom_calculation_method_required(settings.runtime_settings):
			wx.CallAfter(self._show_custom_method_setup)

	@staticmethod
	def _language() -> str:
		return supported_language(languageHandler.getLanguage())

	def _say(self, producer) -> None:
		actions = getattr(self, "_actions", None)
		if actions:
			actions.invalidate_feedback()
		try:
			ui.message(producer())
		except Exception as error:
			logHandler.log.error("Awqati command failed: %s", error)
			ui.message(_("This Awqati command is unavailable until a valid location is assigned."))

	def _announce_qibla(self) -> None:
		"""Use the shared command path for both the gesture and settings button."""
		self._say(lambda: self._content.qibla_text(self._language()))

	def _press(self, handlers, *, repeat_last=True) -> None:
		"""Dispatch immediately using NVDA's native zero-based repeat count."""
		actions = getattr(self, "_actions", None)
		if actions:
			actions.invalidate_feedback()
		compat.dispatch_repeated_script(handlers, repeat_last=repeat_last)

	def _show_first_run(self) -> None:
		if self._terminated or self._context is None or not first_run_location_required(self._context.settings.runtime_settings):
			return
		dialog = FirstRunLocationDialog(gui.mainFrame)
		try: dialog.ShowModal()
		finally: dialog.Destroy()

	def _show_custom_method_setup(self) -> None:
		"""Repair an older custom/AUTO preference only with an explicit choice."""
		if self._terminated or self._context is None:
			return
		draft = self._context.settings.open_draft()
		try:
			if not custom_calculation_method_required(draft.settings):
				return
			if choose_custom_calculation_method(gui.mainFrame, draft.settings):
				try:
					self._context.settings.apply(draft)
				except (SettingsRepositoryError, SettingsValidationError):
					wx.MessageBox(_("The calculation method could not be saved. Your previous settings were preserved."),
						_("Could not save settings"), wx.OK | wx.ICON_ERROR, gui.mainFrame)
		finally:
			draft.discard()

	def _on_resume(self, event=None) -> None:
		if self._runtime: self._runtime.resume()
		if event is not None: event.Skip()

	def _on_time_changed(self, event=None) -> None:
		if self._runtime: self._runtime.system_time_changed()
		if event is not None: event.Skip()

	def _converter_binding_active(self, identifiers):
		from keyboardHandler import KeyboardInputGesture
		if self._terminated:
			return False
		for identifier in identifiers:
			try:
				gesture = KeyboardInputGesture.fromName(identifier.split(":", 1)[1])
				if scriptHandler.findScript(gesture) == self.script_openDateConverter:
					return True
			except (ValueError, LookupError):
				continue
		return False

	@scriptHandler.script(description=_("Open date converter"), category=CATEGORY)
	def script_openDateConverter(self, gesture):
		if self._converter and not self._terminated:
			self._converter.presses.press(gesture.normalizedIdentifiers,
				scriptHandler.getLastScriptRepeatCount())

	@scriptHandler.script(description=_("Open Awqati settings."), category=CATEGORY, gesture="kb:NVDA+alt+a")
	def script_openSettings(self, gesture):
		self._actions.invalidate_feedback()
		compat.open_awqati_settings(AwqatiSettingsPanel)

	@scriptHandler.script(description=_("Open Awqati weather settings."), category=CATEGORY, gesture="kb:NVDA+alt+w")
	def script_weatherSettings(self, gesture):
		self._actions.invalidate_feedback()
		from .settings_sections import SettingsSection
		compat.open_awqati_settings(AwqatiSettingsPanel, SettingsSection.WEATHER)

	@scriptHandler.script(description=_("Press once to announce current time details, twice to announce the previous time, or three times to announce today's prayer times."), category=CATEGORY, gesture="kb:NVDA+f11")
	def script_prayerInfo(self, gesture):
		self._press((
			lambda: self._say(lambda: self._content.current_details(_)),
			lambda: self._say(lambda: self._content.previous_details(_)),
			lambda: self._say(lambda: self._content.daily_prayer_times(_)),
		))

	@scriptHandler.script(description=_("Toggle all automatic alerts."), category=CATEGORY, gesture="kb:NVDA+control+shift+f11")
	def script_toggleAllAlerts(self, gesture):
		self._actions.invalidate_feedback()
		enabled = self._content.toggle("general.all_automatic_alerts_enabled")
		ui.message(_("All automatic Awqati alerts have been enabled.") if enabled else _("All automatic Awqati alerts have been disabled."))

	@scriptHandler.script(description=_("Press once to announce the time, twice to announce the date, or three times to announce daily information."), category=CATEGORY, gesture="kb:NVDA+f12")
	def script_timeDateInfo(self, gesture):
		self._press((
			lambda: self._say(lambda: self._content.clock_text(ClockType.ZAWALI, self._language())),
			lambda: self._say(lambda: self._content.primary_date(self._language())),
			lambda: self._say(lambda: self._content.daily_info_text(self._language())),
		))

	@scriptHandler.script(description=_("On This Day: press once for historical events, twice for births, three times for deaths, or four times for holidays and observances."), category=CATEGORY, gesture="kb:NVDA+windows+f12")
	def script_onThisDay(self, gesture):
		if self._on_this_day and not self._terminated:
			self._press(tuple(lambda key=key: self._on_this_day.select(key)
				for key in ("events", "births", "deaths", "observances")))

	@scriptHandler.script(description=_("Press once to announce the current weather, twice to announce today's weather forecast, or three times to announce the weather forecast for the coming days."), category=CATEGORY, gesture="kb:NVDA+w")
	def script_weather(self, gesture):
		if self._weather and not self._terminated:
			self._weather.presses.press()

	@scriptHandler.script(description=_("Open weather information in a text window"), category=CATEGORY)
	def script_weatherReport(self, gesture):
		if self._weather and not self._terminated:
			self._weather.show()

	@scriptHandler.script(description=_("Repeat the last spoken alert."), category=CATEGORY, gesture="kb:NVDA+shift+f12")
	def script_repeatLastAlert(self, gesture):
		self._actions.invalidate_feedback()
		if not self._runtime.presenter.replay_last(): ui.message(_("No Awqati alert has been presented yet."))

	@scriptHandler.script(description=_("Announce alert status."), category=CATEGORY, gesture="kb:NVDA+alt+f12")
	def script_alertStatus(self, gesture):
		self._say(lambda: self._content.alert_status(_))

	@scriptHandler.script(description=_("Press once to announce Ghurubi time, twice to announce the Qibla direction, or three times to announce the assigned location."), category=CATEGORY, gesture="kb:NVDA+g")
	def script_ghurubiQibla(self, gesture):
		self._press((lambda: self._say(lambda: self._content.clock_text(ClockType.GHURUBI, self._language())),
			self._announce_qibla,
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

	@scriptHandler.script(description=_("Verify today's prayer times online."), category=CATEGORY, gesture="kb:NVDA+shift+p")
	def script_prayerVerification(self, gesture):
		self._press((lambda: wx.CallAfter(self._actions.verify_online, from_global_command=True),), repeat_last=False)

	@scriptHandler.script(description=_("Open today's prayer times window."), category=CATEGORY, gesture="kb:NVDA+alt+p")
	def script_prayerTimesWindow(self, gesture):
		self._actions.invalidate_feedback()
		wx.CallAfter(self._showPrayerTimes)

	@scriptHandler.script(description=_("Announce the Gregorian date."), category=CATEGORY)
	def script_gregorianDate(self, gesture): self._say(lambda: self._content.date_text(CalendarId.GREGORIAN, self._language()))

	@scriptHandler.script(description=_("Toggle the primary calendar between Lunar Hijri and Gregorian."), category=CATEGORY)
	def script_togglePrimaryCalendar(self, gesture):
		self._actions.invalidate_feedback()
		value = self._content.toggle_primary_calendar()
		ui.message(_("The primary calendar is now {calendar}.").format(calendar=_("Gregorian") if value is CalendarId.GREGORIAN else _("Lunar Hijri")))

	@scriptHandler.script(description=_("Announce Zawali time."), category=CATEGORY)
	def script_zawaliTime(self, gesture): self._say(lambda: self._content.clock_text(ClockType.ZAWALI, self._language()))

	def _toggle(self, path, enabled_text, disabled_text):
		self._actions.invalidate_feedback()
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

	def _showAlarms(self):
		self._openTimeTool("alarms")

	def _openTimeTool(self, identity):
		if self._terminated:
			return
		self._actions.invalidate_feedback()
		self._context.time_tools.requested = identity
		compat.open_awqati_settings(AwqatiSettingsPanel)
		self._context.time_tools.request(identity)

	def _showCountdowns(self):
		if self._countdowns and not self._terminated:
			self._openTimeTool("timers")

	@scriptHandler.script(description=_("Open countdown timers."), category=CATEGORY, gesture="kb:NVDA+alt+y")
	def script_countdownWindow(self, gesture): wx.CallAfter(self._showCountdowns)

	@scriptHandler.script(description=_("Press once to announce the selected timer's name and remaining time, twice to announce its state and the number of timers."), category=CATEGORY, gesture="kb:NVDA+y")
	def script_countdownSelected(self, gesture): self._press((self._countdowns.announce_remaining, self._countdowns.status_count))

	@scriptHandler.script(description=_("Start, pause or resume selected countdown timer."), category=CATEGORY, gesture="kb:NVDA+shift+y")
	def script_countdownToggle(self, gesture): self._press((self._countdowns.toggle,), repeat_last=False)

	@scriptHandler.script(description=_("Restart selected countdown timer with confirmation."), category=CATEGORY, gesture="kb:NVDA+control+shift+y")
	def script_countdownRestart(self, gesture): self._press((lambda: wx.CallAfter(self._countdowns.restart),), repeat_last=False)

	@scriptHandler.script(description=_("Silence one currently ringing countdown timer and announce its name."), category=CATEGORY, gesture="kb:NVDA+control+y")
	def script_countdownStopAlert(self, gesture): self._press((self._countdowns.stop_current_alert,))

	@scriptHandler.script(description=_("Select the next countdown timer and announce its name and remaining time."), category=CATEGORY, gesture="kb:NVDA+windows+y")
	def script_countdownNext(self, gesture): self._press((lambda: self._countdowns.navigate(1),))

	@scriptHandler.script(description=_("Select the previous countdown timer and announce its name and remaining time."), category=CATEGORY, gesture="kb:NVDA+windows+shift+y")
	def script_countdownPrevious(self, gesture): self._press((lambda: self._countdowns.navigate(-1),))

	@scriptHandler.script(description=_("Announce number of active countdown timers."), category=CATEGORY)
	def script_countdownCount(self, gesture): self._press((self._countdowns.count,))

	@scriptHandler.script(description=_("Announce countdown timer nearest to completion."), category=CATEGORY)
	def script_countdownNearest(self, gesture): self._press((self._countdowns.nearest,))

	def _showStopwatch(self):
		if self._stopwatch and not self._terminated:
			self._openTimeTool("stopwatch")

	@scriptHandler.script(description=_("Start, pause or resume the stopwatch according to its current state."), category=CATEGORY, gesture="kb:NVDA+j")
	def script_stopwatchInfo(self, gesture):
		if self._stopwatch:
			self._press((self._stopwatch.toggle,), repeat_last=False)

	@scriptHandler.script(description=_("Record a new stopwatch lap."), category=CATEGORY, gesture="kb:NVDA+shift+j")
	def script_stopwatchLaps(self, gesture):
		if self._stopwatch:
			self._press((self._stopwatch.lap,), repeat_last=False)

	@scriptHandler.script(description=_("Press once to announce the current lap duration, or twice to announce the last recorded lap."), category=CATEGORY, gesture="kb:NVDA+windows+shift+j")
	def script_stopwatchCurrentLap(self, gesture): self._press((self._stopwatch.current_lap, self._stopwatch.last_lap))

	@scriptHandler.script(description=_("Open the stopwatch window."), category=CATEGORY, gesture="kb:NVDA+control+j")
	def script_stopwatchWindow(self, gesture):
		wx.CallAfter(self._showStopwatch)

	@scriptHandler.script(description=_("Copy stopwatch results."), category=CATEGORY)
	def script_stopwatchCopy(self, gesture): self._press((self._stopwatch.copy,), repeat_last=False)

	@scriptHandler.script(description=_("Reset stopwatch with confirmation."), category=CATEGORY, gesture="kb:NVDA+control+shift+j")
	def script_stopwatchReset(self, gesture): self._press((lambda: wx.CallAfter(self._stopwatch.reset),), repeat_last=False)

	@scriptHandler.script(description=_("Announce stopwatch status."), category=CATEGORY)
	def script_stopwatchStatus(self, gesture): self._press((self._stopwatch.status,))

	@scriptHandler.script(description=_("Announce stopwatch lap count."), category=CATEGORY)
	def script_stopwatchCount(self, gesture): self._press((self._stopwatch.count,))

	@scriptHandler.script(description=_("Record stopwatch lap."), category=CATEGORY)
	def script_stopwatchLap(self, gesture): self._press((self._stopwatch.lap,), repeat_last=False)

	@scriptHandler.script(description=_("Start, pause or resume stopwatch."), category=CATEGORY)
	def script_stopwatchToggle(self, gesture): self._press((self._stopwatch.toggle,), repeat_last=False)

	@scriptHandler.script(description=_("Press once to announce stopwatch elapsed time, or twice to announce its status and lap count."), category=CATEGORY, gesture="kb:NVDA+windows+j")
	def script_stopwatchTotal(self, gesture): self._press((self._stopwatch.total, self._stopwatch.status))

	@scriptHandler.script(description=_("Announce last stopwatch lap."), category=CATEGORY)
	def script_stopwatchLastLap(self, gesture): self._press((self._stopwatch.last_lap,))

	@scriptHandler.script(description=_("Open personal alarms."), category=CATEGORY, gesture="kb:NVDA+alt+f8")
	def script_personalAlarms(self, gesture):
		wx.CallAfter(self._showAlarms)

	@scriptHandler.script(description=_("Press once to announce the next personal alarm, twice for the enabled alarm count, or three times to stop the current alarm."), category=CATEGORY, gesture="kb:NVDA+f8")
	def script_personalAlarmInfo(self, gesture):
		self._press((lambda: ui.message(next_alarm_text(self._runtime)),
			lambda: ui.message(_("Enabled personal alarms: {count}.").format(count=sum(alarm.enabled for alarm in self._runtime.alarms.alarms.values()))),
			self._stopPersonalAlarm), repeat_last=False)

	@scriptHandler.script(description=_("Stop the current personal alarm."), category=CATEGORY)
	def script_stopPersonalAlarm(self, gesture):
		self._press((self._stopPersonalAlarm,), repeat_last=False)

	@scriptHandler.script(description=_("Snooze the current personal alarm."), category=CATEGORY, gesture="kb:NVDA+shift+f8")
	def script_snoozePersonalAlarm(self, gesture):
		self._press((self._snoozePersonalAlarm,), repeat_last=False)

	def _stopPersonalAlarm(self):
		try:
			ui.message(_("Personal alarm stopped.") if self._runtime.stop_alarm() else _("No personal alarm is active."))
		except OSError:
			ui.message(_("The pending snooze could not be cancelled. No successful stop was recorded."))

	def _snoozePersonalAlarm(self):
		current = self._runtime.presenter.current
		if current is None or current.event_type is not AlertEventType.PERSONAL_ALARM:
			ui.message(_("There is no current personal alarm to snooze."))
			return
		try:
			if self._runtime.snooze_alarm():
				duration = format_minutes(self._runtime.last_snooze_minutes, _, oblique=True, spell_out=True)
				ui.message(_("Personal alarm snoozed. The alarm will ring again in {duration}.").format(duration=duration))
			else:
				ui.message(_("Snooze is unavailable. It may be disabled or exhausted."))
		except OSError:
			ui.message(_("The snooze could not be saved. The alarm has not been postponed."))


	def _showDailyInfo(self):
		self._show_text(_("Daily information"), self._content.daily_info_text(self._language()))

	def _showPrayerTimes(self):
		self._show_text(_("Today's prayer times"), self._content.daily_prayer_times(_))

	def _show_text(self, title, content):
		self._actions.invalidate_feedback()
		focus = wx.Window.FindFocus()
		parent = focus.GetTopLevelParent() if focus is not None else None
		if parent is None or not parent.IsShown():
			parent = gui.mainFrame
		SelectableTextDialog.show(parent, title, content)

	@scriptHandler.script(description=_("Copy diagnostic information."), category=CATEGORY)
	def script_diagnostics(self, gesture): self._actions.copy_diagnostics()

	@scriptHandler.script(description=_("Check for data updates."), category=CATEGORY)
	def script_dataUpdates(self, gesture): self._context.check_data_updates()


	@scriptHandler.script(description=_("Press once to announce the first city's time, twice for the second city's time, and three times for the third city's time."), category=CATEGORY, gesture="kb:NVDA+control+f12")
	def script_worldClock(self, gesture):
		if self._world_clock and not self._terminated:
			actions = getattr(self, "_actions", None)
			if actions:
				actions.invalidate_feedback()
			count = scriptHandler.getLastScriptRepeatCount()
			self._world_clock.announce(min(max(0, count), 2))

	def terminate(self) -> None:
		if self._terminated:
			return
		self._terminated = True
		if self._converter: self._converter.close()
		if self._weather: self._weather.close()
		if self._on_this_day: self._on_this_day.close()
		if self._world_clock: self._world_clock.close()
		if self._countdowns: self._countdowns.close()
		if self._stopwatch: self._stopwatch.close()
		if self._actions: self._actions.close()
		if self._monitor: self._monitor.close()
		if self._runtime: self._runtime.close()
		while AwqatiSettingsPanel in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.remove(AwqatiSettingsPanel)
		configure(None)
		self._context = self._runtime = self._content = self._monitor = self._actions = None
		super().terminate()
