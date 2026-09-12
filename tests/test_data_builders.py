from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import build_locations, build_timezones


def city_line(
	identifier: int,
	name: str,
	country: str,
	admin1: str,
	admin2: str,
	population: int,
	feature_code: str = "PPL",
	timezone_id: str = "Etc/UTC",
) -> str:
	fields = [
		str(identifier), name, name, "", "10.5", "20.5", "P", feature_code,
		country, "", admin1, admin2, "", "", str(population), "", "", timezone_id, "2026-09-11",
	]
	return "\t".join(fields)


class LocationBuilderTests(unittest.TestCase):
	def setUp(self) -> None:
		self.temporary = tempfile.TemporaryDirectory()
		self.root = Path(self.temporary.name)
		(self.root / "cities.txt").write_text(
			"\n".join((
				city_line(10, "Springfield", "US", "IL", "", 1000),
				city_line(11, "Springfield", "US", "MA", "", 500, "PPLA"),
				city_line(12, "Springfield Heights", "US", "IL", "", 5000),
				city_line(20, "Riyadh", "SA", "01", "", 7000000, "PPLC", "Asia/Riyadh"),
			)) + "\n",
			encoding="utf-8",
		)
		(self.root / "alternates.txt").write_text(
			"1\t20\tar\t\u0627\u0644\u0631\u064a\u0627\u0636\t1\t0\t0\t0\t\t\n"
			"2\t20\ten\tAr Riyad\t0\t0\t0\t0\t\t\n"
			"3\t999\tar\t\u0645\u062f\u064a\u0646\u0629 \u062e\u0627\u0631\u062c\u064a\u0629\t1\t0\t0\t0\t\t\n",
			encoding="utf-8",
		)
		(self.root / "countries.txt").write_text(
			"US\tUSA\t840\tUS\tUnited States\nSA\tSAU\t682\tSA\tSaudi Arabia\n",
			encoding="utf-8",
		)
		(self.root / "admin1.txt").write_text(
			"US.IL\tIllinois\tIllinois\t1\nUS.MA\tMassachusetts\tMassachusetts\t2\n"
			"SA.01\tRiyadh Region\tRiyadh Region\t3\n",
			encoding="utf-8",
		)
		(self.root / "admin2.txt").write_text("", encoding="utf-8")

	def tearDown(self) -> None:
		self.temporary.cleanup()

	def args(self, output: Path) -> argparse.Namespace:
		return argparse.Namespace(
			cities=str(self.root / "cities.txt"),
			alternate_names=str(self.root / "alternates.txt"),
			country_info=str(self.root / "countries.txt"),
			admin1=str(self.root / "admin1.txt"),
			admin2=str(self.root / "admin2.txt"),
			output=str(output),
			location_data_version="fixture-1",
			source_snapshot_date="2026-09-11",
			generated_at="2026-09-12",
		)

	def test_build_keeps_geoname_identity_fields_names_and_country_split(self) -> None:
		metadata = build_locations.build(self.args(self.root / "out"))
		self.assertEqual(metadata["schemaVersion"], 2)
		self.assertEqual(metadata["cityCount"], 4)
		self.assertEqual(metadata["countryCount"], 2)
		self.assertEqual({entry["code"] for entry in metadata["countries"]}, {"SA", "US"})
		payload = json.loads(__import__("gzip").decompress((self.root / "out/countries/SA.json.gz").read_bytes()))
		city = payload["cities"][0]
		self.assertEqual(city["i"], "20")
		self.assertEqual(city["a"], ["\u0627\u0644\u0631\u064a\u0627\u0636"])
		self.assertEqual(city["e"], ["Ar Riyad"])
		self.assertEqual((city["lat"], city["lon"], city["tz"]), (10.5, 20.5, "Asia/Riyadh"))
		self.assertEqual((city["p"], city["r"], city["a1"]), (7000000, 0, "Riyadh Region"))
		self.assertNotIn("999", (self.root / "out/countries/SA.json.gz").read_bytes().decode("latin1"))
		self.assertTrue((self.root / "out/spatial-index.bin.gz").is_file())
		self.assertEqual(metadata["spatialIndex"]["cityCount"], 4)

	def test_repeated_generation_is_byte_for_byte_deterministic(self) -> None:
		build_locations.build(self.args(self.root / "one"))
		build_locations.build(self.args(self.root / "two"))
		for relative in ("metadata.json", "spatial-index.bin.gz", "countries/SA.json.gz", "countries/US.json.gz"):
			self.assertEqual((self.root / "one" / relative).read_bytes(), (self.root / "two" / relative).read_bytes())

	def test_invalid_city_record_fails_with_a_known_error(self) -> None:
		(self.root / "cities.txt").write_text("broken\n", encoding="utf-8")
		with self.assertRaises(build_locations.BuildLocationError):
			build_locations.build(self.args(self.root / "out"))


