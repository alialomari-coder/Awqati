"""NVDA-facing orchestration for task 5.3 services."""

from __future__ import annotations

import platform
import threading
from typing import Callable

import addonHandler
import api
import gui
import logHandler
import ui
import versionInfo
import wx

from ..application import (
	CancellationToken, DataUpdateError, DataUpdateService, DiagnosticsService,
	DiagnosticsSnapshot, OnlinePrayerRequest, OnlinePrayerVerificationError,
	OnlinePrayerVerifier, OperationCancelled, UpdateChannelUnavailable,
)
from ..domain import PrayerName
from .settings_sections import N_

addonHandler.initTranslation()
_: Callable[[str], str]

PRAYER_NAMES = {
	PrayerName.FAJR: "Fajr", PrayerName.SUNRISE: "Sunrise", PrayerName.DHUHR: "Dhuhr",
	PrayerName.ASR: "Asr", PrayerName.MAGHRIB: "Maghrib", PrayerName.ISHA: "Isha",
}
DIAGNOSTIC_LABELS = {
	"title": N_("Awqati diagnostics"),
	"awqati_version": N_("Awqati version"),
	"nvda_version": N_("NVDA version"),
	"python_version": N_("Python version"),
	"windows_version": N_("Windows version"),
	"settings_schema_version": N_("Settings schemaVersion"),
	"location_data_version": N_("locationDataVersion"),
	"tz_data_version": N_("tzDataVersion"),
	"hijri_data_version": N_("hijriDataVersion"),
	"calculation_method_data_version": N_("calculationMethodDataVersion"),
	"arabian_calendar_data_version": N_("arabianCalendarDataVersion"),
	"timezone_id": N_("Time zone"),
	"location_id": N_("Location ID"),
	"calculation_method": N_("Calculation method"),
	"high_latitude_rule": N_("High-latitude rule"),
	"scheduler_status": N_("Scheduler"),
	"alerts_status": N_("Alerts"),
	"notAssigned": N_("not assigned"),
}


