"""Atomic JSON persistence for the versioned Awqati settings schema."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable

from ..domain import (
	AdhkarSettings,
	AlertAction,
	AlertOutputSettings,
	AnnouncementStyle,
	AsrMethod,
	AwqatiSettings,
	CalendarId,
	CalendarSettings,
	CalculationMethod,
	ClockChimeIntervals,
	ClockPresentationSettings,
	ClockSettings,
	ClockTime,
	ClockType,
	DailyWirdSettings,
	DateFormat,
	DayPeriod,
	EveningReference,
	FridayReference,
	GeneralSettings,
	HighLatitudeRule,
	HourSystem,
	IqamaAlertSettings,
	Location,
	LocationKind,
	MorningReference,
	PrayerEventAlertSettings,
	PrayerEventName,
	PrayerSettings,
	QuietHoursSettings,
	RecurringDhikrId,
	RecurringDhikrItemSettings,
	RecurringDhikrSettings,
	SETTINGS_SCHEMA_VERSION,
	SoundReference,
	StoredLocation,
	TimeRepresentation,
	TimedDhikrSettings,
	default_settings,
	validate_settings,
)


class SettingsRepositoryError(RuntimeError):
	"""Base failure for loading or saving settings."""


class UnsupportedSettingsSchemaError(SettingsRepositoryError):
	"""The file uses a schema newer than this Awqati build."""


class InvalidSettingsDataError(SettingsRepositoryError):
	"""The settings file is malformed, incomplete, or fails validation."""


class SettingsWriteError(SettingsRepositoryError):
	"""A validated settings graph could not be committed atomically."""


Migration = Callable[[dict[str, Any]], dict[str, Any]]


class SettingsMigrationRegistry:
	"""Explicit N-to-N+1 migration chain; schema 1 intentionally has none."""

	def __init__(self, current_version: int = SETTINGS_SCHEMA_VERSION) -> None:
		self.current_version = current_version
		self._migrations: dict[int, Migration] = {}

	def register(self, from_version: int, migration: Migration) -> None:
		if from_version < SETTINGS_SCHEMA_VERSION or from_version >= self.current_version:
			raise ValueError("migrations are only allowed between published supported schemas")
		if from_version in self._migrations:
			raise ValueError("a migration is already registered for this schema")
		self._migrations[from_version] = migration

	def migrate(self, data: dict[str, Any]) -> dict[str, Any]:
		version = data.get("schemaVersion")
		if isinstance(version, bool) or not isinstance(version, int):
			raise InvalidSettingsDataError("schemaVersion is missing or invalid")
		if version > self.current_version:
			raise UnsupportedSettingsSchemaError(
				f"settings schema {version} is newer than supported schema {self.current_version}")
		if version < SETTINGS_SCHEMA_VERSION:
			raise InvalidSettingsDataError("no migration exists from an unpublished legacy schema")
		result = data
		while version < self.current_version:
			try:
				migration = self._migrations[version]
			except KeyError as error:
				raise InvalidSettingsDataError(f"missing migration from settings schema {version}") from error
			result = migration(result)
			version += 1
			if result.get("schemaVersion") != version:
				raise InvalidSettingsDataError("migration did not advance exactly one schema version")
		return result


class JsonSettingsRepository:
	"""Read and atomically replace one injectable JSON settings file."""

	def __init__(self, path: Path, migrations: SettingsMigrationRegistry | None = None) -> None:
		self._path = Path(path)
		self._migrations = migrations or SettingsMigrationRegistry()

	def load(self) -> AwqatiSettings:
		if not self._path.exists():
			return default_settings()
		try:
			raw = json.loads(self._path.read_text(encoding="utf-8"))
		except (OSError, UnicodeError, json.JSONDecodeError) as error:
			raise InvalidSettingsDataError("cannot read the Awqati settings file") from error
		if not isinstance(raw, dict):
			raise InvalidSettingsDataError("the Awqati settings root must be an object")
		try:
			return _decode_settings(self._migrations.migrate(raw))
		except (KeyError, TypeError, ValueError) as error:
			if isinstance(error, SettingsRepositoryError):
				raise
			raise InvalidSettingsDataError("the Awqati settings file is incomplete or invalid") from error

	def save(self, settings: AwqatiSettings) -> None:
		try:
			validate_settings(settings)
			payload = json.dumps(_encode(settings), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
		except (TypeError, ValueError) as error:
			raise InvalidSettingsDataError("refusing to save invalid Awqati settings") from error
		temporary: Path | None = None
		try:
			self._path.parent.mkdir(parents=True, exist_ok=True)
			with tempfile.NamedTemporaryFile(
				mode="w",
				encoding="utf-8",
				newline="\n",
				dir=self._path.parent,
				prefix=f".{self._path.name}.",
				suffix=".tmp",
				delete=False,
			) as stream:
				temporary = Path(stream.name)
				stream.write(payload)
				stream.flush()
				os.fsync(stream.fileno())
			os.replace(temporary, self._path)
		except OSError as error:
			if temporary is not None:
				try:
					temporary.unlink(missing_ok=True)
				except OSError:
					pass
			raise SettingsWriteError("could not atomically save Awqati settings") from error


def _camel(name: str) -> str:
	return re.sub(r"_([a-z])", lambda match: match.group(1).upper(), name)


def _encode(value: Any) -> Any:
	if isinstance(value, Enum):
		return value.value
	if is_dataclass(value):
		return {_camel(item.name): _encode(getattr(value, item.name)) for item in fields(value)}
	if isinstance(value, dict):
		return {_encode(key): _encode(item) for key, item in value.items()}
	if isinstance(value, (str, int, float, bool)) or value is None:
		return value
	raise TypeError(f"unsupported settings value: {type(value).__name__}")


def _object(data: Any, keys: set[str], path: str) -> dict[str, Any]:
	if not isinstance(data, dict) or set(data) != keys:
		raise InvalidSettingsDataError(f"{path} has missing or unknown fields")
	return data


def _enum(kind: type[Enum], value: Any, path: str):
	try:
		return kind(value)
	except (TypeError, ValueError) as error:
		raise InvalidSettingsDataError(f"{path} has an unknown value") from error


def _sound(value: Any, path: str) -> SoundReference | None:
	if value is None:
		return None
	data = _object(value, {"value"}, path)
	return SoundReference(data["value"])


def _output(value: Any, path: str) -> AlertOutputSettings:
	data = _object(value, {"action", "sound"}, path)
	return AlertOutputSettings(
		_enum(AlertAction, data["action"], f"{path}.action"),
		_sound(data["sound"], f"{path}.sound"),
	)


def _clock_time(value: Any, path: str) -> ClockTime:
	data = _object(value, {"hour", "minute"}, path)
	return ClockTime(data["hour"], data["minute"])


def _location(value: Any) -> StoredLocation | None:
	if value is None:
		return None
	data = _object(value, {"kind", "location", "countryCode"}, "location")
	item = _object(data["location"], {"locationId", "name", "latitude", "longitude", "timezoneId"},
		"location.location")
	return StoredLocation(
		_enum(LocationKind, data["kind"], "location.kind"),
		Location(item["locationId"], item["name"], item["latitude"], item["longitude"], item["timezoneId"]),
		data["countryCode"],
	)


def _decode_settings(value: dict[str, Any]) -> AwqatiSettings:
	root = _object(value, {"schemaVersion", "location", "general", "prayer", "clock", "calendar", "adhkar"},
		"settings")
	general_data = _object(root["general"], {"allAutomaticAlertsEnabled", "quietHours"}, "general")
	quiet_data = _object(general_data["quietHours"],
		{"enabled", "start", "end", "applyToPrayerAlerts"}, "general.quietHours")
	general = GeneralSettings(
		general_data["allAutomaticAlertsEnabled"],
		QuietHoursSettings(
			quiet_data["enabled"],
			_clock_time(quiet_data["start"], "general.quietHours.start"),
			_clock_time(quiet_data["end"], "general.quietHours.end"),
			quiet_data["applyToPrayerAlerts"],
		),
	)

	prayer_data = _object(root["prayer"], {
		"alertsEnabled", "calculationMethod", "asrMethod", "highLatitudeRule",
		"correctionsMinutes", "events", "currentPrayerAfterIqamaMinutes",
	}, "prayer")
	corrections_data = _object(prayer_data["correctionsMinutes"],
		{identity.value for identity in PrayerEventName}, "prayer.correctionsMinutes")
	events_data = _object(prayer_data["events"], {identity.value for identity in PrayerEventName}, "prayer.events")
	events: dict[PrayerEventName, PrayerEventAlertSettings] = {}
	for identity in PrayerEventName:
		path = f"prayer.events.{identity.value}"
		event = _object(events_data[identity.value],
			{"preAlertMinutes", "preAlert", "atTimeAlert", "iqama", "postAlertMinutes", "postAlert"}, path)
		iqama = None
		if event["iqama"] is not None:
			iqama_data = _object(event["iqama"], {"delayMinutes", "alertBeforeMinutes", "alert"}, f"{path}.iqama")
			iqama = IqamaAlertSettings(
				iqama_data["delayMinutes"],
				iqama_data["alertBeforeMinutes"],
				_output(iqama_data["alert"], f"{path}.iqama.alert"),
			)
		events[identity] = PrayerEventAlertSettings(
			event["preAlertMinutes"],
			_output(event["preAlert"], f"{path}.preAlert"),
			_output(event["atTimeAlert"], f"{path}.atTimeAlert"),
			iqama,
			event["postAlertMinutes"],
			None if event["postAlert"] is None else _output(event["postAlert"], f"{path}.postAlert"),
		)
	prayer = PrayerSettings(
		prayer_data["alertsEnabled"],
		_enum(CalculationMethod, prayer_data["calculationMethod"], "prayer.calculationMethod"),
		_enum(AsrMethod, prayer_data["asrMethod"], "prayer.asrMethod"),
		_enum(HighLatitudeRule, prayer_data["highLatitudeRule"], "prayer.highLatitudeRule"),
		{identity: corrections_data[identity.value] for identity in PrayerEventName},
		events,
		prayer_data["currentPrayerAfterIqamaMinutes"],
	)

	clock_data = _object(root["clock"], {"automaticAlertEnabled", "presentations", "intervals", "alert"}, "clock")
	presentations_data = _object(clock_data["presentations"], {identity.value for identity in ClockType},
		"clock.presentations")
	presentations = {}
	for identity in ClockType:
		path = f"clock.presentations.{identity.value}"
		item = _object(presentations_data[identity.value],
			{"style", "hourSystem", "representation", "speakSeconds", "speakZeroMinute"}, path)
		presentations[identity] = ClockPresentationSettings(
			_enum(AnnouncementStyle, item["style"], f"{path}.style"),
			_enum(HourSystem, item["hourSystem"], f"{path}.hourSystem"),
			_enum(TimeRepresentation, item["representation"], f"{path}.representation"),
			item["speakSeconds"],
			item["speakZeroMinute"],
		)
	intervals = _object(clock_data["intervals"],
		{"onHour", "onQuarter", "onHalf", "onThreeQuarters"}, "clock.intervals")
	clock = ClockSettings(
		clock_data["automaticAlertEnabled"],
		presentations,
		ClockChimeIntervals(
			intervals["onHour"], intervals["onQuarter"], intervals["onHalf"], intervals["onThreeQuarters"]),
		_output(clock_data["alert"], "clock.alert"),
	)

	calendar_data = _object(root["calendar"],
		{"primaryCalendar", "formats", "hijriAdjustmentDays", "includeArabianCalendarInDailyInfo"}, "calendar")
	formats_data = _object(calendar_data["formats"], {identity.value for identity in CalendarId}, "calendar.formats")
	calendar = CalendarSettings(
		_enum(CalendarId, calendar_data["primaryCalendar"], "calendar.primaryCalendar"),
		{identity: _enum(DateFormat, formats_data[identity.value], f"calendar.formats.{identity.value}")
			for identity in CalendarId},
		calendar_data["hijriAdjustmentDays"],
		calendar_data["includeArabianCalendarInDailyInfo"],
	)

	adhkar_data = _object(root["adhkar"],
		{"alertsEnabled", "morning", "evening", "fridayHour", "dailyWird", "recurring"}, "adhkar")
	def timed(name: str, reference_type: type[Enum]) -> TimedDhikrSettings:
		item = _object(adhkar_data[name], {"enabled", "reference", "minutes", "alert"}, f"adhkar.{name}")
		return TimedDhikrSettings(item["enabled"], _enum(reference_type, item["reference"], f"adhkar.{name}.reference"),
			item["minutes"], _output(item["alert"], f"adhkar.{name}.alert"))
	wird_data = _object(adhkar_data["dailyWird"],
		{"enabled", "text", "hour", "minute", "period", "alert"}, "adhkar.dailyWird")
	recurring_data = _object(adhkar_data["recurring"], {"enabled", "intervalMinutes", "items"}, "adhkar.recurring")
	items_data = _object(recurring_data["items"], {identity.value for identity in RecurringDhikrId},
		"adhkar.recurring.items")
	items = {}
	for identity in RecurringDhikrId:
		path = f"adhkar.recurring.items.{identity.value}"
		item = _object(items_data[identity.value], {"enabled", "alert"}, path)
		items[identity] = RecurringDhikrItemSettings(item["enabled"], _output(item["alert"], f"{path}.alert"))
	adhkar = AdhkarSettings(
		adhkar_data["alertsEnabled"],
		timed("morning", MorningReference),
		timed("evening", EveningReference),
		timed("fridayHour", FridayReference),
		DailyWirdSettings(
			wird_data["enabled"], wird_data["text"], wird_data["hour"], wird_data["minute"],
			_enum(DayPeriod, wird_data["period"], "adhkar.dailyWird.period"),
			_output(wird_data["alert"], "adhkar.dailyWird.alert"),
		),
		RecurringDhikrSettings(recurring_data["enabled"], recurring_data["intervalMinutes"], items),
	)
	settings = AwqatiSettings(root["schemaVersion"], _location(root["location"]), general, prayer, clock, calendar, adhkar)
	validate_settings(settings)
	return settings
