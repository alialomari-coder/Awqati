from __future__ import annotations

import ast
import configparser
from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dist" / "awqati-0.0.0.nvda-addon"


def _load_addon_info() -> dict[str, object]:
	tree = ast.parse((ROOT / "buildVars.py").read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == "addon_info" for target in node.targets
		):
			return ast.literal_eval(node.value)
	raise AssertionError("addon_info was not found in buildVars.py")


class ScaffoldTests(unittest.TestCase):
	def test_required_source_files_exist(self) -> None:
		for relative_path in (
			"buildVars.py",
			"manifest.ini.tpl",
			"sconstruct",
			"addon/globalPlugins/awqati/__init__.py",
		):
			with self.subTest(path=relative_path):
				self.assertTrue((ROOT / relative_path).is_file())

	def test_internal_name_is_awqati(self) -> None:
		self.assertEqual(_load_addon_info()["addon_name"], "awqati")

	def test_package_is_only_in_dist(self) -> None:
		self.assertTrue(PACKAGE.is_file(), "Build the package before running this test")
		self.assertEqual(list(ROOT.glob("*.nvda-addon")), [])

	def test_built_package_has_minimum_layout(self) -> None:
		self.assertTrue(PACKAGE.is_file(), "Build the package before running this test")
		with zipfile.ZipFile(PACKAGE) as archive:
			names = set(archive.namelist())
			self.assertIsNone(archive.testzip())
			self.assertIn("manifest.ini", names)
			self.assertIn("globalPlugins/awqati/__init__.py", names)
			for relative_path in (
				"globalPlugins/awqati/domain/models.py",
				"globalPlugins/awqati/application/ports.py",
				"globalPlugins/awqati/infrastructure/system_time.py",
				"globalPlugins/awqati/nvda_adapter/plugin.py",
			):
				with self.subTest(path=relative_path):
					self.assertIn(relative_path, names)
			self.assertFalse(any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in names))

	def test_built_manifest_matches_scaffold_metadata(self) -> None:
		with zipfile.ZipFile(PACKAGE) as archive:
			manifest_text = archive.read("manifest.ini").decode("utf-8-sig")
		parser = configparser.ConfigParser()
		parser.read_string("[manifest]\n" + manifest_text)
		manifest = parser["manifest"]
		self.assertEqual(manifest["name"], "awqati")
		self.assertEqual(manifest["version"], "0.0.0")
		self.assertEqual(manifest["minimumNVDAVersion"], "2026.1.0")
		self.assertEqual(manifest["lastTestedNVDAVersion"], "2026.2.0")


if __name__ == "__main__":
	unittest.main()
