"""Validated lazy reader for Awqati's bundled Arabian calendar data."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

from ..domain import (
	ArabianCalendarReading, ArabianMansion, ArabianNaw, ArabianOverlapPeriod,
	ArabianSaying, ArabianSeason, ArabianStartEvent, ArabianTalaa, MonthDay,
	SuhailCycleType,
)


ARABIAN_CALENDAR_DATA_VERSION = "2026.09.13-r1"
ARABIAN_CALENDAR_SCHEMA_VERSION = 1


class ArabianCalendarDataError(RuntimeError):
	"""Bundled Arabian calendar data is missing, corrupt, or incompatible."""


class BundledArabianCalendarRepository:
	def __init__(self, data_directory: Path | None = None) -> None:
		self._data_directory = data_directory or (
			Path(__file__).resolve().parents[1] / "data" / "arabian_calendar"
		)
		self._bundle: dict[str, Any] | None = None
		self._load_count = 0

	@property
	def arabian_calendar_data_version(self) -> str:
		self._ensure_loaded()
		return ARABIAN_CALENDAR_DATA_VERSION

	@property
	def load_count(self) -> int:
		return self._load_count

	def read(self, local_date: date) -> ArabianCalendarReading:
		bundle = self._ensure_loaded()
		anchor_year = local_date.year if (local_date.month, local_date.day) >= (8, 24) else local_date.year - 1
		anchor = date(anchor_year, 8, 24)
		cycle_type = SuhailCycleType.LEAP if calendar.isleap(anchor_year + 1) else SuhailCycleType.COMMON
		index = bundle["indexes"][cycle_type.value]
		key = local_date.strftime("%m-%d")
		try:
			item = index["daysByDate"][key]
		except KeyError as error:
			raise ArabianCalendarDataError(f"daily index has no record for {key}") from error
		talaa = bundle["talaa"][item["talaaId"]]
		return ArabianCalendarReading(
			local_date=local_date, cycle_anchor=anchor, cycle_type=cycle_type,
			cycle_length=item["cycleLength"], suhail_day=item["suhailDay"],
			days_remaining=item["daysRemainingInSuhailYear"], talaa_day=item["talaaDay"],
			talaa_length=item["talaaLength"], season_day=item["seasonDay"],
			season_length=item["seasonLength"], folk_subdivision=item.get("folkSubdivision"),
			talaa=talaa, mansion=bundle["mansions"].get(talaa.id),
			naw=bundle["naws"].get(talaa.id), season=bundle["seasons"][item["seasonId"]],
			overlapping_periods=tuple(bundle["overlaps"][value] for value in item["overlapPeriodIds"]),
			short_saying=bundle["sayings"].get(item.get("shortSayingId")),
			start_events=tuple(bundle["events"][value] for value in item["startEventIds"]),
			data_version=ARABIAN_CALENDAR_DATA_VERSION,
		)

	def _ensure_loaded(self) -> dict[str, Any]:
		if self._bundle is None:
			self._bundle = self._load()
			self._load_count += 1
		return self._bundle

	def _load(self) -> dict[str, Any]:
		metadata = self._read_json("metadata.json")
		_validate_versioned_object(metadata, "metadata.json")
		files = metadata.get("files")
		if not isinstance(files, dict) or set(files) != {
			"arabian_calendar.json", "arabian_calendar_days_common.json",
			"arabian_calendar_days_leap.json",
		}:
			raise ArabianCalendarDataError("metadata.json has an invalid runtime file set")
		for name, expected in files.items():
			path = self._data_directory / name
			try:
				payload = path.read_bytes()
			except OSError as error:
				raise ArabianCalendarDataError(f"required runtime file is unavailable: {name}") from error
			if len(payload) != expected.get("sizeBytes") or hashlib.sha256(payload).hexdigest() != expected.get("sha256"):
				raise ArabianCalendarDataError(f"runtime integrity check failed: {name}")
		rich = self._read_json("arabian_calendar.json")
		common = self._read_json("arabian_calendar_days_common.json")
		leap = self._read_json("arabian_calendar_days_leap.json")
		_validate_versioned_object(rich, "arabian_calendar.json")
		_validate_index(common, SuhailCycleType.COMMON)
		_validate_index(leap, SuhailCycleType.LEAP)
		return _build_bundle(rich, common, leap)

	def _read_json(self, name: str) -> dict[str, Any]:
		path = self._data_directory / name
		try:
			value = json.loads(path.read_bytes().decode("utf-8"))
		except OSError as error:
			raise ArabianCalendarDataError(f"required runtime file is unavailable: {name}") from error
		except (UnicodeDecodeError, json.JSONDecodeError) as error:
			raise ArabianCalendarDataError(f"invalid JSON in runtime file: {name}") from error
		if not isinstance(value, dict):
			raise ArabianCalendarDataError(f"runtime file must contain an object: {name}")
		return value


def _validate_versioned_object(value: dict[str, Any], name: str) -> None:
	if value.get("schemaVersion") != ARABIAN_CALENDAR_SCHEMA_VERSION:
		raise ArabianCalendarDataError(f"unsupported schemaVersion in {name}")
	if value.get("arabianCalendarDataVersion") != ARABIAN_CALENDAR_DATA_VERSION:
		raise ArabianCalendarDataError(f"unsupported arabianCalendarDataVersion in {name}")


def _validate_index(value: dict[str, Any], cycle_type: SuhailCycleType) -> None:
	name = f"{cycle_type.value} daily index"
	_validate_versioned_object(value, name)
	expected_length = 366 if cycle_type is SuhailCycleType.LEAP else 365
	if value.get("cycleType") != cycle_type.value or value.get("cycleLength") != expected_length:
		raise ArabianCalendarDataError(f"invalid cycle metadata in {name}")
	ordered = value.get("orderedDateKeys")
	days = value.get("daysByDate")
	if not isinstance(ordered, list) or not isinstance(days, dict):
		raise ArabianCalendarDataError(f"invalid records in {name}")
	if len(ordered) != expected_length or len(days) != expected_length or len(set(ordered)) != expected_length:
		raise ArabianCalendarDataError(f"missing or duplicate records in {name}")
	anchor = date(2023 if cycle_type is SuhailCycleType.LEAP else 2024, 8, 24)
	expected_keys = [(anchor + timedelta(days=offset)).strftime("%m-%d") for offset in range(expected_length)]
	if ordered != expected_keys or set(days) != set(expected_keys):
		raise ArabianCalendarDataError(f"daily index has gaps or is out of order: {name}")
	for position, key in enumerate(ordered, 1):
		item = days[key]
		if not isinstance(item, dict):
			raise ArabianCalendarDataError(f"invalid daily record: {name} {key}")
		if (
			item.get("suhailDay") != position or item.get("cycleLength") != expected_length
			or item.get("daysRemainingInSuhailYear") != expected_length - position
			or key != f"{item.get('month'):02d}-{item.get('day'):02d}"
		):
			raise ArabianCalendarDataError(f"inconsistent daily record: {name} {key}")


def _month_day(value: Any, context: str) -> MonthDay:
	if not isinstance(value, dict) or not isinstance(value.get("month"), int) or not isinstance(value.get("day"), int):
		raise ArabianCalendarDataError(f"invalid month/day in {context}")
	try:
		date(2000, value["month"], value["day"])
	except ValueError as error:
		raise ArabianCalendarDataError(f"invalid month/day in {context}") from error
	return MonthDay(value["month"], value["day"])


def _build_bundle(rich: dict[str, Any], common: dict[str, Any], leap: dict[str, Any]) -> dict[str, Any]:
	try:
		season_items, talaa_items = rich["seasons"], rich["talaa"]
		overlap_items, event_items = rich.get("overlappingPeriods", []), rich.get("startEvents", {})
	except KeyError as error:
		raise ArabianCalendarDataError(f"missing rich-data field: {error.args[0]}") from error
	if not isinstance(season_items, list) or not isinstance(talaa_items, list):
		raise ArabianCalendarDataError("rich entity collections must be arrays")
	seasons: dict[str, ArabianSeason] = {}
	for item in season_items:
		try:
			entity = ArabianSeason(
				item["id"], item["name"], _month_day(item["start"], "season"),
				_month_day(item["end"], "season"), item["length"]["common"], item["length"]["leap"],
				tuple(item.get("notes", ())), tuple(item.get("talaaIds", ())), tuple(item.get("sourceRefs", ())),
			)
		except (KeyError, TypeError) as error:
			raise ArabianCalendarDataError("invalid season entity") from error
		if entity.id in seasons:
			raise ArabianCalendarDataError(f"duplicate season id: {entity.id}")
		seasons[entity.id] = entity
	overlaps: dict[str, ArabianOverlapPeriod] = {}
	for item in overlap_items:
		try:
			entity = ArabianOverlapPeriod(
				item["id"], item["name"], _month_day(item["start"], "overlap"),
				_month_day(item["end"], "overlap"), item["description"],
				tuple(item.get("talaaIds", ())), tuple(item.get("sourceRefs", ())),
			)
		except (KeyError, TypeError) as error:
			raise ArabianCalendarDataError("invalid overlap entity") from error
		if entity.id in overlaps:
			raise ArabianCalendarDataError(f"duplicate overlap id: {entity.id}")
		overlaps[entity.id] = entity
	talaa: dict[str, ArabianTalaa] = {}
	sayings: dict[str, ArabianSaying] = {}
	mansions: dict[str, ArabianMansion] = {}
	naws: dict[str, ArabianNaw] = {}
	for item in talaa_items:
		try:
			entity_sayings = tuple(ArabianSaying(value["id"], value["text"]) for value in item["sayings"])
			entity = ArabianTalaa(
				item["id"], item["order"], item["name"], tuple(item.get("aliases", ())),
				_month_day(item["start"], "talaa"), _month_day(item["end"], "talaa"),
				item["length"]["common"], item["length"]["leap"], item["seasonId"],
				item.get("folkSubdivision"), tuple(item.get("heritageNotes", ())), entity_sayings,
				tuple(item.get("overlapPeriodIds", ())), tuple(item.get("sourceRefs", ())),
			)
		except (KeyError, TypeError) as error:
			raise ArabianCalendarDataError("invalid talaa entity") from error
		if entity.id in talaa or any(value.id in sayings for value in entity_sayings):
			raise ArabianCalendarDataError(f"duplicate talaa or saying id: {entity.id}")
		talaa[entity.id] = entity
		sayings.update((value.id, value) for value in entity_sayings)
		if item.get("nameOrigin") or item.get("mansionDescription"):
			mansions[entity.id] = ArabianMansion(entity.name, item.get("nameOrigin"), item.get("mansionDescription"))
		if item.get("nawClassical"):
			naws[entity.id] = ArabianNaw(item["nawClassical"])
	if len(talaa) != 28 or sorted(value.order for value in talaa.values()) != list(range(1, 29)):
		raise ArabianCalendarDataError("rich data must define exactly 28 ordered talaa")
	if not isinstance(event_items, dict):
		raise ArabianCalendarDataError("startEvents must be an object")
	try:
		events = {key: ArabianStartEvent(key, value["type"], value["text"]) for key, value in event_items.items()}
	except (KeyError, TypeError) as error:
		raise ArabianCalendarDataError("invalid start event") from error
	for event_id, item in event_items.items():
		if item.get("seasonId") is not None and item["seasonId"] not in seasons:
			raise ArabianCalendarDataError(f"unknown season reference in start event: {event_id}")
		if item.get("overlapPeriodId") is not None and item["overlapPeriodId"] not in overlaps:
			raise ArabianCalendarDataError(f"unknown overlap reference in start event: {event_id}")
	_validate_references(rich, common, leap, talaa, seasons, overlaps, sayings, events)
	return {"talaa": talaa, "mansions": mansions, "naws": naws, "seasons": seasons,
		"overlaps": overlaps, "sayings": sayings, "events": events,
		"indexes": {"common": common, "leap": leap}}


def _validate_references(
	rich: dict[str, Any], common: dict[str, Any], leap: dict[str, Any],
	talaa: dict[str, ArabianTalaa], seasons: dict[str, ArabianSeason],
	overlaps: dict[str, ArabianOverlapPeriod], sayings: dict[str, ArabianSaying],
	events: dict[str, ArabianStartEvent],
) -> None:
	source_ids = set(rich.get("sources", {}))
	for value in (*talaa.values(), *seasons.values(), *overlaps.values()):
		if not set(value.source_refs) <= source_ids:
			raise ArabianCalendarDataError(f"unknown source reference in {value.id}")
	for value in talaa.values():
		if value.season_id not in seasons or not set(value.overlap_period_ids) <= set(overlaps):
			raise ArabianCalendarDataError(f"unknown entity reference in talaa {value.id}")
	for value in seasons.values():
		if not set(value.talaa_ids) <= set(talaa):
			raise ArabianCalendarDataError(f"unknown talaa reference in season {value.id}")
	for value in overlaps.values():
		if not set(value.talaa_ids) <= set(talaa):
			raise ArabianCalendarDataError(f"unknown talaa reference in overlap {value.id}")
	for index in (common, leap):
		seen_sayings: dict[str, set[str]] = {}
		for key in index["orderedDateKeys"]:
			item = index["daysByDate"][key]
			if item.get("talaaId") not in talaa or item.get("seasonId") not in seasons:
				raise ArabianCalendarDataError(f"unknown daily entity reference: {key}")
			if not set(item.get("overlapPeriodIds", ())) <= set(overlaps):
				raise ArabianCalendarDataError(f"unknown daily overlap reference: {key}")
			if not set(item.get("startEventIds", ())) <= set(events):
				raise ArabianCalendarDataError(f"unknown daily start-event reference: {key}")
			saying_id = item.get("shortSayingId")
			if saying_id is not None:
				if saying_id not in sayings:
					raise ArabianCalendarDataError(f"unknown daily saying reference: {key}")
				used = seen_sayings.setdefault(item["talaaId"], set())
				if saying_id in used:
					raise ArabianCalendarDataError(f"repeated daily saying reference: {key}")
				used.add(saying_id)
