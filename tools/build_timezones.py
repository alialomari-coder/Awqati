"""Extract deterministic TZif data and metadata from the official Python tzdata wheel."""

from __future__ import annotations

import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import re
import zipfile


class BuildTimezoneError(RuntimeError):
	"""The supplied tzdata wheel is missing required or valid content."""


def sha256_bytes(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def build(args: argparse.Namespace) -> dict[str, object]:
	wheel = Path(args.wheel)
	if not wheel.is_file():
		raise BuildTimezoneError(f"Wheel does not exist: {wheel}")
	output = Path(args.output)
	zone_root = output / "zoneinfo"
	zone_root.mkdir(parents=True, exist_ok=True)
	zones: dict[str, str] = {}
	zone_data: dict[str, bytes] = {}
	license_text = ""
	package_version = ""
	iana_version = ""

	with zipfile.ZipFile(wheel) as archive:
		for name in archive.namelist():
			if name.endswith(".dist-info/METADATA"):
				metadata = Parser().parsestr(archive.read(name).decode("utf-8"))
				package_version = metadata.get("Version", "")
			elif name == "tzdata/zoneinfo/tzdata.zi":
				first_line = archive.read(name).decode("utf-8").splitlines()[0]
				match = re.fullmatch(r"# version (\S+)", first_line)
				iana_version = match.group(1) if match else ""
			elif name.endswith(".dist-info/licenses/LICENSE") or name.endswith(".dist-info/LICENSE"):
				license_text = archive.read(name).decode("utf-8")
			elif name.startswith("tzdata/zoneinfo/") and not name.endswith("/"):
				data = archive.read(name)
				if data.startswith(b"TZif"):
					key = name.removeprefix("tzdata/zoneinfo/")
					parts = Path(key).parts
					if not parts or any(part in {"", ".", ".."} for part in parts):
						raise BuildTimezoneError(f"Unsafe zone path in wheel: {name}")
					zones[key] = sha256_bytes(data)
					zone_data[key] = data
	if not package_version or not iana_version or not license_text or not zones:
		raise BuildTimezoneError("Wheel is missing version, IANA version, license, or TZif files")

	generated_paths: set[Path] = set()
	for key in sorted(zone_data):
		target = zone_root.joinpath(*key.split("/"))
		target.parent.mkdir(parents=True, exist_ok=True)
		target.write_bytes(zone_data[key])
		generated_paths.add(target.resolve())
	for old_path in zone_root.rglob("*"):
		if old_path.is_file() and old_path.resolve() not in generated_paths:
			old_path.unlink()
	for old_dir in sorted((path for path in zone_root.rglob("*") if path.is_dir()), reverse=True):
		if not any(old_dir.iterdir()):
			old_dir.rmdir()

	wheel_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
	metadata: dict[str, object] = {
		"schemaVersion": 1,
		"tzDataVersion": package_version,
		"ianaVersion": iana_version,
		"generatedAt": args.generated_at,
		"source": "Python tzdata",
		"sourceUrl": args.source_url,
		"sourceSha256": wheel_hash,
		"license": "Apache-2.0",
		"zoneCount": len(zones),
		"zones": dict(sorted(zones.items())),
	}
	output.mkdir(parents=True, exist_ok=True)
	(output / "metadata.json").write_text(
		json.dumps(metadata, indent=2, sort_keys=True) + "\n",
		encoding="utf-8",
		newline="\n",
	)
	(output / "LICENSE.txt").write_text(license_text, encoding="utf-8", newline="\n")
	return metadata


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--wheel", required=True)
	parser.add_argument("--output", required=True)
	parser.add_argument("--source-url", required=True)
	parser.add_argument("--generated-at", required=True)
	return parser.parse_args()


if __name__ == "__main__":
	result = build(parse_args())
	print(
		f"Built {result['zoneCount']} bundled timezones "
		f"from tzdata {result['tzDataVersion']} / IANA {result['ianaVersion']}"
	)
