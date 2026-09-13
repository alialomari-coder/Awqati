from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
CORE = PACKAGES / "awqati"
PACKAGE = ROOT / "dist" / "awqati-0.0.0.nvda-addon"


class ArabianCalendarArchitectureTests(unittest.TestCase):
	def test_domain_and_application_have_no_forbidden_io_or_platform_imports(self) -> None:
		for layer, forbidden in (
			("domain", {"json", "os", "pathlib", "socket", "urllib", "wx", "globalPluginHandler", "config"}),
			("application", {"json", "os", "pathlib", "socket", "urllib", "wx", "globalPluginHandler", "config"}),
		):
			for path in (CORE / layer).glob("*arabian_calendar*.py"):
				tree = ast.parse(path.read_text(encoding="utf-8"))
				imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
				imports |= {(node.module or "").split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0}
				self.assertTrue(imports.isdisjoint(forbidden), (path, imports & forbidden))

	def test_standalone_import_and_read_do_not_load_nvda_or_wx(self) -> None:
		script = """
from datetime import date
import sys
from awqati.application import ArabianCalendarRepository, ArabianCalendarService, ArabicArabianCalendarFormatter, DailyInfoService
from awqati.infrastructure import BundledArabianCalendarRepository
repository = BundledArabianCalendarRepository()
assert isinstance(repository, ArabianCalendarRepository)
reading = ArabianCalendarService(repository).read_date(date(2024, 2, 27))
assert reading.suhail_day == 188 and reading.talaa.id == 'saad_bula'
assert 'سنة سهيل' in ArabicArabianCalendarFormatter().format_short(reading)
assert DailyInfoService is not None
assert 'globalPluginHandler' not in sys.modules and 'wx' not in sys.modules
"""
		environment = os.environ.copy()
		environment["PYTHONPATH"] = str(PACKAGES)
		with tempfile.TemporaryDirectory() as working:
			result = subprocess.run([sys.executable, "-S", "-c", script], cwd=working, env=environment,
				capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_package_contains_runtime_data_not_research_sources(self) -> None:
		with zipfile.ZipFile(PACKAGE) as archive:
			names = set(archive.namelist())
			for name in (
				"globalPlugins/awqati/data/arabian_calendar/metadata.json",
				"globalPlugins/awqati/data/arabian_calendar/arabian_calendar.json",
				"globalPlugins/awqati/data/arabian_calendar/arabian_calendar_days_common.json",
				"globalPlugins/awqati/data/arabian_calendar/arabian_calendar_days_leap.json",
			):
				self.assertIn(name, names)
			self.assertFalse(any("data_sources" in name or name.endswith(".zip") for name in names))


if __name__ == "__main__":
	unittest.main()
