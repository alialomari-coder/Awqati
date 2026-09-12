from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PLUGIN_PACKAGES) not in sys.path:
	sys.path.insert(0, str(PLUGIN_PACKAGES))

from awqati.infrastructure import BundledLocationRepository  # noqa: E402


def record(identifier: str, name: str, rank: int, population: int, admin1: str) -> dict[str, object]:
	return {
		"i": identifier, "n": name, "x": name, "e": [], "a": [],
		"lat": 1.0, "lon": 2.0, "tz": "Etc/UTC", "a1": admin1, "a2": "",
		"p": population, "f": "PPL", "r": rank,
	}


class LocationSearchOrderTests(unittest.TestCase):
	def test_order_is_strength_admin_population_then_stable_id_and_subdivisions_differ(self) -> None:
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			(root / "countries").mkdir()
			records = [
				record("12", "Springfield Heights", 9, 5000, "Illinois"),
				record("10", "Springfield", 9, 1000, "Illinois"),
				record("9", "Springfield", 9, 1000, "Illinois"),
				record("11", "Springfield", 1, 500, "Massachusetts"),
			]
			payload = json.dumps(
				{"schemaVersion": 1, "countryCode": "US", "cities": records},
				separators=(",", ":"),
			).encode("utf-8")
			compressed = gzip.compress(payload, mtime=0)
			(root / "countries/US.json.gz").write_bytes(compressed)
			metadata = {
				"schemaVersion": 2, "locationDataVersion": "fixture", "cityCount": 4, "countryCount": 1,
				"countries": [{
					"code": "US", "name": "United States", "cityCount": 4,
					"file": "countries/US.json.gz", "sha256": hashlib.sha256(compressed).hexdigest(),
				}],
			}
			(root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
			matches = BundledLocationRepository(root).search("US", "Springfield")
			self.assertEqual([match.location.location_id for match in matches], ["11", "9", "10", "12"])
			self.assertEqual(matches[0].subdivisions, ("Massachusetts",))
			self.assertEqual(matches[1].subdivisions, ("Illinois",))


if __name__ == "__main__":
	unittest.main()
