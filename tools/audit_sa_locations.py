"""Audit the final bundled Saudi location file for duplicate candidates."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Iterable

try:
	from tools.build_locations import distance_km, normalize_name
except ModuleNotFoundError:
	from build_locations import distance_km, normalize_name


def record_names(record: dict[str, object]) -> set[str]:
	values: Iterable[object] = (
		record.get("n", ""), record.get("x", ""),
		*record.get("a", []), *record.get("e", []),
	)
	return {normalized for value in values if (normalized := normalize_name(str(value)))}


def summary(record: dict[str, object]) -> dict[str, object]:
	return {
		"geonameId": record["i"], "name": record["n"], "latitude": record["lat"],
		"longitude": record["lon"], "featureCode": record["f"], "population": record["p"],
		"admin1": record["a1"], "admin2": record["a2"], "arabicNames": record["a"],
		"englishNames": record["e"],
	}


def audit(data_path: Path, supplement_path: Path) -> dict[str, object]:
	payload = json.loads(gzip.decompress(data_path.read_bytes()))
	records = payload["cities"]
	supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
	reviewed = {
		frozenset(str(identifier) for identifier in item["geonameIds"]): item
		for item in supplement.get("reviewedSimilarities", [])
	}
	seen: set[str] = set()
	confirmed: list[dict[str, object]] = []
	for record in records:
		identifier = str(record["i"])
		if identifier in seen:
			confirmed.append({"reason": "duplicate geonameId", "records": [summary(record)]})
		seen.add(identifier)

	potential: list[dict[str, object]] = []
	legitimate: list[dict[str, object]] = []
	names = [record_names(record) for record in records]
	for left_index, left in enumerate(records):
		for right_index in range(left_index + 1, len(records)):
			right = records[right_index]
			shared = sorted(names[left_index] & names[right_index])
			if not shared:
				continue
			distance = distance_km(left, right)
			pair = frozenset((str(left["i"]), str(right["i"])))
			candidate = {
				"sharedNormalizedNames": shared, "distanceKm": round(distance, 3),
				"records": [summary(left), summary(right)],
			}
			if pair in reviewed:
				candidate["reason"] = reviewed[pair]["reason"]
				legitimate.append(candidate)
			elif distance <= 1.0 and left["a1"] == right["a1"]:
				candidate["reason"] = "same normalized name, same admin1, and within 1 km"
				confirmed.append(candidate)
			elif distance <= 10.0 or left["a1"] == right["a1"]:
				candidate["reason"] = "shared normalized name with geographic or administrative similarity"
				potential.append(candidate)

	return {
		"countryCode": "SA", "recordCount": len(records),
		"confirmedDuplicateCount": len(confirmed),
		"potentialDuplicateCount": len(potential),
		"reviewedLegitimateSimilarityCount": len(legitimate),
		"confirmedDuplicates": confirmed,
		"potentialDuplicates": potential,
		"reviewedLegitimateSimilarities": legitimate,
	}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--data", required=True, type=Path)
	parser.add_argument("--supplement", required=True, type=Path)
	parser.add_argument("--output", type=Path)
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	result = audit(args.data, args.supplement)
	encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
	if args.output:
		args.output.write_text(encoded, encoding="utf-8", newline="\n")
	print(encoded, end="")
	return 1 if result["confirmedDuplicateCount"] else 0


if __name__ == "__main__":
	raise SystemExit(main())
