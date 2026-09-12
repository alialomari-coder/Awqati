from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "addon" / "globalPlugins" / "awqati" / "data" / "calendars" / "ummalqura"


def _load_builder():
	spec = importlib.util.spec_from_file_location("build_ummalqura", ROOT / "tools" / "build_ummalqura.py")
	assert spec and spec.loader
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


class CalendarDataTests(unittest.TestCase):
	def test_runtime_table_metadata_digest_range_and_license(self) -> None:
		metadata = json.loads((DATA / "metadata.json").read_text(encoding="utf-8"))
		table_bytes = (DATA / metadata["tableFile"]).read_bytes()
		table = json.loads(table_bytes.decode("utf-8"))
		self.assertEqual(hashlib.sha256(table_bytes).hexdigest(), metadata["tableFileSha256"])
		self.assertEqual(metadata["source"]["sha256"],
			"a665b4eed397fc890786a27d27e80c754f71620101d79bc6a2b1bfa7d00bb6cb")
		self.assertEqual((table["firstHijriYear"], table["lastHijriYear"]), (1300, 1600))
		self.assertEqual(len(table["monthLengthMasks"]), 301)
		self.assertEqual(metadata["hijriDataVersion"],
			"icu-78.3-islamic-umalqura-1300-1600")
		self.assertTrue((DATA / "LICENSE-Unicode-3.0.txt").is_file())
		self.assertTrue((DATA / "NOTICE.txt").is_file())

	def test_builder_extracts_exactly_one_mask_per_year(self) -> None:
		builder = _load_builder()
		values = ", ".join(f"0x{index % 4096:03X}" for index in range(301))
		source = f"static const int UMALQURA_MONTHLENGTH[] = {{\n{values}\n}};"
		self.assertEqual(builder.parse_month_masks(source), [index % 4096 for index in range(301)])
		with self.assertRaises(ValueError):
			builder.parse_month_masks("static const int UMALQURA_MONTHLENGTH[] = { 0xAAA\n};")

	def test_corrupt_table_is_rejected_before_conversion(self) -> None:
		import sys
		packages = ROOT / "addon" / "globalPlugins"
		if str(packages) not in sys.path:
			sys.path.insert(0, str(packages))
		from awqati.infrastructure import UmmAlQuraDataError, UmmAlQuraProvider
		with tempfile.TemporaryDirectory() as temporary:
			copy = Path(temporary)
			for source in DATA.iterdir():
				shutil.copy2(source, copy / source.name)
			(copy / "month_lengths.json").write_text("{}", encoding="utf-8")
			with self.assertRaises(UmmAlQuraDataError):
				UmmAlQuraProvider(copy)


if __name__ == "__main__":
	unittest.main()
