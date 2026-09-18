from __future__ import annotations

import ast
import configparser
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _addon_info() -> dict[str, object]:
	tree = ast.parse((ROOT / "buildVars.py").read_text(encoding="utf-8"))
	assignment = next(
		node for node in tree.body
		if isinstance(node, ast.Assign)
		and any(isinstance(target, ast.Name) and target.id == "addon_info" for target in node.targets)
	)
	return ast.literal_eval(assignment.value)


def _content_lines(text: str) -> list[str]:
	result: list[str] = []
	for raw_line in text.replace("\r\n", "\n").splitlines():
		line = raw_line.strip()
		if not line:
			continue
		line = re.sub(r"^#{1,6}\s+", "", line)
		line = re.sub(r"^(?:-|•)\s*", "", line)
		result.append(line)
	return result


class _GuideHtmlParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__()
		self.html_attributes: dict[str, str | None] = {}
		self.headings: list[str] = []

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		if tag == "html":
			self.html_attributes = dict(attrs)
		if re.fullmatch(r"h[1-6]", tag):
			self.headings.append(tag)


class ReleaseMetadataTests(unittest.TestCase):
	def test_release_metadata_has_no_placeholders(self) -> None:
		info = _addon_info()
		expected = {
			"addon_name": "awqati",
			"addon_summary": "Awqati",
			"addon_author": "ali alomari <alialomary@gmail.com>",
			"addon_url": "https://github.com/alialomari-coder/Awqati",
			"addon_sourceURL": "https://github.com/alialomari-coder/Awqati",
			"addon_docFileName": "readme.html",
			"addon_minimumNVDAVersion": "2026.1.0",
			"addon_lastTestedNVDAVersion": "2026.2.0",
			"addon_updateChannel": None,
			"addon_license": "GPL-2.0-or-later",
			"addon_licenseURL": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
		}
		for key, value in expected.items():
			with self.subTest(key=key):
				self.assertEqual(info[key], value)
		self.assertEqual(info["addon_version"], "4.0.0")
		serialized = repr(info).lower()
		self.assertNotIn("placeholder", serialized)
		self.assertNotIn("undecided", serialized)

	def test_owner_approved_arabic_content_is_preserved(self) -> None:
		source = (ROOT / "docs/دليل_أوقاتي_العربي_المعتمد.md").read_text(encoding="utf-8-sig")
		packaged = (ROOT / "addon/doc/ar/readme.md").read_text(encoding="utf-8")
		self.assertEqual(_content_lines(packaged), _content_lines(source))

	def test_only_arabic_and_english_guides_are_declared(self) -> None:
		for language, direction in (("ar", "rtl"), ("en", "ltr")):
			folder = ROOT / "addon/doc" / language
			markdown = folder / "readme.md"
			html = folder / "readme.html"
			self.assertTrue(markdown.is_file())
			self.assertTrue(html.is_file())
			self.assertNotRegex(markdown.read_text(encoding="utf-8"), r"\b0\.5\.\d+")
			parser = _GuideHtmlParser()
			parser.feed(html.read_text(encoding="utf-8"))
			self.assertEqual(parser.html_attributes.get("lang"), language)
			self.assertEqual(parser.html_attributes.get("dir"), direction)
			self.assertIn("h1", parser.headings)
			self.assertIn("h2", parser.headings)
		self.assertEqual(
			{path.name for path in (ROOT / "addon/doc").iterdir() if path.is_dir()},
			{"ar", "en"},
		)
		locale_languages = {
			path.parent.parent.name
			for path in (ROOT / "addon/locale").glob("*/LC_MESSAGES/nvda.po")
		}
		self.assertEqual(locale_languages, {"ar"})

	def test_english_guide_contains_the_complete_release_history(self) -> None:
		guide = (ROOT / "addon/doc/en/readme.md").read_text(encoding="utf-8")
		self.assertIn("formerly known as Prayer Times", guide)
		for version in ("4.0.0", "3.2", "3.1", "3.0", "2.1", "1.3"):
			with self.subTest(version=version):
				self.assertIn(f"Version {version}", guide)

	def test_package_metadata_and_name_match(self) -> None:
		info = _addon_info()
		package = ROOT / "dist" / f"awqati-{info['addon_version']}.nvda-addon"
		self.assertTrue(package.is_file(), "Build the package before running this test")
		with zipfile.ZipFile(package) as archive:
			manifest_text = archive.read("manifest.ini").decode("utf-8-sig")
			parser = configparser.ConfigParser()
			parser.read_string("[manifest]\n" + manifest_text)
			manifest = parser["manifest"]
			self.assertEqual(manifest["name"], info["addon_name"])
			self.assertEqual(manifest["version"], info["addon_version"])
			self.assertEqual(manifest["author"].strip('"'), info["addon_author"])
			self.assertEqual(manifest["url"], info["addon_url"])
			self.assertEqual(manifest["docfilename"], "readme.html")
			self.assertEqual(manifest["minimumnvdaversion"], "2026.1.0")
			self.assertEqual(manifest["lasttestednvdaversion"], "2026.2.0")
			self.assertEqual(manifest["updatechannel"], "")

	def test_package_is_release_clean(self) -> None:
		info = _addon_info()
		package = ROOT / "dist" / f"awqati-{info['addon_version']}.nvda-addon"
		with zipfile.ZipFile(package) as archive:
			names = archive.namelist()
			self.assertIsNone(archive.testzip())
			for required in (
				"COPYING.txt",
				"DATA_SOURCES.md",
				"doc/ar/readme.md",
				"doc/ar/readme.html",
				"doc/en/readme.md",
				"doc/en/readme.html",
				"globalPlugins/awqati/sounds/clock/clock.wav",
			):
				self.assertIn(required, names)
			for name in names:
				parts = {part.lower() for part in PurePosixPath(name).parts}
				self.assertFalse(parts & {".git", "tests", "build", "dist", "__pycache__", "logs", "harness", "scratchpad"}, name)
				self.assertFalse(name.lower().endswith((".pyc", ".pyo", ".log", ".ini.bak")), name)
			sounds = [name for name in names if name.lower().endswith((".wav", ".mp3", ".ogg"))]
			self.assertEqual(sounds, ["globalPlugins/awqati/sounds/clock/clock.wav"])

	def test_full_official_license_is_present(self) -> None:
		license_text = (ROOT / "COPYING.txt").read_text(encoding="utf-8")
		self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
		self.assertIn("Version 2, June 1991", license_text)
		self.assertIn("END OF TERMS AND CONDITIONS", license_text)
		self.assertGreater(len(license_text), 17000)


if __name__ == "__main__":
	unittest.main()
