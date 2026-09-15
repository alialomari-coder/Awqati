"""Lazy, validated reader for Awqati's generated per-country location data."""

from __future__ import annotations

from collections import OrderedDict
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import unicodedata
from typing import Any

from ..application import CountryInfo, LocationMatch
from ..domain import Coordinates, Location


_COUNTRY_CODE = re.compile(r"[A-Z]{2}")
_SPATIAL_MAGIC = b"AWQSPAT1"
_SPATIAL_SCHEMA_VERSION = 1
_SPATIAL_HEADER = struct.Struct(">8sHI")
_SPATIAL_ENTRY = struct.Struct(">dd2sIBI")


class LocationDataError(RuntimeError):
	"""The bundled location data is missing, corrupt, or structurally invalid."""


class InvalidCountryCodeError(ValueError):
	"""A country code is not a two-letter ISO-style code."""


def normalize_location_text(value: str) -> str:
	"""Normalize searchable text without transliteration or guessed spelling."""
	value = unicodedata.normalize("NFKC", value).replace("\u0640", "")
	value = "".join(
		character
		for character in unicodedata.normalize("NFD", value.casefold())
		if unicodedata.category(character) != "Mn"
	)
	return " ".join(value.split())


def _match_strength(candidate: str, query: str) -> int | None:
	if candidate == query:
		return 0
	if candidate.startswith(query):
		return 1
	if any(word.startswith(query) for word in candidate.split()):
		return 2
	if query in candidate:
		return 3
	return None


