"""Build Awqati's compact per-country database from official GeoNames inputs."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import gzip
import hashlib
from io import TextIOWrapper
import json
import math
from pathlib import Path
import re
from typing import Iterator
import unicodedata
import zipfile


SOURCE_URLS = {
	"cities": "https://download.geonames.org/export/dump/cities500.zip",
	"alternateNames": "https://download.geonames.org/export/dump/alternateNamesV2.zip",
	"countries": "https://download.geonames.org/export/dump/countryInfo.txt",
	"admin1": "https://download.geonames.org/export/dump/admin1CodesASCII.txt",
	"admin2": "https://download.geonames.org/export/dump/admin2Codes.txt",
}
ADMIN_RANKS = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPLA4": 4}
SA_DUPLICATE_DISTANCE_KM = 1.0


class BuildLocationError(RuntimeError):
	"""A source record cannot be represented safely in the generated database."""


def sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as source:
		for block in iter(lambda: source.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


@contextmanager
def source_lines(path: Path, preferred_member: str) -> Iterator[Iterator[str]]:
	if path.suffix.lower() == ".zip":
		with zipfile.ZipFile(path) as archive:
			names = [name for name in archive.namelist() if not name.endswith("/")]
			member = preferred_member if preferred_member in names else (names[0] if len(names) == 1 else "")
			if not member:
				raise BuildLocationError(f"Cannot select {preferred_member} in {path}")
			with archive.open(member) as raw, TextIOWrapper(raw, encoding="utf-8", newline="") as text:
				yield text
	else:
		with path.open("r", encoding="utf-8", newline="") as text:
			yield text


def read_country_names(path: Path) -> dict[str, str]:
	result: dict[str, str] = {}
	with source_lines(path, "countryInfo.txt") as lines:
		for line in lines:
			if not line or line.startswith("#"):
				continue
			fields = line.rstrip("\r\n").split("\t")
			if len(fields) >= 5 and len(fields[0]) == 2:
				result[fields[0]] = fields[4]
	return result


def read_admin_names(path: Path, preferred_member: str) -> dict[str, str]:
	result: dict[str, str] = {}
	with source_lines(path, preferred_member) as lines:
		for line in lines:
			fields = line.rstrip("\r\n").split("\t")
			if len(fields) >= 2 and fields[0] and fields[1]:
				result[fields[0]] = fields[1]
	return result


def read_cities(path: Path) -> dict[str, dict[str, object]]:
	cities: dict[str, dict[str, object]] = {}
	with source_lines(path, "cities500.txt") as lines:
		for line_number, fields in enumerate(csv.reader(lines, delimiter="\t"), 1):
			if not fields:
				continue
			if len(fields) < 19:
				raise BuildLocationError(f"cities500 line {line_number} has {len(fields)} fields")
			try:
				identifier = str(int(fields[0]))
				latitude = float(fields[4])
				longitude = float(fields[5])
				population = int(fields[14] or "0")
			except ValueError as error:
				raise BuildLocationError(f"cities500 line {line_number} contains invalid numbers") from error
			name, ascii_name, country, timezone_id = fields[1], fields[2], fields[8], fields[17]
			if not name or not country or len(country) != 2 or not timezone_id:
				raise BuildLocationError(f"cities500 line {line_number} is missing required identity fields")
			if identifier in cities:
				raise BuildLocationError(f"duplicate geonameId {identifier}")
			cities[identifier] = {
				"i": identifier,
				"n": name,
				"x": ascii_name,
				"cc": country,
				"lat": latitude,
				"lon": longitude,
				"tz": timezone_id,
				"a1c": fields[10],
				"a2c": fields[11],
				"p": population,
				"f": fields[7],
				"r": ADMIN_RANKS.get(fields[7], 9),
				"en": {},
				"ar": {},
			}
	return cities


def add_alternate_names(path: Path, cities: dict[str, dict[str, object]]) -> None:
	with source_lines(path, "alternateNamesV2.txt") as lines:
		for fields in csv.reader(lines, delimiter="\t"):
			if len(fields) < 8 or fields[1] not in cities or fields[2] not in {"ar", "en"}:
				continue
			name = fields[3].strip()
			if not name or fields[7] == "1":
				continue
			language = fields[2]
			names = cities[fields[1]][language]
			assert isinstance(names, dict)
			priority = 0 if fields[4] == "1" else 1
			names[name] = min(priority, names.get(name, priority))


def normalize_name(value: str) -> str:
	"""Normalize a source name for conservative build-time duplicate checks."""
	value = unicodedata.normalize("NFKD", value).casefold()
	value = "".join(character for character in value if not unicodedata.combining(character))
	return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def distance_km(first: dict[str, object], second: dict[str, object]) -> float:
	lat1, lon1 = math.radians(float(first["lat"])), math.radians(float(first["lon"]))
	lat2, lon2 = math.radians(float(second["lat"])), math.radians(float(second["lon"]))
	dlat, dlon = lat2 - lat1, lon2 - lon1
	a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
	return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _name_set(city: dict[str, object]) -> set[str]:
	values = [str(city["n"]), str(city["x"])]
	for language in ("en", "ar"):
		names = city.get(language, {})
		if isinstance(names, dict):
			values.extend(str(name) for name in names)
	return {normalized for value in values if (normalized := normalize_name(value))}


def _merge_names(target: dict[str, object], source: dict[str, object]) -> None:
	for language in ("en", "ar"):
		target_names = target[language]
		assert isinstance(target_names, dict)
		for name in source.get(language, {}):
			target_names[str(name)] = min(1, target_names.get(str(name), 1))
	for name in (str(source["n"]), str(source["x"])):
		if name and name not in {str(target["n"]), str(target["x"])}:
			target_names = target["en"]
			assert isinstance(target_names, dict)
			target_names[name] = min(1, target_names.get(name, 1))
	target["p"] = max(int(target["p"]), int(source["p"]))


def apply_sa_supplement(path: Path, cities: dict[str, dict[str, object]]) -> dict[str, object]:
	"""Merge the reviewed Saudi supplement into the ordinary global build input."""
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as error:
		raise BuildLocationError(f"Cannot read Saudi supplement {path}: {error}") from error
	if payload.get("schemaVersion") != 1 or payload.get("countryCode") != "SA" or not payload.get("version"):
		raise BuildLocationError("Saudi supplement has an invalid header")
	sources = payload.get("sources")
	if not isinstance(sources, list) or not sources:
		raise BuildLocationError("Saudi supplement must document its sources")
	source_ids = {source.get("id") for source in sources if isinstance(source, dict)}

	def validate_refs(item: dict[str, object]) -> None:
		refs = item.get("sourceRefs")
		if not isinstance(refs, list) or not refs or any(ref not in source_ids for ref in refs):
			raise BuildLocationError("Saudi supplement record has unknown or missing sourceRefs")

	merged = 0
	for item in payload.get("merges", []):
		validate_refs(item)
		source_id, target_id = str(item["sourceGeonameId"]), str(item["targetGeonameId"])
		if source_id == target_id or source_id not in cities or target_id not in cities:
			raise BuildLocationError(f"Invalid Saudi merge {source_id} -> {target_id}")
		if cities[source_id]["cc"] != "SA" or cities[target_id]["cc"] != "SA":
			raise BuildLocationError("Saudi merges may only reference Saudi records")
		_merge_names(cities[target_id], cities.pop(source_id))
		merged += 1

	augmented = 0
	for item in payload.get("aliases", []):
		validate_refs(item)
		identifier = str(item["geonameId"])
		if identifier not in cities or cities[identifier]["cc"] != "SA":
			raise BuildLocationError(f"Saudi alias target does not exist: {identifier}")
		changed = False
		for language, key in (("ar", "arabicNames"), ("en", "englishNames")):
			names = cities[identifier][language]
			assert isinstance(names, dict)
			for raw_name in item.get(key, []):
				name = str(raw_name).strip()
				if not name:
					raise BuildLocationError(f"Saudi alias {identifier} contains an empty name")
				if name not in names:
					names[name] = 1
					changed = True
		if changed:
			augmented += 1

	added = 0
	for item in payload.get("additions", []):
		validate_refs(item)
		identifier = str(item["geonameId"])
		if identifier in cities:
			raise BuildLocationError(f"Saudi addition reuses an existing geonameId: {identifier}")
		try:
			candidate = {
				"i": str(int(identifier)), "n": str(item["name"]), "x": str(item["asciiName"]),
				"cc": "SA", "lat": float(item["latitude"]), "lon": float(item["longitude"]),
				"tz": str(item["timezoneId"]), "a1c": str(item["admin1Code"]),
				"a2c": str(item.get("admin2Code", "")), "p": int(item.get("population", 0)),
				"f": str(item["featureCode"]), "r": ADMIN_RANKS.get(str(item["featureCode"]), 9),
				"en": {str(name): 1 for name in item.get("englishNames", [])},
				"ar": {str(name): 1 for name in item.get("arabicNames", [])},
			}
		except (KeyError, TypeError, ValueError) as error:
			raise BuildLocationError(f"Invalid Saudi addition {identifier}") from error
		if not candidate["n"] or not candidate["x"] or candidate["tz"] != "Asia/Riyadh":
			raise BuildLocationError(f"Saudi addition {identifier} has invalid identity fields")
		candidate_names = _name_set(candidate)
		for existing in cities.values():
			if existing["cc"] != "SA":
				continue
			same_admin = existing["a1c"] == candidate["a1c"] and existing["a2c"] == candidate["a2c"]
			shared_name = bool(candidate_names & _name_set(existing))
			nearby = distance_km(candidate, existing) <= SA_DUPLICATE_DISTANCE_KM
			if shared_name and (same_admin or nearby):
				raise BuildLocationError(
					f"Saudi addition {identifier} duplicates {existing['i']} by name and administrative/geographic evidence"
				)
		cities[identifier] = candidate
		added += 1
	return {"version": payload["version"], "added": added, "augmented": augmented, "merged": merged}

def _ordered_names(value: object) -> list[str]:
	assert isinstance(value, dict)
	return [name for name, _ in sorted(value.items(), key=lambda item: (item[1], item[0].casefold(), item[0]))]


def _gzip_json(payload: object) -> bytes:
	encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
	return gzip.compress(encoded, compresslevel=9, mtime=0)


def build(args: argparse.Namespace) -> dict[str, object]:
	cities_path = Path(args.cities)
	alternate_path = Path(args.alternate_names)
	country_path = Path(args.country_info)
	admin1_path = Path(args.admin1)
	admin2_path = Path(args.admin2)
	sa_supplement_path = Path(args.sa_supplement) if getattr(args, "sa_supplement", None) else None
	for path in (cities_path, alternate_path, country_path, admin1_path, admin2_path):
		if not path.is_file():
			raise BuildLocationError(f"Source file does not exist: {path}")

	cities = read_cities(cities_path)
	add_alternate_names(alternate_path, cities)
	sa_supplement_result = apply_sa_supplement(sa_supplement_path, cities) if sa_supplement_path else None
	country_names = read_country_names(country_path)
	admin1_names = read_admin_names(admin1_path, "admin1CodesASCII.txt")
	admin2_names = read_admin_names(admin2_path, "admin2Codes.txt")

	grouped: dict[str, list[dict[str, object]]] = {}
	for city in cities.values():
		country = str(city.pop("cc"))
		admin1_code = str(city.pop("a1c"))
		admin2_code = str(city.pop("a2c"))
		city["a1"] = admin1_names.get(f"{country}.{admin1_code}", admin1_code)
		city["a2"] = admin2_names.get(f"{country}.{admin1_code}.{admin2_code}", admin2_code)
		city["e"] = _ordered_names(city.pop("en"))
		city["a"] = _ordered_names(city.pop("ar"))
		grouped.setdefault(country, []).append(city)

	output = Path(args.output)
	countries_dir = output / "countries"
	countries_dir.mkdir(parents=True, exist_ok=True)
	entries: list[dict[str, object]] = []
	generated_names: set[str] = set()
	for code in sorted(grouped):
		records = sorted(grouped[code], key=lambda record: int(str(record["i"])))
		data = _gzip_json({"schemaVersion": 1, "countryCode": code, "cities": records})
		filename = f"{code}.json.gz"
		(countries_dir / filename).write_bytes(data)
		generated_names.add(filename)
		entries.append({
			"code": code,
			"name": country_names.get(code, code),
			"cityCount": len(records),
			"file": f"countries/{filename}",
			"sha256": hashlib.sha256(data).hexdigest(),
		})
	for old_path in countries_dir.glob("*.json.gz"):
		if old_path.name not in generated_names:
			old_path.unlink()

	source_paths = {
		"cities": cities_path,
		"alternateNames": alternate_path,
		"countries": country_path,
		"admin1": admin1_path,
		"admin2": admin2_path,
	}
	metadata: dict[str, object] = {
		"schemaVersion": 1,
		"locationDataVersion": args.location_data_version,
		"generatedAt": args.generated_at,
		"sourceSnapshotDate": args.source_snapshot_date,
		"source": "GeoNames cities500 with reviewed Saudi supplement" if sa_supplement_path else "GeoNames cities500",
		"license": "CC BY 4.0",
		"cityCount": len(cities),
		"countryCount": len(entries),
		"countries": entries,
		"sources": {
			key: {"url": SOURCE_URLS[key], "sha256": sha256(path)}
			for key, path in source_paths.items()
		},
	}
	if sa_supplement_path and sa_supplement_result:
		metadata["saudiSupplement"] = {
			**sa_supplement_result,
			"file": sa_supplement_path.name,
			"sha256": sha256(sa_supplement_path),
		}
	(output / "metadata.json").write_text(
		json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
		encoding="utf-8",
		newline="\n",
	)
	return metadata


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--cities", required=True)
	parser.add_argument("--alternate-names", required=True)
	parser.add_argument("--country-info", required=True)
	parser.add_argument("--admin1", required=True)
	parser.add_argument("--admin2", required=True)
	parser.add_argument("--sa-supplement")
	parser.add_argument("--output", required=True)
	parser.add_argument("--location-data-version", required=True)
	parser.add_argument("--source-snapshot-date", required=True)
	parser.add_argument("--generated-at", required=True)
	return parser.parse_args()


if __name__ == "__main__":
	result = build(parse_args())
	print(f"Built {result['cityCount']} cities in {result['countryCount']} countries")
