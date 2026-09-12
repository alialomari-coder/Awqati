"""Timezone provider backed only by TZif files bundled with Awqati."""

from __future__ import annotations

from datetime import tzinfo
import hashlib
import json
from pathlib import Path
import re

from .tzif_timezone import TzifTimezone

try:
	from zoneinfo import ZoneInfo as _ZoneInfo
except ImportError:  # NVDA may ship a trimmed Python runtime.
	_ZoneInfo = None


_KEY_PART = re.compile(r"[A-Za-z0-9._+-]+")


class TimezoneDataError(RuntimeError):
	"""Bundled timezone metadata or TZif data is missing or corrupt."""


class UnknownTimezoneError(ValueError):
	"""An IANA key is invalid or is not included in the bundled data."""


class BundledTimezoneProvider:
	"""Resolve IANA zones lazily without reading the host TZPATH."""

	def __init__(self, data_root: Path | None = None) -> None:
		self._data_root = data_root or Path(__file__).resolve().parent.parent / "data" / "timezones"
		self._metadata: dict[str, object] | None = None
		self._zones: dict[str, str] | None = None
		self._cache: dict[str, tzinfo] = {}

	@property
	def tz_data_version(self) -> str:
		return str(self._load_metadata()["tzDataVersion"])

	def get_timezone(self, timezone_id: str) -> tzinfo:
		key = self._validate_key(timezone_id)
		if key in self._cache:
			return self._cache[key]
		self._load_metadata()
		assert self._zones is not None
		expected_hash = self._zones.get(key)
		if expected_hash is None:
			raise UnknownTimezoneError(f"Timezone is not present in bundled data: {key}")
		path = self._data_root / "zoneinfo" / Path(*key.split("/"))
		try:
			data = path.read_bytes()
			if hashlib.sha256(data).hexdigest() != expected_hash:
				raise ValueError("checksum mismatch")
			if _ZoneInfo is None:
				zone = TzifTimezone.from_bytes(data, key)
			else:
				with path.open("rb") as stream:
					zone = _ZoneInfo.from_file(stream, key=key)
		except (OSError, ValueError) as error:
			raise TimezoneDataError(f"Cannot load bundled timezone {key}: {error}") from error
		self._cache[key] = zone
		return zone

	@staticmethod
	def _validate_key(timezone_id: str) -> str:
		key = timezone_id.strip()
		parts = key.split("/")
		if not key or any(part in {"", ".", ".."} or _KEY_PART.fullmatch(part) is None for part in parts):
			raise UnknownTimezoneError("timezone_id must be a safe IANA key")
		return key

	def _load_metadata(self) -> dict[str, object]:
		if self._metadata is not None:
			return self._metadata
		path = self._data_root / "metadata.json"
		try:
			metadata = json.loads(path.read_text(encoding="utf-8"))
			if metadata["schemaVersion"] != 1 or not metadata["tzDataVersion"]:
				raise ValueError("unsupported or empty metadata version")
			zones = metadata["zones"]
			if not isinstance(zones, dict) or metadata["zoneCount"] != len(zones):
				raise ValueError("zone index is invalid")
		except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
			raise TimezoneDataError(f"Cannot read timezone metadata: {error}") from error
		self._metadata = metadata
		self._zones = zones
		return metadata
