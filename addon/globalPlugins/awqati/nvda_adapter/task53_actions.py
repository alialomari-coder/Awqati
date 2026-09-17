"""NVDA-facing orchestration for task 5.3 services."""

from __future__ import annotations

import platform
import threading
from typing import Callable

import addonHandler
import api
import gui
import languageHandler
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
from .settings_sections import N_, is_rtl_language

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


class _OperationDialog(wx.Dialog):
	"""Non-modal, keyboard-accessible progress UI for an explicit operation."""

	def __init__(self, parent: wx.Window, title: str, message: str, cancel: Callable[[], None]) -> None:
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
		self._cancel = cancel
		self._cancel_requested = False
		self.SetLayoutDirection(
			wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage())
			else wx.Layout_LeftToRight)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		self.status = wx.StaticText(panel, label=message, name=message)
		self.cancel_button = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
		sizer.Add(self.status, flag=wx.ALL | wx.EXPAND, border=12)
		sizer.Add(self.cancel_button, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT, border=12)
		panel.SetSizer(sizer)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(panel, proportion=1, flag=wx.EXPAND)
		self.SetSizerAndFit(outer)
		self.SetEscapeId(wx.ID_CANCEL)
		self.cancel_button.Bind(wx.EVT_BUTTON, self._on_cancel)
		self.Bind(wx.EVT_CLOSE, self._on_cancel)
		self.CentreOnParent()

	def _on_cancel(self, event) -> None:
		if not self._cancel_requested:
			self._cancel_requested = True
			self._cancel()
			message = _("Cancelling...")
			self.status.SetLabel(message)
			self.status.SetName(message)
			self.cancel_button.Disable()
			ui.message(message)
		if isinstance(event, wx.CloseEvent) and event.CanVeto():
			event.Veto()


class _PrivacyDialog(wx.Dialog):
	"""Non-modal confirmation used only by the global verification command."""

	def __init__(self, parent: wx.Window, title: str, message: str,
			on_answer: Callable[[int], None]) -> None:
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
		self._on_answer = on_answer
		self._answered = False
		self.SetLayoutDirection(
			wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage())
			else wx.Layout_LeftToRight)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		message_label = wx.StaticText(panel, label=message, name=message)
		message_label.Wrap(520)
		buttons = wx.StdDialogButtonSizer()
		self.yes_button = wx.Button(panel, wx.ID_YES)
		self.no_button = wx.Button(panel, wx.ID_NO)
		buttons.AddButton(self.yes_button)
		buttons.AddButton(self.no_button)
		buttons.Realize()
		sizer.Add(message_label, flag=wx.ALL | wx.EXPAND, border=12)
		sizer.Add(buttons, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_RIGHT, border=12)
		panel.SetSizer(sizer)
		outer = wx.BoxSizer(wx.VERTICAL)
		outer.Add(panel, proportion=1, flag=wx.EXPAND)
		self.SetSizerAndFit(outer)
		self.SetAffirmativeId(wx.ID_NO)
		self.SetEscapeId(wx.ID_NO)
		self.no_button.SetDefault()
		self.yes_button.Bind(wx.EVT_BUTTON, lambda event: self._finish(wx.YES))
		self.no_button.Bind(wx.EVT_BUTTON, lambda event: self._finish(wx.NO))
		self.Bind(wx.EVT_CLOSE, lambda event: self._finish(wx.NO))
		self.CentreOnParent()

	def _finish(self, answer: int) -> None:
		if self._answered:
			return
		self._answered = True
		self.Hide()
		self.Destroy()
		wx.CallAfter(self._on_answer, answer)


