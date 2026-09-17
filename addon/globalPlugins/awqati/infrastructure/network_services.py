"""HTTPS adapters for explicit Awqati network operations."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

from ..application import (
	CancellationToken, DataPackageManifest, DataUpdateError, OnlinePrayerRequest,
	OnlinePrayerVerificationError, OperationCancelled,
)
from ..domain import AsrMethod, CalculationMethod, HighLatitudeRule, PrayerName
from .arabian_calendar_repository import BundledArabianCalendarRepository
from .calculation_method_repository import BundledCalculationMethodRepository
from .location_repository import BundledLocationRepository
from .timezone_provider import BundledTimezoneProvider
from .ummalqura_provider import UmmAlQuraProvider


class HttpsTransport:
	"""Small stdlib-only HTTPS reader with bounded payloads and cancellation checks."""

	MAX_BYTES = 100 * 1024 * 1024

	def read_json(self, url: str, *, timeout: float,
			cancellation: CancellationToken) -> Mapping[str, Any]:
		try:
			value = json.loads(self.read_bytes(url, timeout=timeout, cancellation=cancellation).decode("utf-8"))
		except (UnicodeDecodeError, json.JSONDecodeError) as error:
			raise DataUpdateError("server returned invalid JSON") from error
		if not isinstance(value, dict):
			raise DataUpdateError("server JSON must be an object")
		return value

	def read_bytes(self, url: str, *, timeout: float, cancellation: CancellationToken) -> bytes:
		if not url.startswith("https://"):
			raise DataUpdateError("network URL must use HTTPS")
		request = Request(url, headers={"User-Agent": "Awqati/4 data client", "Accept": "application/json, application/zip"})
		try:
			with urlopen(request, timeout=timeout) as response:
				if response.geturl().lower().startswith("https://") is False:
					raise DataUpdateError("HTTPS request redirected to a non-HTTPS URL")
				parts, size = [], 0
				while True:
					cancellation.raise_if_cancelled()
					block = response.read(64 * 1024)
					if not block:
						break
					size += len(block)
					if size > self.MAX_BYTES:
						raise DataUpdateError("network payload exceeds the safety limit")
					parts.append(block)
		except (DataUpdateError, OperationCancelled):
			raise
		except Exception as error:
			raise DataUpdateError(f"HTTPS request failed: {error}") from error
		return b"".join(parts)


_ALADHAN_METHODS = {
	CalculationMethod.MWL: 3, CalculationMethod.ISNA: 2, CalculationMethod.EGYPT: 5,
	CalculationMethod.MAKKAH: 4, CalculationMethod.KARACHI: 1, CalculationMethod.GULF: 8,
	CalculationMethod.KUWAIT: 9, CalculationMethod.QATAR: 10, CalculationMethod.SINGAPORE: 11,
	CalculationMethod.FRANCE: 12, CalculationMethod.TURKEY: 13, CalculationMethod.RUSSIA: 14,
	CalculationMethod.JAKIM: 17, CalculationMethod.TUNISIA: 18, CalculationMethod.ALGERIA: 19,
	CalculationMethod.KEMENAG: 20, CalculationMethod.MOROCCO: 21, CalculationMethod.PORTUGAL: 22,
	CalculationMethod.JORDAN: 23,
}
_HIGH_LATITUDE = {
	HighLatitudeRule.AUTO: 3, HighLatitudeRule.ANGLE_BASED: 3,
	HighLatitudeRule.ONE_SEVENTH: 2, HighLatitudeRule.NIGHT_MIDDLE: 1,
	HighLatitudeRule.NEAREST_LATITUDE: 3,
}
_TIME = re.compile(r"^(\d{1,2}):(\d{2})")


class AlAdhanPrayerProvider:
	"""AlAdhan Prayer Times API adapter; it returns only the six approved times."""

	ENDPOINT = "https://api.aladhan.com/v1/timings/{date}"

	def fetch(self, request: OnlinePrayerRequest, *, timeout: float,
			cancellation: CancellationToken) -> Mapping[PrayerName, int]:
		if request.calculation_method is CalculationMethod.AUTO:
			raise OnlinePrayerVerificationError("the online request requires the effective calculation method")
		method = _ALADHAN_METHODS.get(request.calculation_method)
		if method is None:
			raise OnlinePrayerVerificationError("AlAdhan has no approved equivalent for the selected method")
		query = urlencode({
			"latitude": format(request.latitude, ".8f"),
			"longitude": format(request.longitude, ".8f"),
			"method": method,
			"school": 1 if request.asr_method is AsrMethod.HANAFI else 0,
			"latitudeAdjustmentMethod": _HIGH_LATITUDE[request.high_latitude_rule],
		})
		url = self.ENDPOINT.format(date=request.local_date.strftime("%d-%m-%Y")) + "?" + query
		try:
			payload = HttpsTransport().read_bytes(url, timeout=timeout, cancellation=cancellation)
			document = json.loads(payload.decode("utf-8"))
			if document.get("code") != 200:
				raise ValueError("provider returned a non-success status")
			timings = document["data"]["timings"]
			result = {}
			for prayer in PrayerName:
				key = prayer.value.capitalize() if prayer is not PrayerName.DHUHR else "Dhuhr"
				match = _TIME.match(timings[key])
				if match is None:
					raise ValueError(f"invalid {key} time")
				hour, minute = int(match.group(1)), int(match.group(2))
				if hour > 23 or minute > 59:
					raise ValueError(f"invalid {key} time")
				result[prayer] = hour * 60 + minute
			return result
		except OnlinePrayerVerificationError:
			raise
		except Exception as error:
			raise OnlinePrayerVerificationError(f"AlAdhan response failed validation: {error}") from error


_PACKAGE_PATHS = {
	"locations": ("locations", "locations"),
	"timezones": ("timezones", "timezones"),
	"ummalqura": ("calendars/ummalqura", "ummalqura"),
	"calculationMethods": ("calculation_methods", "calculationMethods"),
	"arabianCalendar": ("arabian_calendar", "arabianCalendar"),
}


def active_data_path(addon_data_root: Path, user_data_root: Path, data_type: str) -> Path:
	"""Prefer a previously validated user update, otherwise use bundled data."""
	relative, storage = _PACKAGE_PATHS[data_type]
	override = user_data_root / "data" / storage / "current"
	return override if override.is_dir() else addon_data_root / Path(relative)


class AtomicDataPackageInstaller:
	"""Validate a ZIP in staging, then atomically replace the user-data package."""

	MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024

	def __init__(self, user_data_root: Path) -> None:
		self._root = user_data_root / "data"

	def install(self, package: DataPackageManifest, payload: bytes,
			cancellation: CancellationToken) -> None:
		if package.data_type not in _PACKAGE_PATHS:
			raise DataUpdateError(f"unsupported dataType: {package.data_type}")
		self._root.mkdir(parents=True, exist_ok=True)
		parent = self._root / _PACKAGE_PATHS[package.data_type][1]
		parent.mkdir(parents=True, exist_ok=True)
		try:
			with tempfile.TemporaryDirectory(prefix="awqati-update-", dir=parent) as temporary:
				staging = Path(temporary) / "payload"
				staging.mkdir()
				self._extract(payload, staging, cancellation)
				self._validate(package, staging)
				cancellation.raise_if_cancelled()
				target, backup = parent / "current", parent / "previous"
				if backup.exists():
					shutil.rmtree(backup)
				if target.exists():
					target.replace(backup)
				try:
					staging.replace(target)
				except Exception:
					if backup.exists() and not target.exists():
						backup.replace(target)
					raise
		except DataUpdateError:
			raise
		except Exception as error:
			raise DataUpdateError(f"atomic install failed for {package.data_type}: {error}") from error

	def _extract(self, payload: bytes, staging: Path, cancellation: CancellationToken) -> None:
		try:
			with zipfile.ZipFile(BytesIO(payload)) as archive:
				total = 0
				for info in archive.infolist():
					cancellation.raise_if_cancelled()
					path = Path(info.filename)
					if path.is_absolute() or ".." in path.parts or info.is_dir():
						if info.is_dir():
							continue
						raise DataUpdateError("package contains an unsafe path")
					if (info.external_attr >> 16) & 0o170000 == 0o120000:
						raise DataUpdateError("package contains a symbolic link")
					total += info.file_size
					if total > self.MAX_UNCOMPRESSED_BYTES:
						raise DataUpdateError("expanded package exceeds the safety limit")
					target = staging / path
					target.parent.mkdir(parents=True, exist_ok=True)
					with archive.open(info) as source, target.open("wb") as destination:
						shutil.copyfileobj(source, destination, 64 * 1024)
		except (zipfile.BadZipFile, OSError) as error:
			raise DataUpdateError(f"invalid package archive: {error}") from error

	def _validate(self, package: DataPackageManifest, root: Path) -> None:
		try:
			if package.data_type == "locations":
				version = BundledLocationRepository(root).location_data_version
			elif package.data_type == "timezones":
				version = BundledTimezoneProvider(root).tz_data_version
			elif package.data_type == "ummalqura":
				version = UmmAlQuraProvider(root).hijri_data_version
			elif package.data_type == "calculationMethods":
				version = BundledCalculationMethodRepository(root).calculation_method_data_version
			else:
				version = BundledArabianCalendarRepository(root).arabian_calendar_data_version
		except Exception as error:
			raise DataUpdateError(f"package structure is invalid for {package.data_type}: {error}") from error
		if version != package.data_version:
			raise DataUpdateError(f"dataVersion does not match package contents for {package.data_type}")
