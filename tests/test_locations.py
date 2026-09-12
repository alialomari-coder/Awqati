from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PLUGIN_PACKAGES) not in sys.path:
	sys.path.insert(0, str(PLUGIN_PACKAGES))

from awqati.application import LocationRepository  # noqa: E402
from awqati.infrastructure import (  # noqa: E402
	BundledLocationRepository,
	InvalidCountryCodeError,
	LocationDataError,
	normalize_location_text,
)


DATA_ROOT = PLUGIN_PACKAGES / "awqati" / "data" / "locations"


class BundledLocationRepositoryTests(unittest.TestCase):
	def test_import_and_construction_do_not_read_location_files(self) -> None:
		script = """
import pathlib
original_text = pathlib.Path.read_text
original_bytes = pathlib.Path.read_bytes
def reject_text(path, *args, **kwargs):
    if 'data\\\\locations' in str(path):
        raise AssertionError(path)
    return original_text(path, *args, **kwargs)
def reject_bytes(path, *args, **kwargs):
    if 'data\\\\locations' in str(path):
        raise AssertionError(path)
    return original_bytes(path, *args, **kwargs)
pathlib.Path.read_text = reject_text
pathlib.Path.read_bytes = reject_bytes
from awqati.infrastructure import BundledLocationRepository
repository = BundledLocationRepository()
assert repository.loaded_country_codes == ()
"""
		environment = dict(__import__("os").environ)
		environment["PYTHONPATH"] = str(PLUGIN_PACKAGES)
		result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment, capture_output=True, text=True)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_country_index_and_search_load_only_requested_country(self) -> None:
		repository = BundledLocationRepository(max_cached_countries=2)
		self.assertIsInstance(repository, LocationRepository)
		self.assertEqual(repository.loaded_country_codes, ())
		countries = repository.countries()
		self.assertGreater(len(countries), 200)
		self.assertEqual(repository.loaded_country_codes, ())
		results = repository.search("SA", "\u0627\u0644\u0631\u064a\u0627\u0636")
		self.assertEqual(results[0].location.location_id, "108410")
		self.assertEqual(results[0].location.timezone_id, "Asia/Riyadh")
		self.assertEqual(repository.loaded_country_codes, ("SA",))
		repository.search("EG", "\u0627\u0644\u0642\u0627\u0647\u0631\u0629")
		self.assertEqual(repository.loaded_country_codes, ("SA", "EG"))
		repository.search("TR", "Istanbul")
		self.assertEqual(repository.loaded_country_codes, ("EG", "TR"))

	def test_names_normalize_case_diacritics_tatweel_and_spaces(self) -> None:
		self.assertEqual(normalize_location_text("  RIY\u0100DH  "), "riyadh")
		self.assertEqual(
			normalize_location_text("\u0627\u0644\u0640\u0631\u0650\u0651\u064a\u0627\u0636"),
			normalize_location_text("\u0627\u0644\u0631\u064a\u0627\u0636"),
		)
		repository = BundledLocationRepository()
		self.assertEqual(repository.search("GB", "  LoNDoN  ")[0].location.name, "London")

	def test_get_preserves_stable_id_and_result_has_subdivision(self) -> None:
		repository = BundledLocationRepository()
		match = repository.get("SA", "108410")
		self.assertIsNotNone(match)
		assert match is not None
		self.assertEqual(match.location.location_id, "108410")
		self.assertIn("Riyadh", match.admin1_name)

	def test_rejects_invalid_country_codes_and_corrupt_country_data(self) -> None:
		repository = BundledLocationRepository()
		for code in ("../SA", "S/A", "SA.json", ""):
			with self.subTest(code=code), self.assertRaises(InvalidCountryCodeError):
				repository.search(code, "x")
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			(root / "countries").mkdir()
			payload = gzip.compress(b'{"schemaVersion":1,"countryCode":"ZZ","cities":[]}', mtime=0)
			metadata = {
				"schemaVersion": 1, "locationDataVersion": "fixture", "cityCount": 0, "countryCount": 1,
				"countries": [{"code": "ZZ", "name": "Test", "cityCount": 0, "file": "countries/ZZ.json.gz", "sha256": hashlib.sha256(payload).hexdigest()}],
			}
			(root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
			(root / "countries/ZZ.json.gz").write_bytes(b"corrupt")
			with self.assertRaises(LocationDataError):
				BundledLocationRepository(root).search("ZZ", "x")

	def test_runtime_operation_does_not_need_network(self) -> None:
		with mock.patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
			match = BundledLocationRepository().search("MY", "Kuala Lumpur")[0]
		self.assertEqual(match.location.timezone_id, "Asia/Kuala_Lumpur")


class BundledWorldCoverageTests(unittest.TestCase):
	def test_metadata_matches_every_generated_country_file_and_is_global(self) -> None:
		metadata = json.loads((DATA_ROOT / "metadata.json").read_text(encoding="utf-8"))
		files = sorted((DATA_ROOT / "countries").glob("*.json.gz"))
		self.assertEqual(metadata["locationDataVersion"], "geonames-cities500-2026-09-11")
		self.assertEqual(metadata["countryCount"], len(files))
		self.assertEqual(metadata["countryCount"], len(metadata["countries"]))
		self.assertEqual(metadata["cityCount"], sum(entry["cityCount"] for entry in metadata["countries"]))
		self.assertGreater(metadata["cityCount"], 180000)
		self.assertGreater(metadata["countryCount"], 200)
		codes = {entry["code"] for entry in metadata["countries"]}
		self.assertTrue({"SA", "EG", "TR", "ID", "MY", "GB", "NO", "US", "CA", "AU", "BR", "ZA"} <= codes)
		self.assertEqual({path.stem.split(".")[0] for path in files}, codes)

	def test_reference_cities_across_regions_are_searchable(self) -> None:
		repository = BundledLocationRepository()
		for country, query in (
			("SA", "Riyadh"), ("EG", "Cairo"), ("TR", "Istanbul"), ("ID", "Jakarta"),
			("MY", "Kuala Lumpur"), ("GB", "London"), ("NO", "Oslo"), ("US", "New York"),
			("CA", "Toronto"), ("AU", "Sydney"), ("BR", "Sao Paulo"), ("ZA", "Cape Town"),
		):
			with self.subTest(country=country, query=query):
				self.assertTrue(repository.search(country, query, 5))


if __name__ == "__main__":
	unittest.main()
