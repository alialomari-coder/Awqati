"""Task 3.3 dynamic settings sections for the single Awqati NVDA panel."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading
from typing import Callable, Sequence

import globalVars
import languageHandler
import wx
import wx.adv
from gui.settingsDialogs import SettingsPanel

from ..domain import (
	AlertAction, AlertOutputSettings, AnnouncementStyle, AsrMethod, CalculationMethod,
	CalendarId, ClockType, DateFormat, DayPeriod, EveningReference, FridayReference,
	HighLatitudeRule, HourSystem, MorningReference, PrayerEventName, SoundReference,
	SettingsValidationError, TimeRepresentation,
)
from ..infrastructure import BundledCalculationMethodRepository
from .settings_sections import (
	CALENDAR_EDIT_ORDER, PRIMARY_CALENDAR_ORDER, PRAYER_ACTIONS, PRAYER_EVENT_ORDER,
	RECURRING_ACTIONS, RECURRING_DHIKR_ORDER, SECTION_ORDER, STANDARD_ALERT_ACTIONS,
	SettingsSection, action_uses_sound, focus_target_for_path, hijri_adjustment_visible,
	is_rtl_language,
)
from .sound_staging import (
	SoundPreparationCancelled, SoundStagingSession, collect_sound_reference_values,
)
from .ui import LocationControls, _context_or_raise, _parse_clock, _


SECTION_LABELS = {
	SettingsSection.PRAYER: "Prayer times",
	SettingsSection.CLOCK: "Clock",
	SettingsSection.DATE: "Date",
	SettingsSection.ADHKAR: "Dhikr alerts",
}
PRAYER_LABELS = {
	PrayerEventName.FAJR: "Fajr", PrayerEventName.SUNRISE: "Sunrise",
	PrayerEventName.DHUHR: "Dhuhr", PrayerEventName.ASR: "Asr",
	PrayerEventName.MAGHRIB: "Maghrib", PrayerEventName.ISHA: "Isha",
	PrayerEventName.MIDNIGHT: "Midnight", PrayerEventName.LAST_THIRD: "Start of the last third",
}
ACTION_LABELS = {
	AlertAction.SILENT: "Silent", AlertAction.SPEECH: "Speech only",
	AlertAction.SOUND: "Sound file only", AlertAction.SOUND_AND_SPEECH: "Sound file and speech",
}
STYLE_LABELS = {
	AnnouncementStyle.DOUBLE: "Double", AnnouncementStyle.FULL: "Full",
	AnnouncementStyle.MODERATE: "Moderate", AnnouncementStyle.SHORT: "Short",
}
DATE_FORMAT_LABELS = {
	DateFormat.DOUBLE: "Double", DateFormat.FULL: "Full",
	DateFormat.MODERATE: "Moderate", DateFormat.SHORT: "Short",
}
CALENDAR_LABELS = {
	CalendarId.HIJRI_UMM_AL_QURA: "Lunar Hijri", CalendarId.GREGORIAN: "Gregorian",
	CalendarId.SAUDI_SOLAR_HIJRI: "Saudi Solar Hijri",
	CalendarId.AFGHAN_SOLAR_HIJRI: "Afghan Solar Hijri",
	CalendarId.PERSIAN_SOLAR_HIJRI: "Persian Solar Hijri",
}
DHIKR_LABELS = {
	identity: label for identity, label in zip(RECURRING_DHIKR_ORDER, (
		"Subhan Allah", "Alhamdu lillah", "La ilaha illa Allah", "Allahu Akbar",
		"La hawla wa la quwwata illa billah", "Astaghfiru Allah",
		"Blessings upon the Prophet", "Remember Allah and He will remember you",
		"Do not forget the remembrance of Allah",
	))
}


def _translated(values: Sequence, labels: dict) -> list[str]:
	return [_(labels[value]) for value in values]


def _choice(parent: wx.Window, sizer: wx.Sizer, label: str, values: Sequence,
		labels: dict, selected, name: str | None = None) -> wx.Choice:
	sizer.Add(wx.StaticText(parent, label=_(label)), flag=wx.ALIGN_CENTER_VERTICAL)
	control = wx.Choice(parent, choices=_translated(values, labels), name=_(name or label.rstrip(":")))
	control.SetSelection(values.index(selected))
	sizer.Add(control, flag=wx.EXPAND)
	return control


def _spin(parent: wx.Window, sizer: wx.Sizer, label: str, value: int,
		minimum: int, maximum: int) -> wx.SpinCtrl:
	sizer.Add(wx.StaticText(parent, label=_(label)), flag=wx.ALIGN_CENTER_VERTICAL)
	control = wx.SpinCtrl(parent, min=minimum, max=maximum, initial=value, name=_(label.rstrip(":")))
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
			on_layout: Callable[[], None], sound_staging: SoundStagingSession,
			register: Callable[[str, wx.Window], None], control_prefix: str) -> None:
		self.parent, self.sizer, self.output = parent, sizer, output
		self.actions, self.category, self.on_layout = tuple(actions), category, on_layout
		self.sound_staging = sound_staging
		self.register, self.control_prefix = register, control_prefix
		self._busy = False
		self.sizer.Add(wx.StaticText(parent, label=_(label)), flag=wx.ALIGN_CENTER_VERTICAL)
		self.action = wx.Choice(parent, choices=_translated(self.actions, ACTION_LABELS), name=_(label.rstrip(":")))
		self.action.SetSelection(self.actions.index(output.action))
		self.sizer.Add(self.action, flag=wx.EXPAND)
		self.register(f"{control_prefix}.action", self.action)
		self.action.Bind(wx.EVT_CHOICE, self._on_action)
		self.sound_panel: wx.Panel | None = None
		self._sound: wx.adv.Sound | None = None
		self._render_sound()

	def _on_action(self, event: wx.CommandEvent) -> None:
		self.output.action = self.actions[self.action.GetSelection()]
		self._render_sound()
		self.action.SetFocus()
		event.Skip()

	def _render_sound(self) -> None:
		if self.sound_panel is not None:
			self.sizer.Detach(self.sound_panel)
			self.sound_panel.Destroy()
			self.sound_panel = None
		if not action_uses_sound(self.output.action):
			self.register(f"{self.control_prefix}.sound", self.action)
			self.on_layout()
			return
		self.sizer.Add((1, 1))
		self.sound_panel = wx.Panel(self.parent)
		row = wx.BoxSizer(wx.HORIZONTAL)
		self.choose = wx.Button(self.sound_panel, label=_("Choose sound file"))
		self.preview = wx.Button(self.sound_panel, label=_("Preview sound"))
		self.remove = wx.Button(self.sound_panel, label=_("Remove custom sound"))
		for button in (self.choose, self.preview, self.remove):
			row.Add(button, flag=wx.RIGHT, border=8)
		self.register(f"{self.control_prefix}.sound", self.choose)
		self.sound_panel.SetSizer(row)
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
		available = self._selected_path()
		available = available is not None and available.is_file()
		self.preview.Enable(available)
		self.remove.Enable(self.output.sound is not None)
		self.choose.Enable(not self._busy)
		self.choose.SetLabel(_("Selecting sound file...") if self._busy else _("Choose sound file"))

	def _on_choose(self, event: wx.CommandEvent) -> None:
		if self._busy:
			event.Skip()
			return
		target_dir = self._root / "sounds" / self.category
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
			wx.MessageBox(_("The sound file could not be selected. {details}").format(details=error),
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
				wx.MessageBox(_("The sound file could not be selected. {details}").format(details=error),
					_("Sound file error"), wx.OK | wx.ICON_ERROR, self.parent)
			if self.sound_panel is not None:
				self._update_buttons()
				self.choose.SetFocus()
		except RuntimeError:
			# The dynamic panel or settings dialog may have closed while the worker ran.
			pass

	def _on_preview(self, event: wx.CommandEvent) -> None:
		path = self._selected_path()
		if path is not None and path.is_file():
			self._sound = wx.adv.Sound(str(path))
			if not self._sound.IsOk() or not self._sound.Play(wx.adv.SOUND_ASYNC):
				wx.MessageBox(_("The selected sound could not be played."), _("Sound preview"),
					wx.OK | wx.ICON_WARNING, self.parent)
		self.preview.SetFocus()
		event.Skip()

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
		self._sound_staging = SoundStagingSession(Path(globalVars.appArgs.configPath) / "awqati")
		current = self._draft.settings
		self.location_controls = LocationControls(self, settingsSizer, context.location_setup, current.location)
		self._register("location", self.location_controls.custom_button)
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
		for label, control in (("Quiet hours start, HH:MM:", self.quiet_start), ("Quiet hours end, HH:MM:", self.quiet_end)):
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
		grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8); grid.AddGrowableCol(1, 1); outer.Add(grid, flag=wx.EXPAND)
		method_values = tuple(CalculationMethod)
		method_labels = {CalculationMethod.AUTO: "Automatic by country"}
		provider = BundledCalculationMethodRepository()
		for method in method_values[1:]: method_labels[method] = provider.get_method(method).name
		method = _choice(panel, grid, "Prayer calculation method:", method_values, method_labels, settings.calculation_method)
		self._register("prayer.calculationMethod", method)
		method.Bind(wx.EVT_CHOICE, lambda e: (setattr(settings, "calculation_method", method_values[method.GetSelection()]), self._update_effective_method(provider), e.Skip()))
		self._effective_method = wx.StaticText(panel, label="")
		grid.Add(wx.StaticText(panel, label=_("Effective automatic method:")), flag=wx.ALIGN_CENTER_VERTICAL)
		grid.Add(self._effective_method, flag=wx.EXPAND)
		self._prayer_method_choice = method; self._update_effective_method(provider)
		asr_values = (AsrMethod.STANDARD, AsrMethod.HANAFI); asr_labels = {AsrMethod.STANDARD: "Standard (Shafi, Maliki, Hanbali)", AsrMethod.HANAFI: "Hanafi"}
		asr = _choice(panel, grid, "Asr calculation:", asr_values, asr_labels, settings.asr_method)
		self._register("prayer.asrMethod", asr)
		asr.Bind(wx.EVT_CHOICE, lambda e: (setattr(settings, "asr_method", asr_values[asr.GetSelection()]), e.Skip()))
		high_values = tuple(HighLatitudeRule); high_labels = {HighLatitudeRule.AUTO:"Automatic", HighLatitudeRule.ANGLE_BASED:"Angle based", HighLatitudeRule.ONE_SEVENTH:"One seventh", HighLatitudeRule.NIGHT_MIDDLE:"Middle of the night", HighLatitudeRule.NEAREST_LATITUDE:"Nearest latitude"}
		high = _choice(panel, grid, "High-latitude handling:", high_values, high_labels, settings.high_latitude_rule)
		self._register("prayer.highLatitudeRule", high)
		high.Bind(wx.EVT_CHOICE, lambda e: (setattr(settings, "high_latitude_rule", high_values[high.GetSelection()]), e.Skip()))
		current = _spin(panel, grid, "Keep prayer current after Iqama, minutes:", settings.current_prayer_after_iqama_minutes, 0, 180)
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
		self._effective_method.SetLabel(provider.get_method(effective).name)

	def _on_prayer_event(self, event: wx.CommandEvent) -> None:
		parent = self._prayer_event_choice.GetParent(); self._render_prayer_event(parent)
		self._prayer_event_choice.SetFocus(); event.Skip()

	def _render_prayer_event(self, parent: wx.Window) -> None:
		if self._prayer_event_panel is not None:
			self._prayer_event_host.Detach(self._prayer_event_panel); self._prayer_event_panel.Destroy()
		name = PRAYER_EVENT_ORDER[self._prayer_event_choice.GetSelection()]
		event_settings = self._draft.settings.prayer.events[name]
		panel, grid = _panel(parent); self._prayer_event_panel = panel; self._prayer_event_host.Add(panel, flag=wx.EXPAND)
		correction = _spin(panel, grid, "Time correction, minutes:", self._draft.settings.prayer.corrections_minutes[name], -30, 30)
		self._register("prayer.correction", correction)
		correction.Bind(wx.EVT_SPINCTRL, lambda e: (self._draft.settings.prayer.corrections_minutes.__setitem__(name, correction.GetValue()), e.Skip()))
		pre = _spin(panel, grid, "Pre-alert minutes:", event_settings.pre_alert_minutes, 0, 180)
		self._register("prayer.preMinutes", pre)
		pre.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings, "pre_alert_minutes", pre.GetValue()), e.Skip()))
		AlertOutputEditor(panel, grid, "Pre-alert action:", event_settings.pre_alert, PRAYER_ACTIONS,
			"adhan", self._layout, self._sound_staging, self._register, "prayer.pre")
		AlertOutputEditor(panel, grid, "At-time alert action:", event_settings.at_time_alert, PRAYER_ACTIONS,
			"adhan", self._layout, self._sound_staging, self._register, "prayer.atTime")
		if event_settings.iqama is not None:
			delay = _spin(panel, grid, "Minutes between Adhan and Iqama:", event_settings.iqama.delay_minutes, 0, 180)
			before = _spin(panel, grid, "Alert before Iqama, minutes:", event_settings.iqama.alert_before_minutes, 0, 180)
			self._register("prayer.iqamaDelay", delay)
			self._register("prayer.iqamaBefore", before)
			delay.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings.iqama, "delay_minutes", delay.GetValue()), e.Skip()))
			before.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings.iqama, "alert_before_minutes", before.GetValue()), e.Skip()))
			AlertOutputEditor(panel, grid, "Iqama alert action:", event_settings.iqama.alert, PRAYER_ACTIONS,
				"adhan", self._layout, self._sound_staging, self._register, "prayer.iqama")
		else:
			post = _spin(panel, grid, "Post-alert minutes:", event_settings.post_alert_minutes, 0, 180)
			self._register("prayer.postMinutes", post)
			post.Bind(wx.EVT_SPINCTRL, lambda e: (setattr(event_settings, "post_alert_minutes", post.GetValue()), e.Skip()))
			AlertOutputEditor(panel, grid, "Post-alert action:", event_settings.post_alert, PRAYER_ACTIONS,
				"alerts", self._layout, self._sound_staging, self._register, "prayer.post")
		self._layout()

	def _build_clock(self) -> wx.Panel:
		panel = wx.Panel(self); outer = wx.BoxSizer(wx.VERTICAL); panel.SetSizer(outer); settings = self._draft.settings.clock
		outer.Add(wx.StaticText(panel, label=_("Zawali time is always primary; Ghurubi time is always additional.")), flag=wx.BOTTOM, border=8)
		outer.Add(wx.StaticText(panel, label=_("Choose clock settings:")))
		clock_labels = {ClockType.ZAWALI:"Zawali", ClockType.GHURUBI:"Ghurubi"}
		self._clock_choice = wx.Choice(panel, choices=_translated(tuple(ClockType), clock_labels), name=_("Choose clock settings")); self._clock_choice.SetSelection(0); outer.Add(self._clock_choice, flag=wx.EXPAND)
		self._register("clock.selector", self._clock_choice)
		self._clock_host = wx.BoxSizer(wx.VERTICAL); outer.Add(self._clock_host, flag=wx.TOP | wx.EXPAND, border=8); self._clock_panel = None
		self._clock_choice.Bind(wx.EVT_CHOICE, self._on_clock_type); self._render_clock_type(panel)
		enabled = wx.CheckBox(panel, label=_("Enable automatic clock alerts")); enabled.SetValue(settings.automatic_alert_enabled); outer.Add(enabled, flag=wx.TOP, border=8)
		self._register("clock.enabled", enabled)
		enabled.Bind(wx.EVT_CHECKBOX, lambda e: (setattr(settings, "automatic_alert_enabled", enabled.GetValue()), e.Skip()))
		for attr, label in (("on_hour","On the hour"),("on_quarter","Quarter past"),("on_half","Half past"),("on_three_quarters","Three quarters past")):
			box = wx.CheckBox(panel, label=_(label)); box.SetValue(getattr(settings.intervals, attr)); outer.Add(box)
			self._register(f"clock.interval.{attr}", box)
			box.Bind(wx.EVT_CHECKBOX, lambda e, a=attr, b=box: (setattr(settings.intervals, a, b.GetValue()), e.Skip()))
		alert_panel, grid = _panel(panel); outer.Add(alert_panel, flag=wx.TOP | wx.EXPAND, border=8)
		AlertOutputEditor(alert_panel, grid, "Clock alert action:", settings.alert, STANDARD_ALERT_ACTIONS,
			"alerts", self._layout, self._sound_staging, self._register, "clock.alert")
		return panel

	def _on_clock_type(self, event: wx.CommandEvent) -> None:
		self._render_clock_type(self._clock_choice.GetParent()); self._clock_choice.SetFocus(); event.Skip()

	def _render_clock_type(self, parent: wx.Window) -> None:
		if self._clock_panel is not None: self._clock_host.Detach(self._clock_panel); self._clock_panel.Destroy()
		identity = tuple(ClockType)[self._clock_choice.GetSelection()]; value = self._draft.settings.clock.presentations[identity]
		panel, grid = _panel(parent); self._clock_panel = panel; self._clock_host.Add(panel, flag=wx.EXPAND)
		styles = tuple(AnnouncementStyle); style = _choice(panel, grid, "Speech format:", styles, STYLE_LABELS, value.style)
		self._register("clock.style", style)
		style.Bind(wx.EVT_CHOICE, lambda e: (setattr(value, "style", styles[style.GetSelection()]), e.Skip()))
		hours = tuple(HourSystem); hour_labels={HourSystem.TWELVE:"12-hour",HourSystem.TWENTY_FOUR:"24-hour"}; hour = _choice(panel, grid, "Hour system:", hours, hour_labels, value.hour_system)
		self._register("clock.hourSystem", hour)
		hour.Bind(wx.EVT_CHOICE, lambda e: (setattr(value, "hour_system", hours[hour.GetSelection()]), e.Skip()))
		reps=tuple(TimeRepresentation); rep_labels={TimeRepresentation.NUMERIC:"Numbers",TimeRepresentation.WORDS:"Words"}; rep=_choice(panel,grid,"Speech representation:",reps,rep_labels,value.representation)
		self._register("clock.representation", rep)
		rep.Bind(wx.EVT_CHOICE, lambda e:(setattr(value,"representation",reps[rep.GetSelection()]),e.Skip()))
		for attr,label in (("speak_seconds","Speak seconds"),("speak_zero_minute","Speak zero minutes")):
			box=wx.CheckBox(panel,label=_(label));box.SetValue(getattr(value,attr));grid.Add((1,1));grid.Add(box)
			self._register("clock.speakSeconds" if attr == "speak_seconds" else "clock.speakZeroMinute", box)
			box.Bind(wx.EVT_CHECKBOX,lambda e,a=attr,b=box:(setattr(value,a,b.GetValue()),e.Skip()))
		self._layout()

	def _build_date(self) -> wx.Panel:
		panel=wx.Panel(self);outer=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(outer);settings=self._draft.settings.calendar
		outer.Add(wx.StaticText(panel,label=_("Choose calendar to configure:")))
		self._calendar_choice=wx.Choice(panel,choices=_translated(CALENDAR_EDIT_ORDER,CALENDAR_LABELS),name=_("Choose calendar to configure"));self._calendar_choice.SetSelection(0);outer.Add(self._calendar_choice,flag=wx.EXPAND)
		self._register("calendar.selector", self._calendar_choice)
		grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=8);grid.AddGrowableCol(1,1);outer.Add(grid,flag=wx.TOP|wx.EXPAND,border=8)
		primary=_choice(panel,grid,"Primary calendar:",PRIMARY_CALENDAR_ORDER,CALENDAR_LABELS,settings.primary_calendar)
		self._register("calendar.primary", primary)
		primary.Bind(wx.EVT_CHOICE,lambda e:(setattr(settings,"primary_calendar",PRIMARY_CALENDAR_ORDER[primary.GetSelection()]),e.Skip()))
		self._calendar_host=wx.BoxSizer(wx.VERTICAL);outer.Add(self._calendar_host,flag=wx.TOP|wx.EXPAND,border=8);self._calendar_panel=None
		self._calendar_choice.Bind(wx.EVT_CHOICE,self._on_calendar);self._render_calendar(panel)
		include=wx.CheckBox(panel,label=_("Include Arabian calendar information in astronomical daily information"));include.SetValue(settings.include_arabian_calendar_in_daily_info);outer.Add(include,flag=wx.TOP,border=8)
		self._register("calendar.includeArabian", include)
		include.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(settings,"include_arabian_calendar_in_daily_info",include.GetValue()),e.Skip()))
		return panel

	def _on_calendar(self,event:wx.CommandEvent)->None:
		self._render_calendar(self._calendar_choice.GetParent());self._calendar_choice.SetFocus();event.Skip()

	def _render_calendar(self,parent:wx.Window)->None:
		if self._calendar_panel is not None:self._calendar_host.Detach(self._calendar_panel);self._calendar_panel.Destroy()
		identity=CALENDAR_EDIT_ORDER[self._calendar_choice.GetSelection()];settings=self._draft.settings.calendar;panel,grid=_panel(parent);self._calendar_panel=panel;self._calendar_host.Add(panel,flag=wx.EXPAND)
		formats=tuple(DateFormat);fmt=_choice(panel,grid,"Date format:",formats,DATE_FORMAT_LABELS,settings.formats[identity]);self._date_format_choice=fmt
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

	def _build_adhkar(self)->wx.Panel:
		panel=wx.Panel(self);outer=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(outer);settings=self._draft.settings.adhkar
		enabled=wx.CheckBox(panel,label=_("Enable Dhikr alerts"));enabled.SetValue(settings.alerts_enabled);outer.Add(enabled,flag=wx.BOTTOM,border=8)
		self._register("adhkar.enabled", enabled)
		enabled.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(settings,"alerts_enabled",enabled.GetValue()),e.Skip()))
		self._adhkar_hosts={};self._adhkar_panels={}
		functions=(("morning","Enable morning Dhikr",settings.morning),("evening","Enable evening Dhikr",settings.evening),("friday","Enable Friday hour reminder",settings.friday_hour),("wird","Enable daily Wird",settings.daily_wird),("recurring","Enable recurring Dhikr reminder",settings.recurring))
		for key,label,value in functions:
			box=wx.CheckBox(panel,label=_(label));box.SetValue(value.enabled);outer.Add(box,flag=wx.TOP,border=8)
			self._register(f"{key}.enabled", box)
			host=wx.BoxSizer(wx.VERTICAL);outer.Add(host,flag=wx.EXPAND);self._adhkar_hosts[key]=host;self._adhkar_panels[key]=None
			box.Bind(wx.EVT_CHECKBOX,lambda e,k=key,v=value,b=box:(setattr(v,"enabled",b.GetValue()),self._render_adhkar_child(panel,k),b.SetFocus(),e.Skip()))
			self._render_adhkar_child(panel,key)
		return panel

	def _render_adhkar_child(self,parent:wx.Window,key:str)->None:
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
		if key=="morning":values=tuple(MorningReference);labels={MorningReference.AFTER_FAJR:"After Fajr",MorningReference.BEFORE_SUNRISE:"Before sunrise",MorningReference.AFTER_SUNRISE:"After sunrise"}
		elif key=="evening":values=tuple(EveningReference);labels={EveningReference.AFTER_ASR:"After Asr",EveningReference.BEFORE_MAGHRIB:"Before Maghrib",EveningReference.AFTER_MAGHRIB:"After Maghrib"}
		else:values=tuple(FridayReference);labels={FridayReference.AFTER_ASR:"After Asr",FridayReference.BEFORE_MAGHRIB:"Before Maghrib"}
		reference=_choice(panel,grid,"Reference time:",values,labels,value.reference);reference.Bind(wx.EVT_CHOICE,lambda e:(setattr(value,"reference",values[reference.GetSelection()]),e.Skip()))
		minutes=_spin(panel,grid,"Offset in minutes:",value.minutes,0,180);minutes.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"minutes",minutes.GetValue()),e.Skip()))
		self._register(f"{key}.reference", reference)
		self._register(f"{key}.minutes", minutes)
		AlertOutputEditor(panel, grid, "Alert action:", value.alert, STANDARD_ALERT_ACTIONS,
			"adhkar", self._layout, self._sound_staging, self._register, key)

	def _build_wird(self,panel,grid,value)->None:
		grid.Add(wx.StaticText(panel,label=_("Reminder text:")),flag=wx.ALIGN_CENTER_VERTICAL);text=wx.TextCtrl(panel,value=value.text,name=_("Daily Wird reminder text"));grid.Add(text,flag=wx.EXPAND);text.Bind(wx.EVT_TEXT,lambda e:(setattr(value,"text",text.GetValue()),e.Skip()))
		hour=_spin(panel,grid,"Hour (1 to 12):",value.hour,1,12);minute=_spin(panel,grid,"Minute (0 to 59):",value.minute,0,59)
		self._register("wird.text", text)
		self._register("wird.hour", hour)
		self._register("wird.minute", minute)
		hour.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"hour",hour.GetValue()),e.Skip()));minute.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"minute",minute.GetValue()),e.Skip()))
		periods=tuple(DayPeriod);labels={DayPeriod.AM:"AM",DayPeriod.PM:"PM"};period=_choice(panel,grid,"Period:",periods,labels,value.period);period.Bind(wx.EVT_CHOICE,lambda e:(setattr(value,"period",periods[period.GetSelection()]),e.Skip()))
		self._register("wird.period", period)
		AlertOutputEditor(panel, grid, "Alert action:", value.alert, STANDARD_ALERT_ACTIONS,
			"adhkar", self._layout, self._sound_staging, self._register, "wird")

	def _build_recurring(self,panel,grid,value)->None:
		interval=_spin(panel,grid,"Interval in minutes:",value.interval_minutes,5,1440);interval.Bind(wx.EVT_SPINCTRL,lambda e:(setattr(value,"interval_minutes",interval.GetValue()),e.Skip()))
		self._register("recurring.interval", interval)
		self._dhikr_choice=_choice(panel,grid,"Dhikr to configure:",RECURRING_DHIKR_ORDER,DHIKR_LABELS,RECURRING_DHIKR_ORDER[0]);self._dhikr_host=wx.BoxSizer(wx.VERTICAL);grid.Add((1,1));grid.Add(self._dhikr_host,flag=wx.EXPAND);self._dhikr_panel=None
		self._register("recurring.selector", self._dhikr_choice)
		self._dhikr_choice.Bind(wx.EVT_CHOICE,self._on_dhikr);self._render_dhikr(panel,value)

	def _on_dhikr(self,event:wx.CommandEvent)->None:
		self._render_dhikr(self._dhikr_choice.GetParent(),self._draft.settings.adhkar.recurring);self._dhikr_choice.SetFocus();event.Skip()

	def _render_dhikr(self,parent,value)->None:
		if self._dhikr_panel is not None:self._dhikr_host.Detach(self._dhikr_panel);self._dhikr_panel.Destroy()
		identity=RECURRING_DHIKR_ORDER[self._dhikr_choice.GetSelection()];item=value.items[identity];panel,grid=_panel(parent);self._dhikr_panel=panel;self._dhikr_host.Add(panel,flag=wx.EXPAND)
		enabled=wx.CheckBox(panel,label=_("Enable selected Dhikr"));enabled.SetValue(item.enabled);grid.Add((1,1));grid.Add(enabled);enabled.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(item,"enabled",enabled.GetValue()),e.Skip()))
		self._register("recurring.item.enabled", enabled)
		AlertOutputEditor(panel, grid, "Selected Dhikr action:", item.alert, RECURRING_ACTIONS,
			"adhkar", self._layout, self._sound_staging, self._register, "recurring.item")
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
		self._sound_staging.complete(commit)
		self._validated_candidate = None

	def onDiscard(self)->None:
		self._sound_staging.discard()
		self._draft.discard()
