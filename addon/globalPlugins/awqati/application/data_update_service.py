"""Manual validation and orchestration for Awqati data packages."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Protocol

from .operation import CancellationToken, OperationCancelled


SUPPORTED_DATA_PACKAGES = {
	"locations": ("locationDataVersion", 2),
	"timezones": ("tzDataVersion", 1),
	"ummalqura": ("hijriDataVersion", 1),
	"calculationMethods": ("calculationMethodDataVersion", 1),
	"arabianCalendar": ("arabianCalendarDataVersion", 1),
}


class DataUpdateError(RuntimeError):
	"""A manifest, package, network, or atomic replacement failed."""


class UpdateChannelUnavailable(DataUpdateError):
	"""The project has not configured an HTTPS data-update manifest."""


@dataclass(frozen=True, slots=True)
class DataPackageManifest:
	data_type: str
	data_version: str
	schema_version: int
	sha256: str
	url: str


@dataclass(frozen=True, slots=True)
class DataUpdateResult:
	updated: tuple[str, ...]
	unchanged: tuple[str, ...]


class UpdateTransport(Protocol):
	def read_json(self, url: str, *, timeout: float, cancellation: CancellationToken) -> Mapping[str, Any]: ...
	def read_bytes(self, url: str, *, timeout: float, cancellation: CancellationToken) -> bytes: ...


class DataPackageInstaller(Protocol):
	def install(self, package: DataPackageManifest, payload: bytes,
			cancellation: CancellationToken) -> None: ...


class DataUpdateService:
	"""Check a configured manifest and install only the five approved packages."""

	def __init__(self, manifest_url: str | None, transport: UpdateTransport,
			installer: DataPackageInstaller, current_versions: Mapping[str, str]) -> None:
		self._manifest_url = manifest_url
		self._transport = transport
		self._installer = installer
		self._current_versions = dict(current_versions)

	@property
	def channel_available(self) -> bool:
		return bool(self._manifest_url)

	def check(self, *, timeout: float = 15.0,
			cancellation: CancellationToken | None = None) -> DataUpdateResult:
		token = cancellation or CancellationToken()
		token.raise_if_cancelled()
		if not self._manifest_url:
			raise UpdateChannelUnavailable("no project data-update manifest URL is configured")
		if not self._manifest_url.startswith("https://"):
			raise UpdateChannelUnavailable("the data-update manifest must use HTTPS")
		try:
			document = self._transport.read_json(self._manifest_url, timeout=timeout, cancellation=token)
			packages = self._parse_manifest(document)
		except DataUpdateError:
			raise
		except Exception as error:
			raise DataUpdateError(str(error)) from error
		updated, unchanged = [], []
		for package in packages:
			token.raise_if_cancelled()
			if self._current_versions.get(package.data_type) == package.data_version:
				unchanged.append(package.data_type)
				continue
			try:
				payload = self._transport.read_bytes(package.url, timeout=timeout, cancellation=token)
			except OperationCancelled:
				raise
			except Exception as error:
				raise DataUpdateError(f"could not download {package.data_type}: {error}") from error
			token.raise_if_cancelled()
			if hashlib.sha256(payload).hexdigest() != package.sha256:
				raise DataUpdateError(f"SHA-256 mismatch for {package.data_type}")
			self._installer.install(package, payload, token)
			updated.append(package.data_type)
		return DataUpdateResult(tuple(updated), tuple(unchanged))

	@staticmethod
	def _parse_manifest(document: Mapping[str, Any]) -> tuple[DataPackageManifest, ...]:
		if not isinstance(document, Mapping) or document.get("schemaVersion") != 1:
			raise DataUpdateError("unsupported update manifest schemaVersion")
		items = document.get("packages")
		if not isinstance(items, list):
			raise DataUpdateError("update manifest packages must be an array")
		result, seen = [], set()
		for item in items:
			if not isinstance(item, Mapping):
				raise DataUpdateError("invalid update package entry")
			data_type = item.get("dataType")
			if data_type not in SUPPORTED_DATA_PACKAGES or data_type in seen:
				raise DataUpdateError(f"unsupported or duplicate dataType: {data_type}")
			version, schema, digest, url = (item.get("dataVersion"), item.get("schemaVersion"),
				item.get("sha256"), item.get("url"))
			if not isinstance(version, str) or not version:
				raise DataUpdateError(f"invalid dataVersion for {data_type}")
			if schema != SUPPORTED_DATA_PACKAGES[data_type][1]:
				raise DataUpdateError(f"unsupported schemaVersion for {data_type}")
			if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
				raise DataUpdateError(f"invalid SHA-256 for {data_type}")
			if not isinstance(url, str) or not url.startswith("https://"):
				raise DataUpdateError(f"package URL must use HTTPS for {data_type}")
			seen.add(data_type)
			result.append(DataPackageManifest(data_type, version, schema, digest.lower(), url))
		return tuple(result)