class SaudiSupplementTests(unittest.TestCase):
	def setUp(self) -> None:
		self.temporary = tempfile.TemporaryDirectory()
		self.root = Path(self.temporary.name)

	def tearDown(self) -> None:
		self.temporary.cleanup()

	def city(
		self, identifier: str, name: str, latitude: float, longitude: float,
		admin1: str, admin2: str = "", population: int = 0,
	) -> dict[str, object]:
		return {
			"i": identifier, "n": name, "x": name, "cc": "SA", "lat": latitude, "lon": longitude,
			"tz": "Asia/Riyadh", "a1c": admin1, "a2c": admin2, "p": population,
			"f": "PPL", "r": 9, "en": {}, "ar": {},
		}

	def addition(
		self, identifier: str, name: str, latitude: float, longitude: float,
		admin1: str, admin2: str = "",
	) -> dict[str, object]:
		return {
			"geonameId": identifier, "name": name, "asciiName": name,
			"latitude": latitude, "longitude": longitude, "timezoneId": "Asia/Riyadh",
			"admin1Code": admin1, "admin2Code": admin2, "population": 0,
			"featureCode": "PPL", "arabicNames": [], "sourceRefs": ["fixture"],
		}

	def supplement(self, **sections: object) -> Path:
		payload = {
			"schemaVersion": 1, "countryCode": "SA", "version": "fixture-sa-1",
			"sources": [{"id": "fixture"}], "aliases": [], "merges": [], "additions": [],
		}
		payload.update(sections)
		path = self.root / "sa.json"
		path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
		return path

	def test_same_geoname_id_adds_arabic_to_one_existing_record(self) -> None:
		cities = {"10": self.city("10", "Al Khafji", 28.44, 48.49, "06")}
		path = self.supplement(aliases=[{
			"geonameId": "10", "arabicNames": ["الخفجي"], "sourceRefs": ["fixture"],
		}])
		result = build_locations.apply_sa_supplement(path, cities)
		self.assertEqual((len(cities), result["augmented"]), (1, 1))
		self.assertIn("الخفجي", cities["10"]["ar"])

	def test_documented_transliteration_duplicate_is_merged(self) -> None:
		cities = {
			"1": self.city("1", "Unaizah", 26.08793, 43.96368, "08", "55", 0),
			"2": self.city("2", "Unayzah", 26.10, 44.00, "08", "55", 183319),
		}
		path = self.supplement(merges=[{
			"sourceGeonameId": "2", "targetGeonameId": "1", "sourceRefs": ["fixture"],
		}])
		result = build_locations.apply_sa_supplement(path, cities)
		self.assertEqual((set(cities), result["merged"]), ({"1"}, 1))
		self.assertEqual(cities["1"]["p"], 183319)
		self.assertIn("Unayzah", cities["1"]["en"])

	def test_same_name_different_region_partial_name_and_proximity_alone_stay_separate(self) -> None:
		cities = {
			"1": self.city("1", "Al Aqiq", 20.0, 41.0, "02"),
			"2": self.city("2", "Al Jubayl", 27.0, 49.6, "06"),
			"3": self.city("3", "Near One", 24.0, 46.0, "10"),
		}
		path = self.supplement(additions=[
			self.addition("11", "Al Aqiq", 17.0, 44.0, "16"),
			self.addition("12", "Al Jubayl Industrial City", 27.001, 49.601, "06"),
			self.addition("13", "Near Two", 24.0001, 46.0001, "10"),
		])
		result = build_locations.apply_sa_supplement(path, cities)
		self.assertEqual((len(cities), result["added"]), (6, 3))

	def test_addition_rejects_reused_id_and_matching_normalized_name_evidence(self) -> None:
		cities = {"10": self.city("10", "Al Khafji", 28.44, 48.49, "06")}
		with self.assertRaises(build_locations.BuildLocationError):
			build_locations.apply_sa_supplement(
				self.supplement(additions=[self.addition("10", "Other", 0, 0, "01")]), cities,
			)
		with self.assertRaises(build_locations.BuildLocationError):
			build_locations.apply_sa_supplement(
				self.supplement(additions=[self.addition("11", "Al-Khafji", 28.4401, 48.4901, "06")]), cities,
			)

class TimezoneBuilderTests(unittest.TestCase):
	def test_extracts_only_tzif_files_and_reads_versions_and_license(self) -> None:
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			wheel = root / "tzdata.whl"
			with zipfile.ZipFile(wheel, "w") as archive:
				archive.writestr("tzdata-9.9.dist-info/METADATA", "Name: tzdata\nVersion: 9.9\n")
				archive.writestr("tzdata-9.9.dist-info/licenses/LICENSE", "test license\n")
				archive.writestr("tzdata/zoneinfo/tzdata.zi", "# version 2099z\n")
				archive.writestr("tzdata/zoneinfo/Test/Zone", b"TZif fixture")
				archive.writestr("tzdata/zoneinfo/__init__.py", "not runtime data")
			args = argparse.Namespace(
				wheel=str(wheel), output=str(root / "out"),
				source_url="https://example.invalid/tzdata.whl", generated_at="2026-09-12",
			)
			metadata = build_timezones.build(args)
			self.assertEqual((metadata["tzDataVersion"], metadata["ianaVersion"], metadata["zoneCount"]), ("9.9", "2099z", 1))
			self.assertTrue((root / "out/zoneinfo/Test/Zone").is_file())
			self.assertFalse((root / "out/zoneinfo/__init__.py").exists())
			self.assertEqual((root / "out/LICENSE.txt").read_text(encoding="utf-8"), "test license\n")


if __name__ == "__main__":
	unittest.main()
