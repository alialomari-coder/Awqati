from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
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


class Task32ArchitectureTests(unittest.TestCase):
	def test_application_policy_and_setup_have_no_wx_nvda_network_or_filesystem(self) -> None:
		for relative in ("application/general_policy.py", "application/location_setup.py"):
			source = (CORE / relative).read_text(encoding="utf-8")
			tree = ast.parse(source)
			imports = {alias.name.split(".")[0] for node in ast.walk(tree)
				if isinstance(node, ast.Import) for alias in node.names}
			self.assertTrue(imports.isdisjoint({"wx", "gui", "globalPluginHandler", "socket", "urllib", "requests", "pathlib", "os"}))

	def test_ui_worker_and_gui_handoff_are_explicit_and_no_network_exists(self) -> None:
		source = (CORE / "nvda_adapter" / "ui.py").read_text(encoding="utf-8")
		self.assertIn("threading.Thread", source)
		self.assertIn("wx.CallAfter", source)
		self.assertNotIn("self.service.detect()", source.split("def _on_detect", 1)[0])
		for forbidden in ("http://", "https://", "requests", "urllib", "socket", "reverse_geocod"):
			self.assertNotIn(forbidden, source.casefold())
		self.assertNotIn("PrayerSettingsPanel", source)
		self.assertNotIn("Scheduler", source)

	def test_plain_core_import_does_not_open_ui_or_import_nvda(self) -> None:
		script = """
import sys
import awqati
from awqati.application import first_run_location_required
from awqati.domain import default_settings
assert first_run_location_required(default_settings())
assert 'wx' not in sys.modules
assert 'globalPluginHandler' not in sys.modules
"""
		environment = {"PYTHONPATH": str(PACKAGES)}
		with tempfile.TemporaryDirectory() as working:
			result = subprocess.run([sys.executable, "-S", "-c", script], cwd=working,
				env=environment, capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_package_contains_task32_modules(self) -> None:
		if PACKAGE.is_file() and PACKAGE.stat().st_mtime >= max((CORE / name).stat().st_mtime for name in ('application/general_policy.py', 'application/location_setup.py', 'nvda_adapter/ui.py')):
			with zipfile.ZipFile(PACKAGE) as archive:
				for name in (
					"globalPlugins/awqati/application/general_policy.py",
					"globalPlugins/awqati/application/location_setup.py",
					"globalPlugins/awqati/nvda_adapter/ui.py",
				):
					self.assertIn(name, archive.namelist())


if __name__ == "__main__":
	unittest.main()
