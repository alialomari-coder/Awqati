from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "addon" / "globalPlugins" / "awqati" / "data"


class GeneratedDataIntegrityTests(unittest.TestCase):
	def test_every_location_file_checksum_header_and_count_matches_metadata(self) -> None:
		root = DATA / "locations"
		metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
		total = 0
		listed: set[Path] = set()
		for entry in metadata["countries"]:
			path = root / entry["file"]
			listed.add(path.resolve())
			compressed = path.read_bytes()
			self.assertEqual(hashlib.sha256(compressed).hexdigest(), entry["sha256"], entry["code"])
			payload = json.loads(gzip.decompress(compressed))
			self.assertEqual(payload["countryCode"], entry["code"])
			self.assertEqual(len(payload["cities"]), entry["cityCount"])
			total += len(payload["cities"])
		actual = {path.resolve() for path in (root / "countries").glob("*.json.gz")}
		self.assertEqual(actual, listed)
		self.assertEqual(total, metadata["cityCount"])

	def test_every_timezone_file_checksum_and_path_matches_metadata(self) -> None:
		root = DATA / "timezones"
		metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
		listed: set[Path] = set()
		for key, expected_hash in metadata["zones"].items():
			self.assertNotIn("..", key.split("/"))
			path = root / "zoneinfo" / Path(*key.split("/"))
			listed.add(path.resolve())
			self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash, key)
		actual = {path.resolve() for path in (root / "zoneinfo").rglob("*") if path.is_file()}
		self.assertEqual(actual, listed)
		self.assertEqual(len(listed), metadata["zoneCount"])


if __name__ == "__main__":
	unittest.main()
