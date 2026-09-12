from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import CalculationMethodProvider  # noqa: E402
from awqati.domain import CalculationMethod  # noqa: E402
from awqati.infrastructure import (  # noqa: E402
	BundledCalculationMethodRepository,
	CalculationMethodDataError,
)


EXPECTED = {
	"MWL": (18, 17, None, None, 0), "ISNA": (15, 15, None, None, 0),
	"EGYPT": (19.5, 17.5, None, None, 0), "MAKKAH": (18.5, None, 90, 120, 0),
	"KARACHI": (18, 18, None, None, 0), "GULF": (19.5, None, 90, None, 0),
	"KUWAIT": (18, 17.5, None, None, 0), "QATAR": (18, None, 90, None, 0),
	"SINGAPORE": (20, 18, None, None, 0), "JAKIM": (20, 18, None, None, 0),
	"KEMENAG": (20, 18, None, None, 0), "FRANCE": (12, 12, None, None, 0),
	"RUSSIA": (16, 15, None, None, 0), "TUNISIA": (18, 18, None, None, 0),
	"ALGERIA": (18, 17, None, None, 0), "MOROCCO": (19, 17, None, None, 0),
	"PORTUGAL": (18, None, 77, None, 3), "JORDAN": (18, 18, None, None, 5),
	"TURKEY": (18, 17, None, None, 0),
}


class CalculationMethodDataTests(unittest.TestCase):
	def setUp(self) -> None:
		self.repository = BundledCalculationMethodRepository()

	def test_all_19_approved_definitions_match_the_specification(self) -> None:
		self.assertIsInstance(self.repository, CalculationMethodProvider)
		methods = self.repository.all_methods()
		self.assertEqual(len(methods), 19)
		self.assertEqual({item.code.value for item in methods}, set(EXPECTED))
		for item in methods:
			with self.subTest(method=item.code.value):
				self.assertEqual((item.fajr_angle, item.isha_angle, item.isha_interval_minutes,
					item.isha_ramadan_interval_minutes, item.maghrib_offset_minutes), EXPECTED[item.code.value])
				self.assertFalse(item.experimental)

	def test_country_auto_map_and_mwl_fallback_match_the_specification(self) -> None:
		expected = {
			"SA": "MAKKAH", "EG": "EGYPT", "PK": "KARACHI", "AF": "KARACHI",
			"BD": "KARACHI", "IN": "KARACHI", "US": "ISNA", "CA": "ISNA",
			"KW": "KUWAIT", "QA": "QATAR", "AE": "GULF", "BH": "GULF",
			"OM": "GULF", "YE": "GULF", "SG": "SINGAPORE", "MY": "JAKIM",
			"ID": "KEMENAG", "FR": "FRANCE", "RU": "RUSSIA", "TN": "TUNISIA",
			"DZ": "ALGERIA", "MA": "MOROCCO", "PT": "PORTUGAL", "JO": "JORDAN", "TR": "TURKEY",
		}
		resolver = self.repository.country_resolver
		for country, method in expected.items():
			self.assertEqual(resolver.resolve(country).value, method)
		self.assertEqual(resolver.resolve("GB"), CalculationMethod.MWL)

	def test_calculation_version_is_independent_and_consistent(self) -> None:
		self.assertEqual(self.repository.calculation_method_data_version, "awqati-4.0-methods-1")
		root = ROOT / "addon" / "globalPlugins" / "awqati" / "data"
		location = json.loads((root / "locations" / "metadata.json").read_text(encoding="utf-8"))
		timezones = json.loads((root / "timezones" / "metadata.json").read_text(encoding="utf-8"))
		self.assertNotEqual(self.repository.calculation_method_data_version, location["locationDataVersion"])
		self.assertNotEqual(self.repository.calculation_method_data_version, timezones["tzDataVersion"])

	def test_corrupt_relations_versions_and_duplicates_are_rejected(self) -> None:
		valid_methods = json.loads((ROOT / "addon/globalPlugins/awqati/data/calculation_methods/methods.json").read_text(encoding="utf-8"))
		valid_countries = json.loads((ROOT / "addon/globalPlugins/awqati/data/calculation_methods/country_methods.json").read_text(encoding="utf-8"))
		for mutation in ("unknown", "version", "duplicate"):
			with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
				root = Path(temporary)
				methods, countries = json.loads(json.dumps(valid_methods)), json.loads(json.dumps(valid_countries))
				if mutation == "unknown": countries["countries"]["SA"] = "AUTO"
				elif mutation == "version": countries["calculationMethodDataVersion"] = "other"
				else: methods["methods"].append(methods["methods"][0])
				(root / "methods.json").write_text(json.dumps(methods), encoding="utf-8")
				(root / "country_methods.json").write_text(json.dumps(countries), encoding="utf-8")
				with self.assertRaises(CalculationMethodDataError):
					_ = BundledCalculationMethodRepository(root).calculation_method_data_version


if __name__ == "__main__":
	unittest.main()
