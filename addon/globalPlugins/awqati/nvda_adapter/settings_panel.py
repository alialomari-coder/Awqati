"""Task 3.3 dynamic settings sections for the single Awqati NVDA panel."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading
from typing import Callable, Sequence

import addonHandler
import globalVars
import languageHandler
import wx
import ui as nvda_ui

from .preview import preview_text
from .audio_service import AudioService
from .native_accessibility import set_spin_name
from ..application.settings_preview import PreviewLocationRequired
from gui.settingsDialogs import SettingsPanel

from ..domain import (
	AlertAction, AlertEventType, AlertOutputSettings, AnnouncementStyle, AsrMethod, CalculationMethod,
	CalendarId, ClockType, DateFormat, DayPeriod, EveningReference, FridayReference,
	HighLatitudeRule, HourSystem, MorningReference, PrayerEventName, SoundReference,
	SettingsValidationError, TimeRepresentation,
)
from ..domain.settings import DEFAULT_DAILY_WIRD_TEXT
from ..infrastructure import BundledCalculationMethodRepository, SoundFileService
from .settings_sections import (
	CALENDAR_EDIT_ORDER, PRIMARY_CALENDAR_ORDER, PRAYER_ACTIONS, PRAYER_EVENT_ORDER,
	RECURRING_ACTIONS, RECURRING_DHIKR_ORDER, SECTION_ORDER, STANDARD_ALERT_ACTIONS,
	SettingsSection, action_uses_sound, focus_target_for_path, hijri_adjustment_visible,
	is_rtl_language, N_,
)
from .sound_staging import (
	SoundPreparationCancelled, SoundStagingSession, collect_sound_reference_values,
)
from .ui import LocationControls, _context_or_raise, _parse_clock


addonHandler.initTranslation()
_: Callable[[str], str]

SECTION_LABELS = {
	SettingsSection.PRAYER: N_("Prayer times"),
	SettingsSection.CLOCK: N_("Clock"),
	SettingsSection.DATE: N_("Date"),
	SettingsSection.ADHKAR: N_("Dhikr alerts"),
}
PRAYER_LABELS = {
	PrayerEventName.FAJR: N_("Fajr"), PrayerEventName.SUNRISE: N_("Sunrise"),
	PrayerEventName.DHUHR: N_("Dhuhr"), PrayerEventName.ASR: N_("Asr"),
	PrayerEventName.MAGHRIB: N_("Maghrib"), PrayerEventName.ISHA: N_("Isha"),
	PrayerEventName.MIDNIGHT: N_("Midnight"), PrayerEventName.LAST_THIRD: N_("Start of the last third"),
}
ACTION_LABELS = {
	AlertAction.SILENT: N_("Silent"), AlertAction.SPEECH: N_("Speech only"),
	AlertAction.SOUND: N_("Sound file only"), AlertAction.SOUND_AND_SPEECH: N_("Sound file and speech"),
}
STYLE_LABELS = {
	AnnouncementStyle.DOUBLE: N_("Double"), AnnouncementStyle.FULL: N_("Full"),
	AnnouncementStyle.MODERATE: N_("Moderate"), AnnouncementStyle.SHORT: N_("Short"),
}
DATE_FORMAT_LABELS = {
	DateFormat.DOUBLE: N_("Double"), DateFormat.FULL: N_("Full"),
	DateFormat.MODERATE: N_("Moderate"), DateFormat.SHORT: N_("Short"),
}
CALENDAR_LABELS = {
	CalendarId.HIJRI_UMM_AL_QURA: N_("Lunar Hijri"), CalendarId.GREGORIAN: N_("Gregorian"),
	CalendarId.SAUDI_SOLAR_HIJRI: N_("Saudi Solar Hijri"),
	CalendarId.AFGHAN_SOLAR_HIJRI: N_("Afghan Solar Hijri"),
	CalendarId.PERSIAN_SOLAR_HIJRI: N_("Persian Solar Hijri"),
}
DHIKR_LABELS = {
	identity: label for identity, label in zip(RECURRING_DHIKR_ORDER, (
		N_("Subhan Allah"), N_("Alhamdu lillah"), N_("La ilaha illa Allah"), N_("Allahu Akbar"),
		N_("La hawla wa la quwwata illa billah"), N_("Astaghfiru Allah"),
		N_("Blessings upon the Prophet"), N_("Remember Allah and He will remember you"),
		N_("Do not forget the remembrance of Allah"),
	))
}


TIMED_ALERT_LABELS = {
	"afterFajr": (N_("Alert after Fajr:"), N_("Alert after Fajr, minutes")),
	"beforeSunrise": (N_("Alert before sunrise:"), N_("Alert before sunrise, minutes")),
	"afterSunrise": (N_("Alert after sunrise:"), N_("Alert after sunrise, minutes")),
	"afterAsr": (N_("Alert after Asr:"), N_("Alert after Asr, minutes")),
	"beforeMaghrib": (N_("Alert before Maghrib:"), N_("Alert before Maghrib, minutes")),
	"afterMaghrib": (N_("Alert after Maghrib:"), N_("Alert after Maghrib, minutes")),
}


def _translated(values: Sequence, labels: dict) -> list[str]:
	return [_(labels[value]) for value in values]


def _choice(parent: wx.Window, sizer: wx.Sizer, label: str, values: Sequence,
		labels: dict, selected, name: str | None = None) -> wx.Choice:
	sizer.Add(wx.StaticText(parent, label=_(label)), flag=wx.ALIGN_CENTER_VERTICAL)
	control = wx.Choice(parent, choices=_translated(values, labels), name=_(name) if name else _(label).rstrip(":"))
	control.SetSelection(values.index(selected))
	sizer.Add(control, flag=wx.EXPAND)
	return control


def _spin(parent: wx.Window, sizer: wx.Sizer, label: str, value: int,
		minimum: int, maximum: int, accessible_name: str | None = None) -> wx.SpinCtrl:
	text = wx.StaticText(parent, label=_(label))
	sizer.Add(text, flag=wx.ALIGN_CENTER_VERTICAL)
	control = wx.SpinCtrl(parent, min=minimum, max=maximum, initial=value, name=_(accessible_name or label).rstrip(":"))
	control.awqati_label = text
	if accessible_name:
		set_spin_name(control, _(accessible_name))
	sizer.Add(control, flag=wx.EXPAND)
	return control


def _panel(parent: wx.Window) -> tuple[wx.Panel, wx.FlexGridSizer]:
	panel = wx.Panel(parent)
	sizer = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
	sizer.AddGrowableCol(1, 1)
	panel.SetSizer(sizer)
	return panel, sizer


class AlertOutputEditor:
	"""Edit one output and physically rebuild its optional sound controls."""

	def __init__(self, parent: wx.Window, sizer: wx.Sizer, label: str,
			output: AlertOutputSettings, actions: Sequence[AlertAction], category: str,
			on_layout: Callable[[], None], sound_staging: SoundStagingSession, audio_service: AudioService,
			event_type: AlertEventType, register: Callable[[str, wx.Window], None], control_prefix: str,
			context: str | None = None) -> None:
		self.parent, self.sizer, self.output = parent, sizer, output
		self.context = context or _(label).rstrip(":")
		self._sound_spacer = None
		self.actions, self.category, self.on_layout = tuple(actions), category, on_layout
		self.sound_staging = sound_staging
		self.audio_service, self.event_type = audio_service, event_type
		self.register, self.control_prefix = register, control_prefix
		self._busy = False
		self.sizer.Add(wx.StaticText(parent, label=_(label)), flag=wx.ALIGN_CENTER_VERTICAL)
		self.action = wx.Choice(parent, choices=_translated(self.actions, ACTION_LABELS), name=_(label).rstrip(":"))
		self.action.SetSelection(self.actions.index(output.action))
		self.sizer.Add(self.action, flag=wx.EXPAND)
		self.register(f"{control_prefix}.action", self.action)
		self.action.Bind(wx.EVT_CHOICE, self._on_action)
		self.sound_panel: wx.Panel | None = None
		self._render_sound()

	def _on_action(self, event: wx.CommandEvent) -> None:
		self.output.action = self.actions[self.action.GetSelection()]
		self._render_sound()
		self.action.SetFocus()
		event.Skip()

	def _render_sound(self) -> None:
		if self.sound_panel is not None:
			self.sizer.Remove(list(self.sizer.GetChildren()).index(self._sound_spacer))
			self._sound_spacer = None
			self.sizer.Detach(self.sound_panel)
			self.sound_panel.Destroy()
			self.sound_panel = None
		if not action_uses_sound(self.output.action):
			self.register(f"{self.control_prefix}.sound", self.action)
			self.on_layout()
			return
		self._sound_spacer = self.sizer.Add((1, 1))
		self.sound_panel = wx.Panel(self.parent)
		row = wx.BoxSizer(wx.HORIZONTAL)
		self.choose = wx.Button(self.sound_panel, label=_("Choose sound file — {context}").format(context=self.context))
		self.preview = wx.Button(self.sound_panel, label=_("Preview sound — {context}").format(context=self.context))
		self.remove = wx.Button(self.sound_panel, label=_("Remove custom sound — {context}").format(context=self.context))
		for button in (self.choose, self.preview, self.remove):
			row.Add(button, flag=wx.RIGHT, border=8)
		self.register(f"{self.control_prefix}.sound", self.choose)
		self.sound_panel.SetSizer(row)
		self.sound_panel.MoveAfterInTabOrder(self.action)
		self.sizer.Add(self.sound_panel, flag=wx.EXPAND)
		self.choose.Bind(wx.EVT_BUTTON, self._on_choose)
		self.preview.Bind(wx.EVT_BUTTON, self._on_preview)
		self.remove.Bind(wx.EVT_BUTTON, self._on_remove)
		self._update_buttons()
		self.on_layout()

	@property
	def _root(self) -> Path:
		return Path(globalVars.appArgs.configPath) / "awqati"

	def _selected_path(self) -> Path | None:
		return self.sound_staging.resolve(self.output.sound) if self.output.sound is not None else None

	def _update_buttons(self) -> None:
		custom = self._selected_path()
		available = custom is not None and custom.is_file()
		if not available:
			available = self.audio_service.files.default_path(self.event_type) is not None
		self.preview.Enable(available and not self.audio_service.busy)
		self.remove.Enable(self.output.sound is not None)
		self.choose.Enable(not self._busy)
		self.choose.SetLabel((_("Selecting sound file — {context}…") if self._busy else _("Choose sound file — {context}")).format(context=self.context))

	def _on_choose(self, event: wx.CommandEvent) -> None:
		if self._busy:
			event.Skip()
			return
		target_dir = self.audio_service.files.ensure_sound_directories()
		dialog = wx.FileDialog(self.parent, message=_("Choose a WAV sound file"),
			defaultDir=str(target_dir), wildcard=_("Wave audio files (*.wav)|*.wav"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			source = Path(dialog.GetPath())
			if source.suffix.casefold() != ".wav":
				wx.MessageBox(_("Only WAV sound files are supported."), _("Sound file error"),
					wx.OK | wx.ICON_ERROR, self.parent)
				return
			if not self.sound_staging.begin_preparation():
				return
			self._busy = True
			self._update_buttons()
			try:
				threading.Thread(
					target=self._choose_worker,
					args=(source,),
					name="AwqatiSoundSelection",
					daemon=True,
				).start()
			except RuntimeError:
				self.sound_staging.finish_preparation()
				self._busy = False
				raise
		except (OSError, RuntimeError) as error:
			wx.MessageBox(_("The sound file could not be selected. Check that it is an accessible WAV file."),
				_("Sound file error"), wx.OK | wx.ICON_ERROR, self.parent)
		finally:
			dialog.Destroy()
			if not self._busy:
				self._update_buttons()
				self.choose.SetFocus()
		event.Skip()

	def _choose_worker(self, source: Path) -> None:
		try:
			reference = self.sound_staging.prepare(source, self.category)
		except SoundPreparationCancelled:
			reference, error = None, None
		except Exception as caught:
			reference, error = None, caught
		else:
			error = None
		wx.CallAfter(self._finish_choose, reference, error)

	def _finish_choose(self, reference: SoundReference | None, error: Exception | None) -> None:
		self.sound_staging.finish_preparation()
		self._busy = False
		if reference is not None:
			self.output.sound = reference
		try:
			if error is not None:
				wx.MessageBox(_("The sound file could not be selected. Check that it is an accessible WAV file."),
					_("Sound file error"), wx.OK | wx.ICON_ERROR, self.parent)
			if self.sound_panel is not None:
				self._update_buttons()
				self.choose.SetFocus()
		except RuntimeError:
			# The dynamic panel or settings dialog may have closed while the worker ran.
			pass

	def _on_preview(self, event: wx.CommandEvent) -> None:
		path = self._selected_path()
		if not self.audio_service.play_preview(self.event_type, path, lambda: None, self._finish_preview):
			wx.MessageBox(_("The selected sound could not be played."), _("Sound preview"),
				wx.OK | wx.ICON_WARNING, self.parent)
		self.preview.SetFocus()
		event.Skip()

	def _finish_preview(self, result) -> None:
		if not result.completed and not result.cancelled:
			wx.MessageBox(_("The selected sound could not be played."), _("Sound preview"),
				wx.OK | wx.ICON_WARNING, self.parent)
		if self.sound_panel is not None:
			self._update_buttons()

	def _on_remove(self, event: wx.CommandEvent) -> None:
		self.output.sound = None
		self._update_buttons()
		self.remove.SetFocus()
		event.Skip()


class AwqatiSettingsPanel(SettingsPanel):
	title = _("Awqati")

	def makeSettings(self, settingsSizer: wx.Sizer) -> None:
		self.SetLayoutDirection(
			wx.Layout_RightToLeft if is_rtl_language(languageHandler.getLanguage())
			else wx.Layout_LeftToRight
		)
		context = _context_or_raise()
		self._settings = context.settings
		self._draft = context.settings.open_draft()
		self._controls: dict[str, wx.Window] = {}
		self._validated_candidate = None
		user_data_root = Path(globalVars.appArgs.configPath) / "awqati"
		self._audio_files = SoundFileService(user_data_root, Path(__file__).resolve().parents[1])
		self._audio = AudioService(self._audio_files)
		self._sound_staging = SoundStagingSession(user_data_root, self._audio_files)
		current = self._draft.settings
		self.location_controls = LocationControls(self, settingsSizer, context.location_setup, current.location)
		self._register("location", self.location_controls.custom_button)
		self.show_qibla = wx.Button(self, label=_("Show Qibla direction"))
		settingsSizer.Add(self.show_qibla, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
		self._register("showQibla", self.show_qibla)
		self.show_qibla.Bind(wx.EVT_BUTTON, lambda event: (
			context.show_qibla() if context.show_qibla else None, event.Skip()))
		self.all_alerts = wx.CheckBox(self, label=_("Enable all automatic alerts"))
		self.all_alerts.SetValue(current.general.all_automatic_alerts_enabled)
		settingsSizer.Add(self.all_alerts, flag=wx.ALL, border=8)
		self._register("allAlerts", self.all_alerts)
		self.quiet_enabled = wx.CheckBox(self, label=_("Enable quiet hours"))
		self.quiet_enabled.SetValue(current.general.quiet_hours.enabled)
		settingsSizer.Add(self.quiet_enabled, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
		self._register("quietEnabled", self.quiet_enabled)
		self.quiet_panel = wx.Panel(self)
		quiet_sizer = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
		quiet_sizer.AddGrowableCol(1, 1)
		quiet = current.general.quiet_hours
		self.quiet_start = wx.TextCtrl(self.quiet_panel, value=f"{quiet.start.hour:02d}:{quiet.start.minute:02d}", name=_("Quiet hours start"))
		self.quiet_end = wx.TextCtrl(self.quiet_panel, value=f"{quiet.end.hour:02d}:{quiet.end.minute:02d}", name=_("Quiet hours end"))
		self._register("quietStart", self.quiet_start)
		self._register("quietEnd", self.quiet_end)
		for label, control in ((N_("Quiet hours start, HH:MM:"), self.quiet_start), (N_("Quiet hours end, HH:MM:"), self.quiet_end)):
			quiet_sizer.Add(wx.StaticText(self.quiet_panel, label=_(label)), flag=wx.ALIGN_CENTER_VERTICAL)
			quiet_sizer.Add(control, flag=wx.EXPAND)
		self.apply_prayer = wx.CheckBox(self.quiet_panel, label=_("Apply quiet hours to prayer-time alerts"))
		self.apply_prayer.SetValue(quiet.apply_to_prayer_alerts)
		self._register("quietPrayer", self.apply_prayer)
		quiet_sizer.Add((1, 1)); quiet_sizer.Add(self.apply_prayer)
		self.quiet_panel.SetSizer(quiet_sizer)
		settingsSizer.Add(self.quiet_panel, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=8)
		self.quiet_enabled.Bind(wx.EVT_CHECKBOX, self._on_quiet_toggle)
		self.quiet_panel.Show(quiet.enabled)

		actions = wx.BoxSizer(wx.HORIZONTAL)
		self.copy_diagnostics = wx.Button(self, label=_("Copy diagnostic information"))
		self.check_data_updates = wx.Button(self, label=_("Check for data updates"))
		actions.Add(self.copy_diagnostics, flag=wx.RIGHT, border=8)
		actions.Add(self.check_data_updates)
		settingsSizer.Add(actions, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
		self._register("copyDiagnostics", self.copy_diagnostics)
		self._register("checkDataUpdates", self.check_data_updates)
		self.copy_diagnostics.Bind(wx.EVT_BUTTON, lambda event: (
			context.copy_diagnostics() if context.copy_diagnostics else None, event.Skip()))
		self.check_data_updates.Bind(wx.EVT_BUTTON, lambda event: (
			context.check_data_updates() if context.check_data_updates else None, event.Skip()))

		settingsSizer.Add(wx.StaticText(self, label=_("Choose settings section:")), flag=wx.LEFT | wx.RIGHT, border=8)
		self.section_choice = wx.Choice(self, choices=_translated(SECTION_ORDER, SECTION_LABELS),
			name=_("Choose settings section"))
		self.section_choice.SetSelection(0)
		settingsSizer.Add(self.section_choice, flag=wx.ALL | wx.EXPAND, border=8)
		self._register("section", self.section_choice)
		self._settings_sizer = settingsSizer
		self._section_panel: wx.Panel | None = None
		self._section = SECTION_ORDER[0]
		self.section_choice.Bind(wx.EVT_CHOICE, self._on_section)
		self._render_section()

	def _register(self, key: str, control: wx.Window) -> None:
		self._controls[key] = control

	def postInit(self) -> None:
		self.location_controls.country.SetFocus()

	def _layout(self) -> None:
		self.Layout()
		if hasattr(self, "FitInside"):
			self.FitInside()
		self._sendLayoutUpdatedEvent()

	def _on_quiet_toggle(self, event: wx.CommandEvent) -> None:
		self.quiet_panel.Show(self.quiet_enabled.GetValue())
		self._layout(); event.Skip()

	def _on_section(self, event: wx.CommandEvent) -> None:
		self._section = SECTION_ORDER[self.section_choice.GetSelection()]
		self._render_section()
		self.section_choice.SetFocus()
		event.Skip()

	def _render_section(self) -> None:
		if self._section_panel is not None:
			self._settings_sizer.Detach(self._section_panel)
			self._section_panel.Destroy()
		builder = {
			SettingsSection.PRAYER: self._build_prayer,
			SettingsSection.CLOCK: self._build_clock,
			SettingsSection.DATE: self._build_date,
			SettingsSection.ADHKAR: self._build_adhkar,
		}[self._section]
		self._section_panel = builder()
		self._settings_sizer.Add(self._section_panel, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, border=8)
		self._layout()

	def _build_prayer(self) -> wx.Panel:
		panel = wx.Panel(self); outer = wx.BoxSizer(wx.VERTICAL); panel.SetSizer(outer)
		settings = self._draft.settings.prayer
		enabled = wx.CheckBox(panel, label=_("Enable prayer-time alerts")); enabled.SetValue(settings.alerts_enabled)
		self._register("prayer.enabled", enabled)
		enabled.Bind(wx.EVT_CHECKBOX, lambda e: (setattr(settings, "alerts_enabled", enabled.GetValue()), e.Skip()))
		outer.Add(enabled, flag=wx.BOTTOM, border=8)
		open_daily = wx.Button(panel, label=_("Open daily prayer times window"))
		outer.Add(open_daily, flag=wx.TOP, border=8)
		self._register("prayer.openDailyPrayerTimesWindow", open_daily)
		context = _context_or_raise()
		open_daily.Bind(wx.EVT_BUTTON, lambda event: (
			context.show_prayer_times() if context.show_prayer_times else None, event.Skip()))
		verify = wx.Button(panel, label=_("Verify today's prayer times online..."))
		outer.Add(verify, flag=wx.TOP | wx.BOTTOM, border=8)
		self._register("prayer.verifyOnline", verify)
		verify.Bind(wx.EVT_BUTTON, lambda event: (
			context.verify_prayer_times() if context.verify_prayer_times else None, event.Skip()))
		grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8); grid.AddGrowableCol(1, 1); outer.Add(grid, flag=wx.EXPAND)
		method_values = tuple(CalculationMethod)
		method_labels = {CalculationMethod.AUTO: N_("Automatic by country")}
		provider = BundledCalculationMethodRepository()
		for method in method_values[1:]: method_labels[method] = provider.get_method(method).name
		method = _choice(panel, grid, N_("Prayer calculation method:"), method_values, method_labels, settings.calculation_method)
		self._register("prayer.calculationMethod", method)
		method.Bind(wx.EVT_CHOICE, lambda e: (setattr(settings, "calculation_method", method_values[method.GetSelection()]), self._update_effective_method(provider), e.Skip()))
		self._effective_method = wx.StaticText(panel, label="")
		grid.Add(wx.StaticText(panel, label=_("Effective automatic method:")), flag=wx.ALIGN_CENTER_VERTICAL)
		grid.Add(self._effective_method, flag=wx.EXPAND)
		self._prayer_method_choice = method; self._update_effective_method(provider)
		asr_values = (AsrMethod.STANDARD, AsrMethod.HANAFI); asr_labels = {AsrMethod.STANDARD: N_("Standard (Shafi, Maliki, Hanbali)"), AsrMethod.HANAFI: N_("Hanafi")}
		asr = _choice(panel, grid, N_("Asr calculation:"), asr_values, asr_labels, settings.asr_method)
		self._register("prayer.asrMethod", asr)
		asr.Bind(wx.EVT_CHOICE, lambda e: (setattr(settings, "asr_method", asr_values[asr.GetSelection()]), e.Skip()))
		high_values = tuple(HighLatitudeRule); high_labels = {HighLatitudeRule.AUTO:N_("Automatic"), HighLatitudeRule.ANGLE_BASED:N_("Angle based"), HighLatitudeRule.ONE_SEVENTH:N_("One seventh"), HighLatitudeRule.NIGHT_MIDDLE:N_("Middle of the night"), HighLatitudeRule.NEAREST_LATITUDE:N_("Nearest latitude")}
		high = _choice(panel, grid, N_("High-latitude handling:"), high_values, high_labels, settings.high_latitude_rule)
		self._register("prayer.highLatitudeRule", high)
		high.Bind(wx.EVT_CHOICE, lambda e: (setattr(settings, "high_latitude_rule", high_values[high.GetSelection()]), e.Skip()))
		current = _spin(panel, grid, N_("Keep prayer current after Iqama, minutes:"), settings.current_prayer_after_iqama_minutes, 0, 180)
		self._register("prayer.currentDuration", current)
		current.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(settings, "current_prayer_after_iqama_minutes", current.GetValue()), e.Skip()))
		outer.Add(wx.StaticText(panel, label=_("Time to configure:")), flag=wx.TOP, border=8)
		self._prayer_event_choice = wx.Choice(panel, choices=_translated(PRAYER_EVENT_ORDER, PRAYER_LABELS), name=_("Time to configure")); self._prayer_event_choice.SetSelection(0)
		self._register("prayer.event", self._prayer_event_choice)
		outer.Add(self._prayer_event_choice, flag=wx.EXPAND)
		self._prayer_event_host = wx.BoxSizer(wx.VERTICAL); outer.Add(self._prayer_event_host, flag=wx.TOP | wx.EXPAND, border=8)
		self._prayer_event_panel = None; self._prayer_event_choice.Bind(wx.EVT_CHOICE, self._on_prayer_event); self._render_prayer_event(panel)
		return panel

	def _update_effective_method(self, provider) -> None:
		if self._draft.settings.prayer.calculation_method is not CalculationMethod.AUTO:
			self._effective_method.SetLabel(_("Manual selection")); return
		stored = self.location_controls.pending
		if stored is None or not stored.country_code:
			self._effective_method.SetLabel(_("A selected country is required")); return
		effective = provider.country_resolver.resolve(stored.country_code)
		self._effective_method.SetLabel(_(provider.get_method(effective).name))

	def _on_prayer_event(self, event: wx.CommandEvent) -> None:
		parent = self._prayer_event_choice.GetParent(); self._render_prayer_event(parent)
		self._prayer_event_choice.SetFocus(); event.Skip()

	def _render_prayer_event(self, parent: wx.Window) -> None:
		if self._prayer_event_panel is not None:
			self._prayer_event_host.Detach(self._prayer_event_panel); self._prayer_event_panel.Destroy()
		name = PRAYER_EVENT_ORDER[self._prayer_event_choice.GetSelection()]
		event_settings = self._draft.settings.prayer.events[name]
		panel, grid = _panel(parent); self._prayer_event_panel = panel; self._prayer_event_host.Add(panel, flag=wx.EXPAND)
		correction = _spin(panel, grid, N_("Time correction, minutes:"), self._draft.settings.prayer.corrections_minutes[name], -30, 30)
		self._register("prayer.correction", correction)
		correction.Bind(wx.EVT_SPINCTRL, lambda e: (self._draft.settings.prayer.corrections_minutes.__setitem__(name, correction.GetValue()), e.Skip()))
		pre = _spin(panel, grid, N_("Alert before the event:"), event_settings.pre_alert_minutes, 0, 180, N_("Alert before the event, minutes"))
		self._register("prayer.preMinutes", pre)
		pre.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings, "pre_alert_minutes", pre.GetValue()), e.Skip()))
		AlertOutputEditor(panel, grid, N_("Alert action before the event:"), event_settings.pre_alert, PRAYER_ACTIONS,
			"alerts", self._layout, self._sound_staging, self._audio, AlertEventType.PRAYER_PRE_ALERT, self._register, "prayer.pre", _("Before {time}").format(time=_(PRAYER_LABELS[name])))
		AlertOutputEditor(panel, grid, N_("Alert action at the event:"), event_settings.at_time_alert, PRAYER_ACTIONS,
			"alerts", self._layout, self._sound_staging, self._audio, AlertEventType.PRAYER_TIME, self._register, "prayer.atTime", _("At {time}").format(time=_(PRAYER_LABELS[name])))
		if event_settings.iqama is not None:
			delay = _spin(panel, grid, N_("Minutes between Adhan and Iqama:"), event_settings.iqama.delay_minutes, 0, 180)
			before = _spin(panel, grid, N_("Alert before Iqama, minutes:"), event_settings.iqama.alert_before_minutes, 0, 180)
			self._register("prayer.iqamaDelay", delay)
			self._register("prayer.iqamaBefore", before)
			delay.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings.iqama, "delay_minutes", delay.GetValue()), e.Skip()))
			before.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings.iqama, "alert_before_minutes", before.GetValue()), e.Skip()))
			AlertOutputEditor(panel, grid, N_("Alert action before Iqama:"), event_settings.iqama.alert, PRAYER_ACTIONS,
				"alerts", self._layout, self._sound_staging, self._audio, AlertEventType.IQAMA_PRE_ALERT, self._register, "prayer.iqama", _("Before Iqama — {time}").format(time=_(PRAYER_LABELS[name])))
		else:
			post = _spin(panel, grid, N_("Alert after the event:"), event_settings.post_alert_minutes, 0, 180, N_("Alert after the event, minutes"))
			self._register("prayer.postMinutes", post)
			post.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings, "post_alert_minutes", post.GetValue()), e.Skip()))
			AlertOutputEditor(panel, grid, N_("Alert action after the event:"), event_settings.post_alert, PRAYER_ACTIONS,
				"alerts", self._layout, self._sound_staging, self._audio, AlertEventType.PRAYER_POST_ALERT, self._register, "prayer.post", _("After {time}").format(time=_(PRAYER_LABELS[name])))
		self._layout()

	def _build_clock(self) -> wx.Panel:
		panel = wx.Panel(self); outer = wx.BoxSizer(wx.VERTICAL); panel.SetSizer(outer); settings = self._draft.settings.clock
		outer.Add(wx.StaticText(panel, label=_("Zawali time is always primary; Ghurubi time is always additional.")), flag=wx.BOTTOM, border=8)
		outer.Add(wx.StaticText(panel, label=_("Choose clock settings:")))
		clock_labels = {ClockType.ZAWALI:N_("Zawali"), ClockType.GHURUBI:N_("Ghurubi")}
		self._clock_choice = wx.Choice(panel, choices=_translated(tuple(ClockType), clock_labels), name=_("Choose clock settings")); self._clock_choice.SetSelection(0); outer.Add(self._clock_choice, flag=wx.EXPAND)
		self._register("clock.selector", self._clock_choice)
		self._clock_host = wx.BoxSizer(wx.VERTICAL); outer.Add(self._clock_host, flag=wx.TOP | wx.EXPAND, border=8); self._clock_panel = None
		self._clock_choice.Bind(wx.EVT_CHOICE, self._on_clock_type); self._render_clock_type(panel)
		enabled = wx.CheckBox(panel, label=_("Enable automatic clock alerts")); enabled.SetValue(settings.automatic_alert_enabled); outer.Add(enabled, flag=wx.TOP, border=8)
		self._register("clock.enabled", enabled)
		enabled.Bind(wx.EVT_CHECKBOX, lambda e: (setattr(settings, "automatic_alert_enabled", enabled.GetValue()), e.Skip()))
		for attr, label in (("on_quarter",N_("Alert at quarter past the hour")),("on_half",N_("Alert at half past the hour")),("on_three_quarters",N_("Alert at three quarters past the hour")),("on_hour",N_("Alert on the hour"))):
			box = wx.CheckBox(panel, label=_(label)); box.SetValue(getattr(settings.intervals, attr)); outer.Add(box)
			self._register(f"clock.interval.{attr}", box)
			box.Bind(wx.EVT_CHECKBOX, lambda e, a=attr, b=box: (setattr(settings.intervals, a, b.GetValue()), e.Skip()))
		alert_panel, grid = _panel(panel); outer.Add(alert_panel, flag=wx.TOP | wx.EXPAND, border=8)
		AlertOutputEditor(alert_panel, grid, N_("Clock alert action:"), settings.alert, STANDARD_ALERT_ACTIONS,
			"clock", self._layout, self._sound_staging, self._audio, AlertEventType.CLOCK, self._register, "clock.alert")
		return panel

	def _on_clock_type(self, event: wx.CommandEvent) -> None:
		self._render_clock_type(self._clock_choice.GetParent()); self._clock_choice.SetFocus(); event.Skip()

	def _render_clock_type(self, parent: wx.Window) -> None:
		if self._clock_panel is not None: self._clock_host.Detach(self._clock_panel); self._clock_panel.Destroy()
		identity = tuple(ClockType)[self._clock_choice.GetSelection()]; value = self._draft.settings.clock.presentations[identity]
		panel, grid = _panel(parent); self._clock_panel = panel; self._clock_host.Add(panel, flag=wx.EXPAND)
		panel.MoveAfterInTabOrder(self._clock_choice)
		styles = tuple(AnnouncementStyle); style = _choice(panel, grid, N_("Speech format:"), styles, STYLE_LABELS, value.style)
		self._register("clock.style", style)
		style.Bind(wx.EVT_CHOICE, lambda e: (setattr(value, "style", styles[style.GetSelection()]), e.Skip()))
		hours = tuple(HourSystem); hour_labels={HourSystem.TWELVE:N_("12-hour"),HourSystem.TWENTY_FOUR:N_("24-hour")}; hour = _choice(panel, grid, N_("Hour system:"), hours, hour_labels, value.hour_system)
		self._register("clock.hourSystem", hour)
		hour.Bind(wx.EVT_CHOICE, lambda e: (setattr(value, "hour_system", hours[hour.GetSelection()]), e.Skip()))
		reps=tuple(TimeRepresentation); rep_labels={TimeRepresentation.NUMERIC:N_("Numbers"),TimeRepresentation.WORDS:N_("Words")}; rep=_choice(panel,grid,N_("Speech representation:"),reps,rep_labels,value.representation)
		self._register("clock.representation", rep)
		rep.Bind(wx.EVT_CHOICE, lambda e:(setattr(value,"representation",reps[rep.GetSelection()]),e.Skip()))
		for attr,label in (("speak_seconds",N_("Speak seconds")),("speak_zero_minute",N_("Say “zero minutes” when there are no minutes"))):
			box=wx.CheckBox(panel,label=_(label));box.SetValue(getattr(value,attr));grid.Add((1,1));grid.Add(box)
			self._register("clock.speakSeconds" if attr == "speak_seconds" else "clock.speakZeroMinute", box)
			box.Bind(wx.EVT_CHECKBOX,lambda e,a=attr,b=box:(setattr(value,a,b.GetValue()),e.Skip()))
		self._add_preview(panel, grid, "clock", identity)
		self._layout()

	def _build_date(self) -> wx.Panel:
		panel=wx.Panel(self);outer=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(outer);settings=self._draft.settings.calendar
		grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=8);grid.AddGrowableCol(1,1);outer.Add(grid,flag=wx.TOP|wx.EXPAND,border=8)
		primary=_choice(panel,grid,N_("Primary calendar:"),PRIMARY_CALENDAR_ORDER,CALENDAR_LABELS,settings.primary_calendar)
		self._register("calendar.primary", primary)
		primary.Bind(wx.EVT_CHOICE,lambda e:(setattr(settings,"primary_calendar",PRIMARY_CALENDAR_ORDER[primary.GetSelection()]),e.Skip()))
		include=wx.CheckBox(panel,label=_("Include Arabian calendar information in astronomical daily information"));include.SetValue(settings.include_arabian_calendar_in_daily_info);outer.Add(include,flag=wx.TOP,border=8)
		self._register("calendar.includeArabian", include)
		include.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(settings,"include_arabian_calendar_in_daily_info",include.GetValue()),e.Skip()))
		open_daily=wx.Button(panel,label=_("Open daily information window"));outer.Add(open_daily,flag=wx.TOP,border=8)
		self._register("calendar.openDailyInfoWindow", open_daily)
		context=_context_or_raise()
		open_daily.Bind(wx.EVT_BUTTON,lambda event:(context.show_daily_info() if context.show_daily_info else None,event.Skip()))
		outer.Add(wx.StaticText(panel,label=_("Choose calendar to configure:")))
		self._calendar_choice=wx.Choice(panel,choices=_translated(CALENDAR_EDIT_ORDER,CALENDAR_LABELS),name=_("Choose calendar to configure"));self._calendar_choice.SetSelection(0);outer.Add(self._calendar_choice,flag=wx.EXPAND)
		self._register("calendar.selector", self._calendar_choice)
		self._calendar_host=wx.BoxSizer(wx.VERTICAL);outer.Add(self._calendar_host,flag=wx.TOP|wx.EXPAND,border=8);self._calendar_panel=None
		self._calendar_choice.Bind(wx.EVT_CHOICE,self._on_calendar);self._render_calendar(panel)
		return panel

	def _on_calendar(self,event:wx.CommandEvent)->None:
		self._render_calendar(self._calendar_choice.GetParent());self._calendar_choice.SetFocus();event.Skip()

	def _render_calendar(self,parent:wx.Window)->None:
		if self._calendar_panel is not None:self._calendar_host.Detach(self._calendar_panel);self._calendar_panel.Destroy()
		identity=CALENDAR_EDIT_ORDER[self._calendar_choice.GetSelection()];settings=self._draft.settings.calendar;panel,grid=_panel(parent);self._calendar_panel=panel;self._calendar_host.Add(panel,flag=wx.EXPAND)
		formats=tuple(DateFormat);fmt=_choice(panel,grid,N_("Date format:"),formats,DATE_FORMAT_LABELS,settings.formats[identity]);self._date_format_choice=fmt
		self._register("calendar.format", fmt)
		adjust_label=wx.StaticText(panel,label=_("Lunar Hijri correction, days:"));grid.Add(adjust_label,flag=wx.ALIGN_CENTER_VERTICAL)
		adjust=wx.SpinCtrl(panel,min=-2,max=2,initial=settings.hijri_adjustment_days,name=_("Lunar Hijri correction, days"));grid.Add(adjust,flag=wx.EXPAND)
		self._register("calendar.adjustment", adjust)
		def update_adjustment_visibility():
			visible=hijri_adjustment_visible(identity,settings.formats[identity]);adjust_label.Show(visible);adjust.Show(visible);self._layout()
		def changed(event):
			settings.formats[identity]=formats[fmt.GetSelection()];update_adjustment_visibility();fmt.SetFocus();event.Skip()
		fmt.Bind(wx.EVT_CHOICE,changed)
		adjust.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(settings,"hijri_adjustment_days",adjust.GetValue()),e.Skip()))
		update_adjustment_visibility()
		self._add_preview(panel, grid, "date", identity)


	def _add_preview(self, parent, grid, kind, identity):
		button = wx.Button(parent, label=_("Preview speech"))
		grid.Add((1, 1)); grid.Add(button)
		self._register(f"{kind}.preview", button)
		busy = False
		def finish(text, error):
			nonlocal busy
			busy = False
			if not button:
				return
			button.SetFocus()
			if isinstance(error, PreviewLocationRequired):
				nvda_ui.message(_("No location has been assigned. Please set it in Awqati settings and try again."))
			elif error is not None:
				wx.MessageBox(_("The preview could not be prepared. Check the selected settings and try again."),
					_("Speech preview"), wx.OK | wx.ICON_WARNING, self)
				button.SetFocus()
			else:
				nvda_ui.message(text)
		def worker(snapshot, language):
			try:
				text = preview_text(snapshot, kind, identity, language)
			except Exception as error:
				wx.CallAfter(finish, None, error)
			else:
				wx.CallAfter(finish, text, None)
		def activate(event):
			nonlocal busy
			if not busy:
				# Capture only preview inputs; unrelated validation belongs to Apply.
				snapshot = deepcopy(self._draft.settings)
				snapshot.location = self.location_controls.pending
				if kind == "date":
					snapshot.calendar.hijri_adjustment_days = self._controls["calendar.adjustment"].GetValue()
				busy = True
				language = languageHandler.getLanguage().split("_")[0]
				threading.Thread(target=worker, args=(snapshot, language), name="AwqatiSpeechPreview", daemon=True).start()
			event.Skip()
		button.Bind(wx.EVT_BUTTON, activate)

	def _build_adhkar(self)->wx.Panel:
		panel=wx.Panel(self);outer=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(outer);settings=self._draft.settings.adhkar
		enabled=wx.CheckBox(panel,label=_("Enable Dhikr alerts"));enabled.SetValue(settings.alerts_enabled);outer.Add(enabled,flag=wx.BOTTOM,border=8)
		self._register("adhkar.enabled", enabled)
		enabled.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(settings,"alerts_enabled",enabled.GetValue()),e.Skip()))
		self._adhkar_hosts={};self._adhkar_panels={};self._adhkar_containers={}
		functions=(("morning",N_("Enable morning Dhikr"),settings.morning),("evening",N_("Enable evening Dhikr"),settings.evening),("friday",N_("Enable Friday hour reminder"),settings.friday_hour),("wird",N_("Enable daily Wird"),settings.daily_wird),("recurring",N_("Enable recurring Dhikr reminder"),settings.recurring))
		for key,label,value in functions:
			container=wx.Panel(panel);stack=wx.BoxSizer(wx.VERTICAL);container.SetSizer(stack)
			outer.Add(container,flag=wx.TOP|wx.EXPAND,border=8);self._adhkar_containers[key]=container
			box=wx.CheckBox(container,label=_(label));box.SetValue(value.enabled);stack.Add(box)
			self._register(f"{key}.enabled", box)
			host=wx.BoxSizer(wx.VERTICAL);stack.Add(host,flag=wx.EXPAND);self._adhkar_hosts[key]=host;self._adhkar_panels[key]=None
			box.Bind(wx.EVT_CHECKBOX,lambda e,k=key,v=value,b=box:(setattr(v,"enabled",b.GetValue()),self._render_adhkar_child(panel,k),b.SetFocus(),e.Skip()))
			self._render_adhkar_child(panel,key)
		return panel

	def _render_adhkar_child(self,parent:wx.Window,key:str)->None:
		parent=self._adhkar_containers[key]
		host=self._adhkar_hosts[key];old=self._adhkar_panels[key]
		if old is not None:host.Detach(old);old.Destroy();self._adhkar_panels[key]=None
		settings=self._draft.settings.adhkar;value={"morning":settings.morning,"evening":settings.evening,"friday":settings.friday_hour,"wird":settings.daily_wird,"recurring":settings.recurring}[key]
		if not value.enabled:self._layout();return
		panel,grid=_panel(parent);self._adhkar_panels[key]=panel;host.Add(panel,flag=wx.LEFT|wx.EXPAND,border=16)
		if key in {"morning","evening","friday"}:self._build_timed_adhkar(panel,grid,key,value)
		elif key=="wird":self._build_wird(panel,grid,value)
		else:self._build_recurring(panel,grid,value)
		self._layout()

	def _build_timed_adhkar(self,panel,grid,key,value)->None:
		if key=="morning":values=tuple(MorningReference);labels={MorningReference.AFTER_FAJR:N_("After Fajr"),MorningReference.BEFORE_SUNRISE:N_("Before sunrise"),MorningReference.AFTER_SUNRISE:N_("After sunrise")}
		elif key=="evening":values=tuple(EveningReference);labels={EveningReference.AFTER_ASR:N_("After Asr"),EveningReference.BEFORE_MAGHRIB:N_("Before Maghrib"),EveningReference.AFTER_MAGHRIB:N_("After Maghrib")}
		else:values=tuple(FridayReference);labels={FridayReference.AFTER_ASR:N_("After Asr"),FridayReference.BEFORE_MAGHRIB:N_("Before Maghrib")}
		reference_label={"morning":N_("Morning Dhikr reference time:"),"evening":N_("Evening Dhikr reference time:"),"friday":N_("Friday hour reference time:")}[key]
		reference = _choice(panel, grid, reference_label, values, labels, value.reference)
		label, name = TIMED_ALERT_LABELS[value.reference.value]
		minutes = _spin(panel, grid, label, value.minutes, 0, 180, name)
		minutes.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(value, "minutes", minutes.GetValue()), e.Skip()))
		def change_reference(event):
			value.reference = values[reference.GetSelection()]
			label, name = TIMED_ALERT_LABELS[value.reference.value]
			minutes.awqati_label.SetLabel(_(label))
			set_spin_name(minutes, _(name))
			panel.Layout()
			event.Skip()
		reference.Bind(wx.EVT_CHOICE, change_reference)
		action_label = N_("Alert action:")
		self._register(f"{key}.reference", reference)
		self._register(f"{key}.minutes", minutes)
		event_type = {"morning": AlertEventType.MORNING_ADHKAR, "evening": AlertEventType.EVENING_ADHKAR,
			"friday": AlertEventType.FRIDAY_HOUR}[key]
		AlertOutputEditor(panel, grid, action_label, value.alert, STANDARD_ALERT_ACTIONS,
			"adhkar", self._layout, self._sound_staging, self._audio, event_type, self._register, key, _(reference_label).rstrip(":"))

	def _build_wird(self,panel,grid,value)->None:
		display_text = _("Do not forget your daily Wird.") if value.text == DEFAULT_DAILY_WIRD_TEXT else value.text
		grid.Add(wx.StaticText(panel,label=_("Daily Wird reminder text:")),flag=wx.ALIGN_CENTER_VERTICAL);text=wx.TextCtrl(panel,value=display_text,name=_("Daily Wird reminder text"));grid.Add(text,flag=wx.EXPAND);text.Bind(wx.EVT_TEXT,lambda e:(setattr(value,"text",text.GetValue()),e.Skip()))
		hour=_spin(panel,grid,N_("Daily Wird hour (1 to 12):"),value.hour,1,12);minute=_spin(panel,grid,N_("Daily Wird minute (0 to 59):"),value.minute,0,59)
		self._register("wird.text", text)
		self._register("wird.hour", hour)
		self._register("wird.minute", minute)
		hour.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"hour",hour.GetValue()),e.Skip()));minute.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"minute",minute.GetValue()),e.Skip()))
		periods=tuple(DayPeriod);labels={DayPeriod.AM:N_("AM"),DayPeriod.PM:N_("PM")};period=_choice(panel,grid,N_("Daily Wird period:"),periods,labels,value.period);period.Bind(wx.EVT_CHOICE,lambda e:(setattr(value,"period",periods[period.GetSelection()]),e.Skip()))
		self._register("wird.period", period)
		AlertOutputEditor(panel, grid, N_("Daily Wird alert action:"), value.alert, STANDARD_ALERT_ACTIONS,
			"adhkar", self._layout, self._sound_staging, self._audio, AlertEventType.DAILY_WIRD, self._register, "wird")

	def _build_recurring(self,panel,grid,value)->None:
		interval=_spin(panel,grid,N_("Recurring Dhikr interval, minutes:"),value.interval_minutes,5,1440);interval.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"interval_minutes",interval.GetValue()),e.Skip()))
		self._register("recurring.interval", interval)
		self._dhikr_choice=_choice(panel,grid,N_("Dhikr to configure:"),RECURRING_DHIKR_ORDER,DHIKR_LABELS,RECURRING_DHIKR_ORDER[0]);self._dhikr_host=wx.BoxSizer(wx.VERTICAL);grid.Add((1,1));grid.Add(self._dhikr_host,flag=wx.EXPAND);self._dhikr_panel=None
		self._register("recurring.selector", self._dhikr_choice)
		self._dhikr_choice.Bind(wx.EVT_CHOICE,self._on_dhikr);self._render_dhikr(panel,value)

	def _on_dhikr(self,event:wx.CommandEvent)->None:
		self._render_dhikr(self._dhikr_choice.GetParent(),self._draft.settings.adhkar.recurring);self._dhikr_choice.SetFocus();event.Skip()

	def _render_dhikr(self,parent,value)->None:
		if self._dhikr_panel is not None:self._dhikr_host.Detach(self._dhikr_panel);self._dhikr_panel.Destroy()
		identity=RECURRING_DHIKR_ORDER[self._dhikr_choice.GetSelection()];item=value.items[identity];panel,grid=_panel(parent);self._dhikr_panel=panel;self._dhikr_host.Add(panel,flag=wx.EXPAND)
		enabled=wx.CheckBox(panel,label=_("Enable selected Dhikr"));enabled.SetValue(item.enabled);grid.Add((1,1));grid.Add(enabled);enabled.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(item,"enabled",enabled.GetValue()),e.Skip()))
		self._register("recurring.item.enabled", enabled)
		AlertOutputEditor(panel, grid, N_("Selected Dhikr action:"), item.alert, RECURRING_ACTIONS,
			"adhkar", self._layout, self._sound_staging, self._audio, AlertEventType.RECURRING_DHIKR, self._register, "recurring.item", _(DHIKR_LABELS[identity]))
		self._layout()

	def _candidate_from_controls(self):
		candidate = deepcopy(self._draft.settings)
		candidate.location = self.location_controls.pending
		candidate.general.all_automatic_alerts_enabled = self.all_alerts.GetValue()
		candidate.general.quiet_hours.enabled = self.quiet_enabled.GetValue()
		for value, attribute, path in (
			(self.quiet_start.GetValue(), "start", "general.quietHours.start"),
			(self.quiet_end.GetValue(), "end", "general.quietHours.end"),
		):
			try:
				parsed = _parse_clock(value)
			except (TypeError, ValueError) as error:
				raise SettingsValidationError(
					"quiet-hours time is not HH:MM",
					path=path,
					code="invalidTime",
				) from error
			setattr(candidate.general.quiet_hours, attribute, parsed)
		candidate.general.quiet_hours.apply_to_prayer_alerts = self.apply_prayer.GetValue()
		return candidate

	def isValid(self) -> bool:
		if self._sound_staging.has_pending_work:
			wx.MessageBox(
				_("Wait for the sound file selection to finish, then try again."),
				_("Settings not applied"),
				wx.OK | wx.ICON_WARNING,
				self,
			)
			return False
		try:
			candidate = self._candidate_from_controls()
			self._settings.validate(candidate)
		except SettingsValidationError as error:
			self._show_validation_error(error)
			self._validated_candidate = None
			return False
		self._validated_candidate = candidate
		return True

	def _show_validation_error(self, error: SettingsValidationError) -> None:
		message = {
			"iqamaBeforeDelay": _("The Iqama reminder must be earlier than the Iqama time."),
			"outOfRange": _("This value is outside the allowed range."),
			"invalidChoice": _("Choose an allowed option."),
			"invalidTime": _("Enter a valid time in 24-hour HH:MM format."),
			"invalidTimezone": _("Choose a valid IANA time zone."),
			"invalidLocation": _("Check the location details."),
			"invalidSound": _("Choose a valid Awqati sound file."),
		}.get(error.code, _("Check this setting and try again."))
		wx.MessageBox(message, _("Settings not applied"), wx.OK | wx.ICON_ERROR, self)
		self._focus_validation_path(error.path)

	def _focus_validation_path(self, path: str) -> None:
		target = focus_target_for_path(path)
		if target.section is not None and target.section is not self._section:
			self.section_choice.SetSelection(SECTION_ORDER.index(target.section))
			self._section = target.section
			self._render_section()
		if target.prayer_event is not None:
			self._prayer_event_choice.SetSelection(PRAYER_EVENT_ORDER.index(target.prayer_event))
			self._render_prayer_event(self._prayer_event_choice.GetParent())
		if target.clock_type is not None:
			self._clock_choice.SetSelection(tuple(ClockType).index(target.clock_type))
			self._render_clock_type(self._clock_choice.GetParent())
		if target.calendar_id is not None:
			self._calendar_choice.SetSelection(CALENDAR_EDIT_ORDER.index(target.calendar_id))
			self._render_calendar(self._calendar_choice.GetParent())
		if target.adhkar_function is not None:
			value = {
				"morning": self._draft.settings.adhkar.morning,
				"evening": self._draft.settings.adhkar.evening,
				"friday": self._draft.settings.adhkar.friday_hour,
				"wird": self._draft.settings.adhkar.daily_wird,
				"recurring": self._draft.settings.adhkar.recurring,
			}.get(target.adhkar_function)
			if value is not None and not value.enabled:
				self._controls[f"{target.adhkar_function}.enabled"].SetFocus()
				return
		if target.recurring_item is not None:
			self._dhikr_choice.SetSelection(RECURRING_DHIKR_ORDER.index(target.recurring_item))
			self._render_dhikr(self._dhikr_choice.GetParent(), self._draft.settings.adhkar.recurring)
		control = self._controls.get(target.control_key, self.section_choice)
		control.SetFocus()

	def onSave(self)->None:
		candidate = self._validated_candidate
		if candidate is None:
			candidate = self._candidate_from_controls()
			self._settings.validate(candidate)
		draft_settings = self._draft.settings
		draft_settings.location = candidate.location
		draft_settings.general = deepcopy(candidate.general)
		commit = None
		try:
			commit = self._sound_staging.begin_commit(collect_sound_reference_values(candidate))
			self._settings.apply(self._draft)
		except Exception as error:
			if commit is not None:
				self._sound_staging.rollback(commit)
			wx.MessageBox(
				_("Awqati could not save the settings. Your previous applied settings were preserved."),
				_("Settings not applied"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			raise ValueError("Awqati settings save failed") from error
		self._sound_staging.complete(commit, collect_sound_reference_values(candidate))
		self._validated_candidate = None

	def onDiscard(self)->None:
		self._audio.close()
		self._sound_staging.discard()
		self._draft.discard()
