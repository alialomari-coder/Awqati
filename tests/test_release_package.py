from __future__ import annotations

import ast
import hashlib
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]

from test_manifest_metadata_822 import (
    EXPECTED_DESCRIPTION_EN as EXPECTED_ENGLISH_DESCRIPTION,
    EXPECTED_DESCRIPTION_AR as EXPECTED_ARABIC_DESCRIPTION,
    EXPECTED_SUMMARY_EN, EXPECTED_SUMMARY_AR,
)


def _manifest_value(text: str, key: str) -> str:
	multiline = re.search(rf'(?ms)^{re.escape(key)}\s*=\s*"""(.*?)"""\s*$', text)
	if multiline:
		return multiline.group(1).replace("\r\n", "\n")
	line = re.search(rf'(?m)^{re.escape(key)}\s*=\s*(.*?)\s*$', text)
	if not line:
		raise AssertionError(f"Missing manifest field: {key}")
	return line.group(1).strip('"')


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
	def test_current_source_resources_are_preserved(self):
		package = ROOT / "dist" / f"awqati-{_addon_info()['addon_version']}.nvda-addon"
		with zipfile.ZipFile(package) as archive:
			self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
			for path in (ROOT / "addon").rglob("*"):
				if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo", ".mo"):
					name = path.relative_to(ROOT / "addon").as_posix()
					with self.subTest(resource=name):
						self.assertEqual(archive.read(name), path.read_bytes())

	def test_release_metadata_has_no_placeholders(self) -> None:
		info = _addon_info()
		expected = {
			"addon_name": "awqati",
			"addon_summary": "Awqati: prayer times, calendars, weather, astronomical information and time tools.",
			"addon_author": "ali alomari <alialomary@gmail.com>",
			"addon_url": "https://github.com/alialomari-coder/Awqati",
			"addon_sourceURL": "https://github.com/alialomari-coder/Awqati",
			"addon_docFileName": "readme.html",
			"addon_minimumNVDAVersion": "2026.1.0",
			"addon_lastTestedNVDAVersion": "2026.3.1",
			"addon_updateChannel": "stable",
			"addon_license": "GPL-2.0-or-later",
			"addon_licenseURL": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
		}
		for key, value in expected.items():
			with self.subTest(key=key):
				self.assertEqual(info[key], value)
		self.assertRegex(info["addon_version"], r"^\d+\.\d+\.\d+$")
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
		self.assertIn("changed its name from Prayer Times to Awqati", guide)
		for version in ("8.2.2", "8.2.1", "8.0.2", "8.0.0", "7.1.0", "7.0.0", "6.0.0", "5.0.0", "4.0.0"):
			with self.subTest(version=version):
				self.assertIn(f"Version {version}", guide)

	def test_package_metadata_and_name_match(self) -> None:
		info = _addon_info()
		package = ROOT / "dist" / f"awqati-{info['addon_version']}.nvda-addon"
		self.assertTrue(package.is_file(), "Build the package before running this test")
		with zipfile.ZipFile(package) as archive:
			manifest_text = archive.read("manifest.ini").decode("utf-8-sig")
		self.assertEqual(_manifest_value(manifest_text, "name"), info["addon_name"])
		self.assertEqual(_manifest_value(manifest_text, "version"), info["addon_version"])
		self.assertEqual(_manifest_value(manifest_text, "author"), info["addon_author"])
		self.assertEqual(_manifest_value(manifest_text, "url"), info["addon_url"])
		self.assertEqual(_manifest_value(manifest_text, "docFileName"), "readme.html")
		self.assertEqual(_manifest_value(manifest_text, "minimumNVDAVersion"), "2026.1.0")
		self.assertEqual(_manifest_value(manifest_text, "lastTestedNVDAVersion"), "2026.3.1")
		self.assertEqual(_manifest_value(manifest_text, "updateChannel"), "stable")

	def test_packaged_manifest_descriptions_preserve_approved_paragraphs(self) -> None:
		info = _addon_info()
		package = ROOT / "dist" / f"awqati-{info['addon_version']}.nvda-addon"
		with zipfile.ZipFile(package) as archive:
			english_manifest = archive.read("manifest.ini").decode("utf-8-sig")
			arabic_manifest = archive.read("locale/ar/manifest.ini").decode("utf-8-sig")
		self.assertEqual(_manifest_value(english_manifest, "summary"), EXPECTED_SUMMARY_EN)
		self.assertEqual(_manifest_value(arabic_manifest, "summary"), EXPECTED_SUMMARY_AR)
		self.assertEqual(_manifest_value(english_manifest, "description"), EXPECTED_ENGLISH_DESCRIPTION)
		self.assertEqual(_manifest_value(arabic_manifest, "description"), EXPECTED_ARABIC_DESCRIPTION)
		for description in (EXPECTED_ENGLISH_DESCRIPTION, EXPECTED_ARABIC_DESCRIPTION):
			self.assertEqual(description.count("\n\n"), 6)
			self.assertFalse(any(line.lstrip().startswith(("-", "*", "•")) for line in description.splitlines()))

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
			self.assertEqual(sounds, ["globalPlugins/awqati/sounds/alarms/alarm.wav", "globalPlugins/awqati/sounds/clock/clock.wav"] + [
				"globalPlugins/awqati/sounds/stopwatch/" + name + ".wav"
                for name in ("lap", "pause", "reset", "resume", "start")] + [
                    "globalPlugins/awqati/sounds/timers/" + name + ".wav"
                    for name in ("cancel", "finished", "pause", "restart", "resume", "start", "tick", "tock")])

	def test_full_official_license_is_present(self) -> None:
		license_text = (ROOT / "COPYING.txt").read_text(encoding="utf-8")
		self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
		self.assertIn("Version 2, June 1991", license_text)
		self.assertIn("END OF TERMS AND CONDITIONS", license_text)
		self.assertGreater(len(license_text), 17000)


if __name__ == "__main__":
	unittest.main()
