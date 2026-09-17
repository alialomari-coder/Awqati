"""Build and validate the public Awqati data-update channel."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from addon.globalPlugins.awqati.application import CancellationToken, DataPackageManifest
from addon.globalPlugins.awqati.infrastructure import AtomicDataPackageInstaller


DATA_ROOT = ROOT / "addon" / "globalPlugins" / "awqati" / "data"
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/alialomari-coder/awqati-data/main"
_SAFE_VERSION = re.compile(r"[^A-Za-z0-9._+-]+")


@dataclass(frozen=True, slots=True)
class PackageSpec:
	data_type: str
	source: Path
	metadata: Path
	version_key: str
	schema_version: int


SPECS = (
	PackageSpec("locations", DATA_ROOT / "locations", DATA_ROOT / "locations" / "metadata.json",
		"locationDataVersion", 2),
	PackageSpec("timezones", DATA_ROOT / "timezones", DATA_ROOT / "timezones" / "metadata.json",
		"tzDataVersion", 1),
	PackageSpec("ummalqura", DATA_ROOT / "calendars" / "ummalqura",
		DATA_ROOT / "calendars" / "ummalqura" / "metadata.json", "hijriDataVersion", 1),
	PackageSpec("calculationMethods", DATA_ROOT / "calculation_methods",
		DATA_ROOT / "calculation_methods" / "methods.json", "calculationMethodDataVersion", 1),
	PackageSpec("arabianCalendar", DATA_ROOT / "arabian_calendar",
		DATA_ROOT / "arabian_calendar" / "metadata.json", "arabianCalendarDataVersion", 1),
)


def _metadata(spec: PackageSpec) -> tuple[str, int]:
	document = json.loads(spec.metadata.read_text(encoding="utf-8"))
	version = document.get(spec.version_key)
	schema = document.get("schemaVersion")
	if not isinstance(version, str) or not version:
		raise ValueError(f"missing {spec.version_key} in {spec.metadata}")
	if schema != spec.schema_version:
		raise ValueError(f"unexpected schemaVersion for {spec.data_type}: {schema!r}")
	return version, schema


def _archive(source: Path) -> tuple[bytes, tuple[str, ...]]:
	files = tuple(sorted(path for path in source.rglob("*") if path.is_file()))
	if not files:
		raise ValueError(f"package source is empty: {source}")
	stream = BytesIO()
	with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
		for path in files:
			name = path.relative_to(source).as_posix()
			info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
			info.compress_type = zipfile.ZIP_DEFLATED
			info.external_attr = 0o100644 << 16
			archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
				compresslevel=9)
	return stream.getvalue(), tuple(sorted(path.relative_to(source).as_posix() for path in files))


def _verify_archive(payload: bytes, expected: tuple[str, ...]) -> None:
	with zipfile.ZipFile(BytesIO(payload)) as archive:
		names = tuple(sorted(info.filename for info in archive.infolist() if not info.is_dir()))
		if names != expected:
			raise ValueError("archive file list does not match its source directory")
		for info in archive.infolist():
			path = Path(info.filename)
			if path.is_absolute() or ".." in path.parts:
				raise ValueError(f"unsafe archive path: {info.filename}")
			if (info.external_attr >> 16) & 0o170000 == 0o120000:
				raise ValueError(f"symbolic link in archive: {info.filename}")


def _write_immutable(path: Path, payload: bytes) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	if path.exists():
		if path.read_bytes() != payload:
			raise FileExistsError(f"refusing to replace historical package with different bytes: {path}")
		return
	path.write_bytes(payload)


def build(output: Path, base_url: str) -> dict[str, object]:
	packages: list[dict[str, object]] = []
	for spec in SPECS:
		version, schema = _metadata(spec)
		payload, files = _archive(spec.source)
		_verify_archive(payload, files)
		digest = hashlib.sha256(payload).hexdigest()
		file_version = _SAFE_VERSION.sub("-", version).strip("-")
		relative = Path("packages") / spec.data_type / f"{file_version}.zip"
		url = f"{base_url.rstrip('/')}/{relative.as_posix()}"
		manifest = DataPackageManifest(spec.data_type, version, schema, digest, url)
		with tempfile.TemporaryDirectory(prefix="awqati-channel-verify-") as temporary:
			AtomicDataPackageInstaller(Path(temporary)).install(manifest, payload, CancellationToken())
		_write_immutable(output / relative, payload)
		packages.append({
			"dataType": spec.data_type,
			"dataVersion": version,
			"schemaVersion": schema,
			"sha256": digest,
			"url": url,
		})
	document: dict[str, object] = {"schemaVersion": 1, "packages": packages}
	(output / "manifest.json").write_text(
		json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
	return document


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("output", type=Path, help="Local checkout of the awqati-data repository")
	parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
	args = parser.parse_args()
	document = build(args.output.resolve(), args.base_url)
	print(json.dumps(document, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
