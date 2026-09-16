"""Manual Awqati commands composed from existing application services."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

from ..application import (
	ArabicArabianCalendarFormatter, ArabicDailyInfoFormatter, ArabicQiblaFormatter,
	DailyInfoService, EnglishDateFormatter, EnglishQiblaFormatter, QiblaService,
	EventPreAlertSettings, IqamaRule, IqamaSettings, PrayerStatePriority, PrayerStateService,
)
from ..application.calendar_formatters import ArabicDateFormatter
from ..application.settings_preview import SettingsPreviewService
from ..domain import CalendarId, ClockType, PrayerCalculationRequest, PrayerCorrections, PrayerEventName, PrayerName, complete_prayer_times


class CommandContent:
	"""Read-only command content; manual requests never enter the alert queue."""

	def __init__(self, settings, now, zones, prayers, clock, calendars,
			daily_info: DailyInfoService, arabian_calendar) -> None:
		self.settings, self.now, self.zones, self.prayers = settings, now, zones, prayers
		self.clock, self.calendars = clock, calendars
		self.daily_info, self.arabian_calendar = daily_info, arabian_calendar
		self.preview = SettingsPreviewService(clock, calendars, now)

	def _settings(self):
		return self.settings.runtime_settings

	def _location(self):
		stored = self._settings().location
		if stored is None:
			raise ValueError("No location has been assigned.")
		return stored.location

	def clock_text(self, identity: ClockType, language: str) -> str:
		return self.preview.clock_text(self._settings(), identity, language)

	def date_text(self, identity: CalendarId, language: str) -> str:
		return self.preview.date_text(self._settings(), identity, language)

	def primary_date(self, language: str) -> str:
		return self.date_text(self._settings().calendar.primary_calendar, language)

	def location_text(self, translate) -> str:
		return translate("Assigned location: {name}; time zone: {timezone}").format(
			name=self._location().name, timezone=self._location().timezone_id)

	def qibla_text(self, language: str) -> str:
		formatter = ArabicQiblaFormatter() if language == "ar" else EnglishQiblaFormatter()
		return formatter.format(QiblaService().calculate(self._location()))

	def arabian_short(self) -> str:
		return ArabicArabianCalendarFormatter().format_short(self.arabian_calendar.read(self._location()))

	def arabian_detailed(self) -> str:
		return ArabicArabianCalendarFormatter().format_detailed(self.arabian_calendar.read(self._location()))

	def daily_info_text(self) -> str:
		settings = self._settings()
		reading = self.daily_info.read(self._location(),
			include_arabian_calendar=settings.calendar.include_arabian_calendar_in_daily_info)
		return ArabicDailyInfoFormatter().format(reading)

	def scientific_info_text(self) -> str:
		return ArabicDailyInfoFormatter().format_scientific(
			self.daily_info.read(self._location(), include_arabian_calendar=False).scientific)

	def _request(self, day):
		settings, location = self._settings(), self._location()
		config = settings.prayer
		return PrayerCalculationRequest(day, location.latitude, location.longitude, location.timezone_id,
			config.calculation_method, config.asr_method, config.high_latitude_rule,
			country_code=settings.location.country_code, corrections=PrayerCorrections(**{
				name.value: config.corrections_minutes[PrayerEventName(name.value)] for name in PrayerName}))

	def daily_prayer_times(self, translate) -> str:
		location = self._location()
		zone = self.zones.get_timezone(location.timezone_id)
		day = self.now.now().value.astimezone(zone).date()
		today = self.prayers.calculate(self._request(day))
		tomorrow = self.prayers.calculate(self._request(day + timedelta(days=1)))
		complete = complete_prayer_times(today, tomorrow.fajr)
		labels = {
			"fajr": "Fajr", "sunrise": "Sunrise", "dhuhr": "Dhuhr", "asr": "Asr",
			"maghrib": "Maghrib", "isha": "Isha", "midnight": "Midnight",
			"last_third_start": "Start of the last third",
		}
		lines = [translate("Today's prayer times:")]
		for key in labels:
			value = getattr(complete, key)
			lines.append(translate("{name}: {time}").format(name=translate(labels[key]), time=value.strftime("%H:%M")))
		return "\n".join(lines)

	def _timeline(self):
		location = self._location()
		zone = self.zones.get_timezone(location.timezone_id)
		day = self.now.now().value.astimezone(zone).date()
		calculated = {offset: self.prayers.calculate(self._request(day + timedelta(days=offset)))
			for offset in (-1, 0, 1, 2)}
		events = []
		for offset in (-1, 0, 1):
			events.extend(complete_prayer_times(calculated[offset], calculated[offset + 1].fajr).events)
		return tuple(events)

	def _state(self):
		settings = self._settings().prayer
		pre = EventPreAlertSettings({name: settings.events[name].pre_alert_minutes for name in PrayerEventName})
		rules = {}
		for name in PrayerEventName:
			value = settings.events[name].iqama
			if value is not None:
				rules[name] = IqamaRule(value.delay_minutes, value.alert_before_minutes)
		return PrayerStateService(self.now).snapshot(self._timeline(), pre_alerts=pre,
			iqama=IqamaSettings(rules),
			current_prayer_duration_minutes=settings.current_prayer_after_iqama_minutes)

	@staticmethod
	def _event_name(event, translate):
		return translate({
			PrayerEventName.FAJR: "Fajr", PrayerEventName.SUNRISE: "Sunrise",
			PrayerEventName.DHUHR: "Dhuhr", PrayerEventName.ASR: "Asr",
			PrayerEventName.MAGHRIB: "Maghrib", PrayerEventName.ISHA: "Isha",
			PrayerEventName.MIDNIGHT: "Midnight", PrayerEventName.LAST_THIRD: "Start of the last third",
		}[event.name])

	def current_details(self, translate) -> str:
		state = self._state()
		now = state.as_of.value
		if state.priority is PrayerStatePriority.WAITING:
			event = state.waiting_window.event
			minutes = max(0, round((event.occurs_at - now.astimezone(event.occurs_at.tzinfo)).total_seconds() / 60))
			return translate("Waiting for {name}; {minutes} minutes remain.").format(
				name=self._event_name(event, translate), minutes=minutes)
		if state.priority is PrayerStatePriority.CURRENT_PRAYER:
			event = state.current_prayer.event
			minutes = max(0, round((now.astimezone(event.occurs_at.tzinfo) - event.occurs_at).total_seconds() / 60))
			return translate("The current prayer is {name}; it began {minutes} minutes ago.").format(
				name=self._event_name(event, translate), minutes=minutes)
		event = state.next_event
		minutes = max(0, round((event.occurs_at - now.astimezone(event.occurs_at.tzinfo)).total_seconds() / 60))
		kind = "The next prayer is {name} at {time}; in {minutes} minutes." if event.kind.value == "prayer" else "The next time is {name} at {time}; in {minutes} minutes."
		return translate(kind).format(name=self._event_name(event, translate), time=event.occurs_at.strftime("%H:%M"), minutes=minutes)

	def previous_details(self, translate) -> str:
		state = self._state()
		event = state.previous_event
		minutes = max(0, round((state.as_of.value.astimezone(event.occurs_at.tzinfo) - event.occurs_at).total_seconds() / 60))
		kind = "The previous prayer was {name} at {time}; {minutes} minutes ago." if event.kind.value == "prayer" else "The previous time was {name} at {time}; {minutes} minutes ago."
		return translate(kind).format(name=self._event_name(event, translate), time=event.occurs_at.strftime("%H:%M"), minutes=minutes)

	def toggle(self, path: str) -> bool:
		draft = self.settings.open_draft()
		target = draft.settings
		parts = path.split(".")
		for part in parts[:-1]:
			target = getattr(target, part)
		name = parts[-1]
		value = not getattr(target, name)
		setattr(target, name, value)
		self.settings.apply(draft)
		return value

	def toggle_primary_calendar(self):
		draft = self.settings.open_draft()
		current = draft.settings.calendar.primary_calendar
		draft.settings.calendar.primary_calendar = (
			CalendarId.GREGORIAN if current is CalendarId.HIJRI_UMM_AL_QURA else CalendarId.HIJRI_UMM_AL_QURA)
		self.settings.apply(draft)
		return draft.settings.calendar.primary_calendar

	def alert_status(self, translate) -> str:
		s = self._settings()
		state = lambda value: translate("enabled") if value else translate("disabled")
		return translate(
			"Awqati alerts: all automatic alerts {all}; prayer alerts {prayer}; clock alert {clock}; "
			"dhikr alerts {dhikr}; recurring dhikr {recurring}; quiet hours {quiet}."
		).format(all=state(s.general.all_automatic_alerts_enabled), prayer=state(s.prayer.alerts_enabled),
			clock=state(s.clock.automatic_alert_enabled), dhikr=state(s.adhkar.alerts_enabled),
			recurring=state(s.adhkar.recurring.enabled), quiet=state(s.general.quiet_hours.enabled))
