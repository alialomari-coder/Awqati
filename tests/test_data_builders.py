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

	def test_repeated_generation_is_byte_for_byte_deterministic(self) -> None:
		build_locations.build(self.args(self.root / "one"))
		build_locations.build(self.args(self.root / "two"))
		for relative in ("metadata.json", "countries/SA.json.gz", "countries/US.json.gz"):
			self.assertEqual((self.root / "one" / relative).read_bytes(), (self.root / "two" / relative).read_bytes())

	def test_invalid_city_record_fails_with_a_known_error(self) -> None:
		(self.root / "cities.txt").write_text("broken\n", encoding="utf-8")
		with self.assertRaises(build_locations.BuildLocationError):
			build_locations.build(self.args(self.root / "out"))


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
