from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.infrastructure import ArabianCalendarDataError, BundledArabianCalendarRepository  # noqa: E402


RUNTIME = ROOT / "addon" / "globalPlugins" / "awqati" / "data" / "arabian_calendar"


def copy_runtime(destination: Path) -> None:
	for source in RUNTIME.iterdir():
		shutil.copy2(source, destination / source.name)


def replace_json(directory: Path, name: str, transform) -> None:
	path = directory / name
	value = json.loads(path.read_text(encoding="utf-8"))
	transform(value)
	payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
	path.write_bytes(payload)
	metadata_path = directory / "metadata.json"
	metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
	metadata["files"][name]["sizeBytes"] = len(payload)
	metadata["files"][name]["sha256"] = hashlib.sha256(payload).hexdigest()
	metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ArabianCalendarFailureTests(unittest.TestCase):
	def test_missing_runtime_file_is_typed(self) -> None:
		with tempfile.TemporaryDirectory() as temporary:
			path = Path(temporary)
			copy_runtime(path)
			(path / "arabian_calendar.json").unlink()
			with self.assertRaisesRegex(ArabianCalendarDataError, "unavailable"):
				BundledArabianCalendarRepository(path).read(date(2024, 2, 27))

	def test_invalid_json_is_typed(self) -> None:
		with tempfile.TemporaryDirectory() as temporary:
			path = Path(temporary)
			copy_runtime(path)
			(path / "metadata.json").write_text("{", encoding="utf-8")
			with self.assertRaisesRegex(ArabianCalendarDataError, "invalid JSON"):
				BundledArabianCalendarRepository(path).read(date(2024, 2, 27))

	def test_unsupported_schema_and_data_versions_are_typed(self) -> None:
		for field, value, message in (
			("schemaVersion", 2, "schemaVersion"),
			("arabianCalendarDataVersion", "future", "arabianCalendarDataVersion"),
		):
			with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
				path = Path(temporary)
				copy_runtime(path)
				metadata_path = path / "metadata.json"
				metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
				metadata[field] = value
				metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
				with self.assertRaisesRegex(ArabianCalendarDataError, message):
					BundledArabianCalendarRepository(path).read(date(2024, 2, 27))

	def test_unknown_entity_reference_is_typed(self) -> None:
		with tempfile.TemporaryDirectory() as temporary:
			path = Path(temporary)
			copy_runtime(path)
			replace_json(path, "arabian_calendar.json", lambda value: value["talaa"][0].update(seasonId="missing"))
			with self.assertRaisesRegex(ArabianCalendarDataError, "unknown entity reference"):
				BundledArabianCalendarRepository(path).read(date(2024, 2, 27))

	def test_missing_or_duplicate_daily_index_record_is_typed(self) -> None:
		def remove_record(value):
			value["daysByDate"].pop(value["orderedDateKeys"][-1])

		def duplicate_record(value):
			value["orderedDateKeys"][-1] = value["orderedDateKeys"][-2]

		for transform in (remove_record, duplicate_record):
			with self.subTest(transform=transform.__name__), tempfile.TemporaryDirectory() as temporary:
				path = Path(temporary)
				copy_runtime(path)
				replace_json(path, "arabian_calendar_days_common.json", transform)
				with self.assertRaises(ArabianCalendarDataError):
					BundledArabianCalendarRepository(path).read(date(2025, 2, 27))


if __name__ == "__main__":
	unittest.main()