class Task53Actions:
	"""Keep GlobalPlugin and the settings panel thin while sharing the same actions."""

	def __init__(self, *, settings, now, zones, prayers, request_factory, runtime,
			locations, lunar, methods, arabian, data_updates: DataUpdateService,
			online_verifier: OnlinePrayerVerifier, awqati_version: str,
			show_text: Callable[[str, str], None]) -> None:
		self.settings, self.now, self.zones, self.prayers = settings, now, zones, prayers
		self.request_factory, self.runtime = request_factory, runtime
		self.locations, self.lunar, self.methods, self.arabian = locations, lunar, methods, arabian
		self.data_updates, self.online_verifier = data_updates, online_verifier
		self.awqati_version, self.show_text = awqati_version, show_text
		self._privacy_approved = False
		self._closed = False
		self._tokens: set[CancellationToken] = set()

	def close(self) -> None:
		self._closed = True
		for token in tuple(self._tokens):
			token.cancel()

	def copy_diagnostics(self) -> None:
		report = DiagnosticsService().create_report(
			self._diagnostics_snapshot(),
			{key: _(value) for key, value in DIAGNOSTIC_LABELS.items()},
		)
		if api.copyToClip(report):
			ui.message(_("Awqati diagnostic information has been copied to the clipboard."))
		else:
			ui.message(_("Could not copy Awqati diagnostic information to the clipboard."))

	def check_data_updates(self) -> None:
		if not self.data_updates.channel_available:
			ui.message(_("The project data update channel has not been configured. Your current local data remains available."))
			return
		self._run_async(
			_("Checking for Awqati data updates"),
			_("Checking the data manifest and packages..."),
			lambda token: self.data_updates.check(cancellation=token),
			self._update_success,
		)

	def verify_online(self) -> None:
		settings = self.settings.runtime_settings
		if settings.location is None:
			ui.message(_("This Awqati command is unavailable until a valid location is assigned."))
			return
		if not self._privacy_approved:
			answer = wx.MessageBox(
				_("Online verification sends the coordinates required for calculation and the selected calculation method to the AlAdhan Prayer Times API. Approval applies only to this NVDA session. Do you want to continue?"),
				_("Awqati online prayer-time verification"),
				wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
				gui.mainFrame,
			)
			if answer != wx.YES:
				ui.message(_("Online prayer-time verification was cancelled. No data was sent."))
				return
			self._privacy_approved = True
		stored = settings.location
		location = stored.location
		zone = self.zones.get_timezone(location.timezone_id)
		local_date = self.now.now().value.astimezone(zone).date()
		request = self.request_factory(local_date, location)
		internal = self.prayers.calculate(request)
		online_request = OnlinePrayerRequest(
			local_date, location.latitude, location.longitude,
			internal.metadata.effective_method, request.asr_method, request.high_latitude_rule,
		)
		self._run_async(
			_("Verifying today's prayer times online"),
			_("Contacting AlAdhan for a diagnostic comparison..."),
			lambda token: self.online_verifier.verify(online_request, internal, cancellation=token),
			self._verification_success,
		)

	def _run_async(self, title: str, message: str, worker, on_success) -> None:
		token = CancellationToken()
		self._tokens.add(token)
		dialog = wx.ProgressDialog(
			title, message, maximum=100, parent=gui.mainFrame,
			style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME,
		)
		state: dict[str, object] = {}
		timer = wx.Timer(dialog)

		def finish() -> None:
			timer.Stop()
			self._tokens.discard(token)
			if dialog:
				dialog.Destroy()
			if self._closed:
				return
			if "error" in state:
				error = state["error"]
				if isinstance(error, OperationCancelled):
					ui.message(_("The operation was cancelled."))
				else:
					logHandler.log.error("Awqati explicit operation failed: %s", error)
					ui.message(_("The operation failed. Your existing local data and settings were not changed."))
			else:
				on_success(state.get("result"))

		def poll(event) -> None:
			value = dialog.Pulse()
			continued = value[0] if isinstance(value, tuple) else bool(value)
			if not continued:
				token.cancel()
				dialog.Update(0, _("Cancelling..."))

		def run() -> None:
			try:
				state["result"] = worker(token)
			except Exception as error:
				state["error"] = error
			wx.CallAfter(finish)

		dialog.Bind(wx.EVT_TIMER, poll, timer)
		timer.Start(250)
		threading.Thread(target=run, name="Awqati explicit network operation", daemon=True).start()

	def _verification_success(self, result) -> None:
		if result.is_close:
			ui.message(_("All six online prayer times are within two minutes of Awqati's internal times."))
			return
		lines = [_("The following prayer times differ by more than two minutes:")]
		for difference in result.differences:
			hour, minute = divmod(difference.online_minutes, 60)
			lines.append(_("{prayer}: internal {internal}; online {online}; difference {difference} minutes.").format(
				prayer=_(PRAYER_NAMES[difference.prayer]),
				internal=difference.internal.strftime("%H:%M"),
				online=f"{hour:02d}:{minute:02d}",
				difference=difference.difference_minutes,
			))
		self.show_text(_("Online prayer-time comparison"), "\n".join(lines))

	def _update_success(self, result) -> None:
		if result.updated:
			ui.message(_("Awqati data updates were installed safely. Restart NVDA to use them."))
		else:
			ui.message(_("Awqati data is already up to date."))

	def _diagnostics_snapshot(self) -> DiagnosticsSnapshot:
		settings = self.settings.runtime_settings
		stored = settings.location
		scheduler = self.runtime.scheduler
		return DiagnosticsSnapshot(
			awqati_version=self.awqati_version,
			nvda_version=versionInfo.version,
			python_version=platform.python_version(),
			windows_version=platform.platform(),
			settings_schema_version=settings.schema_version,
			location_data_version=self.locations.location_data_version,
			tz_data_version=self.zones.tz_data_version,
			hijri_data_version=self.lunar.hijri_data_version,
			calculation_method_data_version=self.methods.calculation_method_data_version,
			arabian_calendar_data_version=self.arabian.arabian_calendar_data_version,
			timezone_id=stored.location.timezone_id if stored else None,
			location_id=stored.location.location_id if stored else None,
			calculation_method=settings.prayer.calculation_method.value,
			high_latitude_rule=settings.prayer.high_latitude_rule.value,
			scheduler_status=_("active; current={current}; waiting={waiting}").format(
				current=_("yes") if scheduler.current else _("no"), waiting=len(scheduler.waiting)),
			alerts_status=_("all={all}; prayer={prayer}; clock={clock}; dhikr={dhikr}").format(
				all=_("yes") if settings.general.all_automatic_alerts_enabled else _("no"),
				prayer=_("yes") if settings.prayer.alerts_enabled else _("no"),
				clock=_("yes") if settings.clock.automatic_alert_enabled else _("no"),
				dhikr=_("yes") if settings.adhkar.alerts_enabled else _("no")),
		)
