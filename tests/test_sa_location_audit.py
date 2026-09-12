from __future__ import annotations

import gzip
import json
from pathlib import Path
import unittest

from tools import audit_sa_locations


ROOT = Path(__file__).resolve().parents[1]
SA_DATA = ROOT / "addon" / "globalPlugins" / "awqati" / "data" / "locations" / "countries" / "SA.json.gz"
SUPPLEMENT = ROOT / "data_sources" / "sa_locations_supplement.v1.json"


class SaudiLocationAuditTests(unittest.TestCase):
	def test_final_saudi_data_has_no_confirmed_duplicate_and_documents_candidates(self) -> None:
		result = audit_sa_locations.audit(SA_DATA, SUPPLEMENT)
		self.assertEqual(result["recordCount"], 183)
		self.assertEqual(result["confirmedDuplicateCount"], 0)
		self.assertEqual(result["potentialDuplicateCount"], 1)
		self.assertEqual(result["reviewedLegitimateSimilarityCount"], 1)
		potential_ids = {record["geonameId"] for record in result["potentialDuplicates"][0]["records"]}
		self.assertEqual(potential_ids, {"110059", "110060"})
		legitimate_ids = {record["geonameId"] for record in result["reviewedLegitimateSimilarities"][0]["records"]}
		self.assertEqual(legitimate_ids, {"109435", "109436"})

	def test_saudi_counts_arabic_coverage_regions_and_capitals(self) -> None:
		records = json.loads(gzip.decompress(SA_DATA.read_bytes()))["cities"]
		self.assertEqual(len({record["i"] for record in records}), len(records))
		self.assertEqual([(record["i"], record["n"]) for record in records if not record["a"]], [
			("9031043", "Alrmtheiah"),
		])
		expected_regions = {
			"Riyadh Region", "Mecca Region", "Medina Region", "Al-Qassim Region",
			"Eastern Province", "'Asir Region", "Tabuk Region", "Ha'il Region",
			"Northern Borders Region", "Jazan Region", "Najran Region",
			"Al Bahah Region", "Al Jawf Region",
		}
		self.assertTrue(expected_regions <= {record["a1"] for record in records})
		capital_ids = {
			"108410", "104515", "109223", "102651", "110336", "110690", "101628",
			"106281", "102527", "108512", "109953", "105299", "103630",
		}
		self.assertEqual(capital_ids, {record["i"] for record in records if record["i"] in capital_ids})

	def test_versioned_supplement_has_valid_sources_and_expected_operations(self) -> None:
		payload = json.loads(SUPPLEMENT.read_text(encoding="utf-8"))
		metadata_path = SA_DATA.parent.parent / "metadata.json"
		metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
		self.assertEqual(
			metadata["locationDataVersion"],
			"geonames-cities500-2026-09-11+sa-2026-09-12.1+spatial-1",
		)
		self.assertEqual(
			metadata["saudiSupplement"]["sha256"],
			__import__("hashlib").sha256(SUPPLEMENT.read_bytes()).hexdigest(),
		)
		self.assertEqual(
			(metadata["saudiSupplement"]["added"], metadata["saudiSupplement"]["augmented"], metadata["saudiSupplement"]["merged"]),
			(25, 45, 3),
		)
		source_ids = {source["id"] for source in payload["sources"]}
		self.assertEqual((len(payload["additions"]), len(payload["aliases"]), len(payload["merges"])), (25, 45, 3))
		for section in ("additions", "aliases", "merges", "reviewedSimilarities"):
			for item in payload[section]:
				self.assertTrue(item["sourceRefs"])
				self.assertTrue(set(item["sourceRefs"]) <= source_ids)


if __name__ == "__main__":
	unittest.main()
