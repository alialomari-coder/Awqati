from __future__ import annotations

import ast
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
CORE = PACKAGES / "awqati"
import runpy
BUILD_INFO = runpy.run_path(str(ROOT / "buildVars.py"))["addon_info"]
PACKAGE = ROOT / "dist" / f"awqati-{BUILD_INFO['addon_version']}.nvda-addon"


class CalendarArchitectureTests(unittest.TestCase):
	def test_domain_algorithms_are_language_neutral_and_prayer_engine_is_calendar_neutral(self) -> None:
		calendar_source = (CORE / "domain" / "calendar.py").read_text(encoding="utf-8")
		prayer_source = (CORE / "domain" / "prayer.py").read_text(encoding="utf-8")
		self.assertFalse(any("\u0600" <= character <= "\u06ff" for character in calendar_source))
		calendar_tree = ast.parse(calendar_source)
		assigned_names = {target.id for node in ast.walk(calendar_tree)
			if isinstance(node, (ast.Assign, ast.AnnAssign))
			for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
			if isinstance(target, ast.Name)}
		self.assertTrue({"language", "locale", "month_names", "weekday_names"}.isdisjoint(assigned_names))
		self.assertNotIn("calendar", {alias.name for node in ast.walk(ast.parse(prayer_source))
			if isinstance(node, ast.Import) for alias in node.names})
		self.assertNotIn("UmmAlQura", prayer_source)
		self.assertNotIn("CalendarService", prayer_source)

	def test_persian_and_afghan_do_not_import_or_call_each_other(self) -> None:
		tree = ast.parse((CORE / "domain" / "calendar.py").read_text(encoding="utf-8"))
		classes = {node.name: ast.unparse(node) for node in tree.body if isinstance(node, ast.ClassDef)}
		self.assertNotIn("AfghanSolarHijriProvider", classes["PersianSolarHijriProvider"])
		self.assertNotIn("PersianSolarHijriProvider", classes["AfghanSolarHijriProvider"])

	def test_calendar_core_imports_and_runs_in_standalone_python_without_nvda_or_network(self) -> None:
		script = """
from datetime import date, datetime, timezone
import sys
from awqati.application import ArabicDateFormatter, CalendarProvider, CalendarService, EnglishDateFormatter
from awqati.domain import *
from awqati.infrastructure import UmmAlQuraProvider
providers = [GregorianProvider(), UmmAlQuraProvider(), SaudiSolarHijriProvider(), PersianSolarHijriProvider(), AfghanSolarHijriProvider()]
assert all(isinstance(provider, CalendarProvider) for provider in providers)
assert UmmAlQuraProvider().from_gregorian(date(2026, 9, 12)).month == 4
assert PersianSolarHijriProvider().from_gregorian(date(2029, 3, 20)).day == 1
assert AfghanSolarHijriProvider().from_gregorian(date(2029, 3, 20)).day == 30
assert ArabicDateFormatter().language == 'ar' and EnglishDateFormatter().language == 'en'
assert 'globalPluginHandler' not in sys.modules and 'wx' not in sys.modules and 'socket' not in sys.modules
"""
		environment = os.environ.copy()
		environment["PYTHONPATH"] = str(PACKAGES)
		with tempfile.TemporaryDirectory() as working:
			result = subprocess.run([sys.executable, "-S", "-c", script], cwd=working,
				env=environment, capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_package_contains_calendar_code_runtime_data_and_license_only(self) -> None:
		with zipfile.ZipFile(PACKAGE) as archive:
			names = set(archive.namelist())
			for name in (
				"globalPlugins/awqati/domain/calendar.py",
				"globalPlugins/awqati/application/calendar_service.py",
				"globalPlugins/awqati/application/calendar_formatters.py",
				"globalPlugins/awqati/infrastructure/ummalqura_provider.py",
				"globalPlugins/awqati/data/calendars/ummalqura/month_lengths.json",
				"globalPlugins/awqati/data/calendars/ummalqura/metadata.json",
				"globalPlugins/awqati/data/calendars/ummalqura/NOTICE.txt",
				"globalPlugins/awqati/data/calendars/ummalqura/LICENSE-Unicode-3.0.txt",
			):
				self.assertIn(name, names)
			self.assertFalse(any("islamcal" in name or "persncal" in name for name in names))


if __name__ == "__main__":
	unittest.main()
