"""Build the bundled Umm al-Qura month table from a pinned ICU source file."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


SOURCE_URL = "https://raw.githubusercontent.com/unicode-org/icu/release-78.3/icu4c/source/i18n/islamcal.cpp"
SOURCE_SHA256 = "a665b4eed397fc890786a27d27e80c754f71620101d79bc6a2b1bfa7d00bb6cb"
HIJRI_DATA_VERSION = "icu-78.3-islamic-umalqura-1300-1600"
FIRST_YEAR = 1300
LAST_YEAR = 1600
FIRST_GREGORIAN_DATE = "1882-11-12"


def _sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def parse_month_masks(source: str) -> list[int]:
	"""Extract ICU's 12-bit month-length masks and reject a changed source shape."""
	match = re.search(
		r"UMALQURA_MONTHLENGTH\[\]\s*=\s*\{(?P<body>.*?)\n\};",
		source,
		flags=re.DOTALL,
	)
	if match is None:
		raise ValueError("UMALQURA_MONTHLENGTH table was not found")
	masks = [int(value, 16) for value in re.findall(r"0x[0-9A-Fa-f]+", match.group("body"))]
	if len(masks) != LAST_YEAR - FIRST_YEAR + 1:
		raise ValueError(f"expected 301 year masks, found {len(masks)}")
	if any(mask < 0 or mask > 0xFFF for mask in masks):
		raise ValueError("month-length mask exceeds twelve bits")
	return masks


def build(source_path: Path, output_directory: Path, generated_at: str) -> tuple[Path, Path]:
	source_bytes = source_path.read_bytes()
	if _sha256(source_bytes) != SOURCE_SHA256:
		raise ValueError("ICU source SHA-256 does not match the pinned release-78.3 artifact")
	masks = parse_month_masks(source_bytes.decode("utf-8"))
	output_directory.mkdir(parents=True, exist_ok=True)
	table_path = output_directory / "month_lengths.json"
	table_document = {
		"schemaVersion": 1,
		"hijriDataVersion": HIJRI_DATA_VERSION,
		"firstHijriYear": FIRST_YEAR,
		"lastHijriYear": LAST_YEAR,
		"firstGregorianDate": FIRST_GREGORIAN_DATE,
		"monthLengthMasks": masks,
	}
	table_bytes = (json.dumps(table_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
	table_path.write_bytes(table_bytes)
	metadata_path = output_directory / "metadata.json"
	metadata = {
		"schemaVersion": 1,
		"hijriDataVersion": HIJRI_DATA_VERSION,
		"calendarId": "HIJRI_UMM_AL_QURA",
		"firstHijriYear": FIRST_YEAR,
		"lastHijriYear": LAST_YEAR,
		"firstGregorianDate": FIRST_GREGORIAN_DATE,
		"source": {
			"project": "Unicode ICU",
			"release": "78.3",
			"tag": "release-78.3",
			"file": "icu4c/source/i18n/islamcal.cpp",
			"url": SOURCE_URL,
			"sha256": SOURCE_SHA256,
		},
		"derivation": "The 301 hexadecimal UMALQURA_MONTHLENGTH masks are extracted unchanged; bit 11 is Muharram and a set bit means 30 days.",
		"tableFile": table_path.name,
		"tableFileSha256": _sha256(table_bytes),
		"generatedAt": generated_at,
		"license": "Unicode-3.0",
	}
	metadata_path.write_text(
		json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
		encoding="utf-8",
		newline="\n",
	)
	return table_path, metadata_path


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--icu-source", required=True, type=Path)
	parser.add_argument("--output", required=True, type=Path)
	parser.add_argument("--generated-at", required=True)
	arguments = parser.parse_args()
	build(arguments.icu_source, arguments.output, arguments.generated_at)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