def _interaction_parent() -> wx.Window:
	"""Use the invoking NVDA dialog when one has focus, otherwise the main frame."""
	focus = wx.Window.FindFocus()
	if focus is not None:
		parent = focus.GetTopLevelParent()
		if parent is not None and parent.IsShown():
			return parent
	return gui.mainFrame


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
		self._privacy_dialog: _PrivacyDialog | None = None
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

	def verify_online(self, *, from_global_command: bool = False) -> None:
		settings = self.settings.runtime_settings
		if settings.location is None:
			ui.message(_("This Awqati command is unavailable until a valid location is assigned."))
			return
		if not self._privacy_approved:
			privacy_message = _("Online verification sends the coordinates required for calculation and the selected calculation method to the AlAdhan Prayer Times API. Approval applies only to this NVDA session. Do you want to continue?")
			if from_global_command:
				self._show_global_privacy_prompt(settings.location, privacy_message)
				return
			answer = wx.MessageBox(
				privacy_message,
				_("Awqati online prayer-time verification"),
				wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
				_interaction_parent(),
			)
			if answer != wx.YES:
				ui.message(_("Online prayer-time verification was cancelled. No data was sent."))
				return
			self._privacy_approved = True
		self._start_online_verification(settings.location)

	def _show_global_privacy_prompt(self, stored, privacy_message: str) -> None:
		if self._privacy_dialog is not None and not self._privacy_dialog.IsBeingDeleted():
			self._privacy_dialog.Raise()
			self._privacy_dialog.no_button.SetFocus()
			return
		gui.mainFrame.prePopup()

		def answered(answer: int) -> None:
			self._privacy_dialog = None
			gui.mainFrame.postPopup()
			if self._closed:
				return
			if answer != wx.YES:
				ui.message(_("Online prayer-time verification was cancelled. No data was sent."))
				return
			self._privacy_approved = True
			self._start_online_verification(stored)

		try:
			dialog = _PrivacyDialog(
				gui.mainFrame,
				_("Awqati online prayer-time verification"),
				privacy_message,
				answered,
			)
			self._privacy_dialog = dialog
			dialog.Show()
			dialog.Raise()
			dialog.no_button.SetFocus()
			wx.CallLater(100, ui.message, privacy_message)
		except Exception:
			self._privacy_dialog = None
			gui.mainFrame.postPopup()
			raise

	def _start_online_verification(self, stored) -> None:
		parent = _interaction_parent()

		def verify(token: CancellationToken):
			# Time-zone lookup and prayer calculation may lazily read bundled or
			# activated data. Keep them on the same worker as HTTPS and DNS.
			token.raise_if_cancelled()
			location = stored.location
			zone = self.zones.get_timezone(location.timezone_id)
			local_date = self.now.now().value.astimezone(zone).date()
			request = self.request_factory(local_date, location)
			internal = self.prayers.calculate(request)
			token.raise_if_cancelled()
			online_request = OnlinePrayerRequest(
				local_date, location.latitude, location.longitude,
				internal.metadata.effective_method, request.asr_method, request.high_latitude_rule,
			)
			return self.online_verifier.verify(online_request, internal, cancellation=token)

		self._run_async(
			_("Verifying today's prayer times online"),
			_("Contacting AlAdhan for a diagnostic comparison..."),
			verify,
			self._verification_success,
			parent=parent,
		)

	def _run_async(self, title: str, message: str, worker, on_success,
			parent: wx.Window | None = None) -> None:
		token = CancellationToken()
		self._tokens.add(token)
		state: dict[str, object] = {}
		dialog = _OperationDialog(parent or _interaction_parent(), title, message, token.cancel)
		dialog.Show()
		dialog.cancel_button.SetFocus()
		# Opening and focusing the dialog produces accessibility speech. Announce
		# after that focus settles so the explicit start message is not cut off.
		wx.CallLater(100, ui.message, message)

		def finish() -> None:
			self._tokens.discard(token)
			if not dialog.IsBeingDeleted():
				dialog.Destroy()
			if self._closed:
				return
			# Destruction restores focus to the invoking dialog. Deliver the result
			# after restoration so button and script invocations are equally audible.
			wx.CallLater(100, complete)

		def complete() -> None:
			if self._closed:
				return
			if "error" in state:
				error = state["error"]
				if isinstance(error, OperationCancelled):
					ui.message(_("The operation was cancelled."))
				else:
					log = (logHandler.log.warning
						if isinstance(error, (DataUpdateError, OnlinePrayerVerificationError, OSError))
						else logHandler.log.error)
					log("Awqati explicit operation failed: %s", error)
					ui.message(_("The operation failed. Your existing local data and settings were not changed."))
			else:
				on_success(state.get("result"))

		def run() -> None:
			try:
				state["result"] = worker(token)
			except Exception as error:
				state["error"] = error
			wx.CallAfter(finish)

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
