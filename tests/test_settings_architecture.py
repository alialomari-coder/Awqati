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


class SettingsArchitectureTests(unittest.TestCase):
	def test_schema_is_language_neutral_except_the_user_editable_wird_default(self) -> None:
		source = (CORE / "domain" / "settings.py").read_text(encoding="utf-8")
		tree = ast.parse(source)
		arabic_strings = [
			node.value for node in ast.walk(tree)
			if isinstance(node, ast.Constant) and isinstance(node.value, str)
			and any("\u0600" <= character <= "\u06ff" for character in node.value)
		]
		self.assertEqual(arabic_strings, ["لا تنس وردك اليومي."])
		for forbidden in ("config", "wx", "globalPluginHandler", "pathlib", "os"):
			self.assertNotIn(forbidden, {alias.name for node in ast.walk(tree)
				if isinstance(node, ast.Import) for alias in node.names})

	def test_application_and_domain_import_without_nvda_config_wx_or_filesystem(self) -> None:
		script = """
from datetime import datetime, timezone
import sys
from awqati.application import EventDispatcher, SettingsDraft, SettingsRepository, SettingsService
from awqati.domain import *
settings = default_settings()
validate_settings(settings)
draft = SettingsDraft(settings)
draft.settings.adhkar.recurring.items[RecurringDhikrId.SUBHAN_ALLAH].enabled = False
assert settings.adhkar.recurring.items[RecurringDhikrId.SUBHAN_ALLAH].enabled
event = SystemTimeChanged(Instant(datetime(2026, 1, 1, tzinfo=timezone.utc)))
assert event.occurred_at.value.year == 2026
assert all(name not in sys.modules for name in ('globalPluginHandler', 'wx', 'config'))
"""
		environment = os.environ.copy()
		environment["PYTHONPATH"] = str(PACKAGES)
		with tempfile.TemporaryDirectory() as working:
			result = subprocess.run([sys.executable, "-S", "-c", script], cwd=working,
				env=environment, capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_settings_repository_is_in_infrastructure_and_package(self) -> None:
		sources = (
			CORE / "domain" / "settings.py",
			CORE / "application" / "settings_service.py",
			CORE / "infrastructure" / "settings_repository.py",
		)
		self.assertTrue(all(path.is_file() for path in sources))
		if PACKAGE.is_file() and PACKAGE.stat().st_mtime >= max(path.stat().st_mtime for path in sources):
			with zipfile.ZipFile(PACKAGE) as archive:
				for name in (
					"globalPlugins/awqati/domain/settings.py",
					"globalPlugins/awqati/application/settings_service.py",
					"globalPlugins/awqati/infrastructure/settings_repository.py",
				):
					self.assertIn(name, archive.namelist())

	def test_no_old_addon_migration_names_or_nvda_config_import(self) -> None:
		source = (CORE / "infrastructure" / "settings_repository.py").read_text(encoding="utf-8")
		tree = ast.parse(source)
		imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
		self.assertNotIn("config", imports)
		self.assertNotIn("globalPluginHandler", imports)
		self.assertNotIn('"schemaVersion": 0', source)


if __name__ == "__main__":
	unittest.main()