class BundledLocationRepository:
	"""Load the metadata index lazily and cache only a few requested countries."""

	def __init__(self, data_root: Path | None = None, *, max_cached_countries: int = 4) -> None:
		if max_cached_countries < 1:
			raise ValueError("max_cached_countries must be at least 1")
		self._data_root = data_root or Path(__file__).resolve().parent.parent / "data" / "locations"
		self._max_cached_countries = max_cached_countries
		self._metadata: dict[str, Any] | None = None
		self._country_entries: dict[str, dict[str, Any]] | None = None
		self._cache: OrderedDict[str, tuple[dict[str, Any], ...]] = OrderedDict()
		self._spatial_data: bytes | None = None

	@property
	def loaded_country_codes(self) -> tuple[str, ...]:
		"""Expose bounded cache state for diagnostics and lazy-loading tests."""
		return tuple(self._cache)

	@property
	def spatial_index_loaded(self) -> bool:
		"""Report whether an explicit nearest-location request loaded the small index."""
		return self._spatial_data is not None

	@property
	def location_data_version(self) -> str:
		return str(self._load_metadata()["locationDataVersion"])

	def countries(self) -> tuple[CountryInfo, ...]:
		metadata = self._load_metadata()
		return tuple(
			CountryInfo(entry["code"], entry["name"], entry["cityCount"])
			for entry in metadata["countries"]
		)

	def search(self, country_code: str, query: str, limit: int = 20) -> tuple[LocationMatch, ...]:
		code = self._validate_country_code(country_code)
		if limit < 1:
			raise ValueError("limit must be at least 1")
		normalized_query = normalize_location_text(query)
		if not normalized_query:
			return ()
		matches: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
		for record in self._load_country(code):
			strengths = (
				strength
				for name in self._search_names(record)
				if (strength := _match_strength(name, normalized_query)) is not None
			)
			strength = min(strengths, default=None)
			if strength is not None:
				matches.append(((strength, record["r"], -record["p"], int(record["i"])), record))
		matches.sort(key=lambda item: item[0])
		return tuple(self._to_match(code, record) for _, record in matches[:limit])

	def browse(self, country_code: str, limit: int = 40) -> tuple[LocationMatch, ...]:
		"""A bounded initial list ranked by administrative importance and population."""
		from heapq import nsmallest
		code = self._validate_country_code(country_code)
		if limit < 1:
			raise ValueError("limit must be at least 1")
		records = nsmallest(limit, self._load_country(code),
			key=lambda record: (record["r"], -record["p"], int(record["i"])))
		return tuple(self._to_match(code, record) for record in records)

	def get(self, country_code: str, location_id: str) -> LocationMatch | None:
		code = self._validate_country_code(country_code)
		identifier = str(location_id)
		for record in self._load_country(code):
			if record["i"] == identifier:
				return self._to_match(code, record)
		return None

	def nearest(self, latitude: float, longitude: float) -> LocationMatch:
		"""Return the deterministic great-circle nearest bundled location."""
		coordinates = Coordinates(float(latitude), float(longitude))
		data = self._load_spatial_index()
		best_key: tuple[float, int, int, int, str] | None = None
		best_identity: tuple[str, str] | None = None
		for offset in range(_SPATIAL_HEADER.size, len(data), _SPATIAL_ENTRY.size):
			candidate_latitude, candidate_longitude, raw_code, identifier, rank, population = _SPATIAL_ENTRY.unpack_from(
				data, offset
			)
			code = raw_code.decode("ascii")
			distance = self._central_angle(
				coordinates.latitude,
				coordinates.longitude,
				candidate_latitude,
				candidate_longitude,
			)
			key = (distance, rank, -population, identifier, code)
			if best_key is None or key < best_key:
				best_key = key
				best_identity = (code, str(identifier))
		if best_identity is None:
			raise LocationDataError("Spatial index contains no locations")
		match = self.get(*best_identity)
		if match is None:
			raise LocationDataError(f"Spatial index points to missing location: {best_identity}")
		return match

	@staticmethod
	def _validate_country_code(country_code: str) -> str:
		code = country_code.strip().upper()
		if _COUNTRY_CODE.fullmatch(code) is None:
			raise InvalidCountryCodeError("country_code must contain exactly two ASCII letters")
		return code

	def _load_metadata(self) -> dict[str, Any]:
		if self._metadata is not None:
			return self._metadata
		path = self._data_root / "metadata.json"
		try:
			metadata = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, UnicodeError, json.JSONDecodeError) as error:
			raise LocationDataError(f"Cannot read location metadata: {error}") from error
		try:
			if metadata["schemaVersion"] != 2 or not metadata["locationDataVersion"]:
				raise ValueError("unsupported or empty metadata version")
			countries = metadata["countries"]
			if metadata["countryCount"] != len(countries):
				raise ValueError("country count does not match the index")
			entries = {entry["code"]: entry for entry in countries}
			if len(entries) != len(countries) or any(_COUNTRY_CODE.fullmatch(code) is None for code in entries):
				raise ValueError("country index contains invalid or duplicate codes")
		except (KeyError, TypeError, ValueError) as error:
			raise LocationDataError(f"Invalid location metadata: {error}") from error
		self._metadata = metadata
		self._country_entries = entries
		return metadata

	def _load_spatial_index(self) -> bytes:
		if self._spatial_data is not None:
			return self._spatial_data
		metadata = self._load_metadata()
		try:
			entry = metadata["spatialIndex"]
			if entry["schemaVersion"] != _SPATIAL_SCHEMA_VERSION or entry["cityCount"] != metadata["cityCount"]:
				raise ValueError("spatial index metadata does not match")
			path = self._data_root / entry["file"]
			compressed = path.read_bytes()
			if hashlib.sha256(compressed).hexdigest() != entry["sha256"]:
				raise ValueError("checksum mismatch")
			data = gzip.decompress(compressed)
			if len(data) != entry["uncompressedBytes"]:
				raise ValueError("uncompressed size mismatch")
			magic, schema_version, count = _SPATIAL_HEADER.unpack_from(data)
			if magic != _SPATIAL_MAGIC or schema_version != _SPATIAL_SCHEMA_VERSION or count != entry["cityCount"]:
				raise ValueError("spatial index header does not match")
			if len(data) != _SPATIAL_HEADER.size + count * _SPATIAL_ENTRY.size:
				raise ValueError("spatial index entry count does not match")
		except (KeyError, OSError, TypeError, UnicodeError, ValueError, gzip.BadGzipFile, struct.error) as error:
			raise LocationDataError(f"Cannot read spatial index: {error}") from error
		self._spatial_data = data
		return data

	@staticmethod
	def _central_angle(latitude1: float, longitude1: float, latitude2: float, longitude2: float) -> float:
		lat1, lat2 = math.radians(latitude1), math.radians(latitude2)
		dlat = lat2 - lat1
		dlon = math.radians(longitude2 - longitude1)
		value = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
		return 2.0 * math.asin(min(1.0, math.sqrt(value)))

	def _load_country(self, code: str) -> tuple[dict[str, Any], ...]:
		if code in self._cache:
			self._cache.move_to_end(code)
			return self._cache[code]
		self._load_metadata()
		assert self._country_entries is not None
		entry = self._country_entries.get(code)
		if entry is None:
			raise InvalidCountryCodeError(f"Country is not present in bundled data: {code}")
		path = self._data_root / "countries" / f"{code}.json.gz"
		try:
			compressed = path.read_bytes()
			if hashlib.sha256(compressed).hexdigest() != entry["sha256"]:
				raise ValueError("checksum mismatch")
			payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
		except (OSError, UnicodeError, ValueError, json.JSONDecodeError, gzip.BadGzipFile) as error:
			raise LocationDataError(f"Cannot read country data for {code}: {error}") from error
		try:
			if payload["schemaVersion"] != 1 or payload["countryCode"] != code:
				raise ValueError("country header does not match")
			cities = tuple(payload["cities"])
			if len(cities) != entry["cityCount"]:
				raise ValueError("city count does not match metadata")
			for record in cities:
				self._validate_record(record)
		except (KeyError, TypeError, ValueError) as error:
			raise LocationDataError(f"Invalid country data for {code}: {error}") from error
		self._cache[code] = cities
		self._cache.move_to_end(code)
		while len(self._cache) > self._max_cached_countries:
			self._cache.popitem(last=False)
		return cities

	@staticmethod
	def _validate_record(record: dict[str, Any]) -> None:
		required = ("i", "n", "x", "e", "a", "lat", "lon", "tz", "a1", "a2", "p", "f", "r")
		if not isinstance(record, dict) or any(key not in record for key in required):
			raise ValueError("city record is missing required fields")
		Location(record["i"], record["n"], float(record["lat"]), float(record["lon"]), record["tz"])
		if not isinstance(record["e"], list) or not isinstance(record["a"], list):
			raise ValueError("alternate names must be lists")
		if not isinstance(record["p"], int) or record["p"] < 0 or not isinstance(record["r"], int):
			raise ValueError("population and rank must be valid integers")

	@staticmethod
	def _search_names(record: dict[str, Any]) -> tuple[str, ...]:
		values = (record["n"], record["x"], *record["e"], *record["a"])
		return tuple(dict.fromkeys(normalize_location_text(value) for value in values if value))

	def _to_match(self, code: str, record: dict[str, Any]) -> LocationMatch:
		assert self._country_entries is not None
		location = Location(record["i"], record["n"], record["lat"], record["lon"], record["tz"])
		return LocationMatch(
			location=location,
			country_code=code,
			country_name=self._country_entries[code]["name"],
			admin1_name=record["a1"],
			admin2_name=record["a2"],
			population=record["p"],
			feature_code=record["f"],
			arabic_names=tuple(record["a"]),
			english_names=tuple(record["e"]),
			arabic_admin1_names=tuple(record.get("a1ar", ())),
			arabic_admin2_names=tuple(record.get("a2ar", ())),
		)
