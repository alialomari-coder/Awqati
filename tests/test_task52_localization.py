"""Acceptance contracts for task 5.2 bilingual localization."""

from __future__ import annotations

import ast
from html.parser import HTMLParser
import io
import gettext
from pathlib import Path
import sys
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "addon/globalPlugins/awqati"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))

import buildVars
from tools.build_translations import extract_catalog
from awqati.application.islamic_terms import (
	GLOSSARY_IDENTITIES,
	TermKind,
	normalize_language,
	source_message,
	term_kind,
	term_text,
)
from awqati.application.general_policy import LOCATION_REQUIRED_MESSAGE
from awqati.domain.settings import DEFAULT_DAILY_WIRD_TEXT
from awqati.nvda_adapter.settings_sections import is_rtl_language, supported_language


class _DocumentOutline(HTMLParser):
	def __init__(self):
		super().__init__()
		self.headings = []
		self._heading = None

	def handle_starttag(self, tag, attrs):
		if tag in {"h1", "h2", "h3"}:
			self._heading = []

	def handle_data(self, data):
		if self._heading is not None:
			self._heading.append(data)

	def handle_endtag(self, tag):
		if tag in {"h1", "h2", "h3"} and self._heading is not None:
			self.headings.append("".join(self._heading).strip())
			self._heading = None


class DomainNeutralityTests(unittest.TestCase):
	def test_domain_has_no_arabic_logical_string_literals(self):
		for path in (CORE / "domain").glob("*.py"):
			tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
			arabic = [node.value for node in ast.walk(tree)
				if isinstance(node, ast.Constant) and isinstance(node.value, str)
				and any("\u0600" <= char <= "\u06ff" for char in node.value)]
			self.assertEqual(arabic, [], path.name)

	def test_default_wird_is_an_english_source_msgid_not_arabic_identity(self):
		self.assertEqual(DEFAULT_DAILY_WIRD_TEXT, "Do not forget your daily Wird.")
		self.assertFalse(any("\u0600" <= char <= "\u06ff" for char in DEFAULT_DAILY_WIRD_TEXT))


class IslamicGlossaryTests(unittest.TestCase):
	def test_glossary_has_all_categories_and_stable_prayer_spellings(self):
		self.assertEqual({term_kind(identity) for identity in GLOSSARY_IDENTITIES}, set(TermKind))
		self.assertEqual([term_text(name, "en") for name in
			("fajr", "dhuhr", "asr", "maghrib", "isha")],
			["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"])

	def test_devotional_english_is_transliterated_and_reminders_are_semantic(self):
		self.assertEqual(term_text("subhanAllah", "en"), "Subhan Allah.")
		self.assertEqual(term_text("laHawlaWaLaQuwwata", "en"),
			"La hawla wa la quwwata illa billah.")
		self.assertEqual(term_text("udhkurAllah", "en"),
			"Remember Allah, and He will remember you.")
		self.assertIs(term_kind("subhanAllah"), TermKind.DEVOTIONAL)
		self.assertIs(term_kind("udhkurAllah"), TermKind.REMINDER)
		self.assertIs(term_kind("salatAlaAlNabi"), TermKind.FEATURE)

	def test_astronomical_terms_translate_fully_and_unknown_locale_falls_back(self):
		self.assertEqual(term_text("sunrise", "ar_SA"), "الشروق")
		self.assertEqual(term_text("midnight", "en_GB"), "Midnight")
		self.assertEqual(term_text("lastThird", "ar"), "بداية الثلث الأخير")
		self.assertEqual(term_text("last_third_start", "fr"), "Start of the last third")
		self.assertEqual(normalize_language("fr"), "en")

	def test_every_glossary_source_is_in_gettext_catalog(self):
		catalog = extract_catalog()
		for identity in GLOSSARY_IDENTITIES:
			self.assertIn(source_message(identity), catalog)
		self.assertIn(DEFAULT_DAILY_WIRD_TEXT, catalog)
		self.assertIn(LOCATION_REQUIRED_MESSAGE, catalog)


class DirectionAndDocumentationTests(unittest.TestCase):
	def test_central_direction_and_fallback_policy(self):
		for language, supported, rtl in (
			("ar", "ar", True), ("ar_SA", "ar", True),
			("en", "en", False), ("en_GB", "en", False), ("fr", "en", False),
		):
			with self.subTest(language=language):
				self.assertEqual(supported_language(language), supported)
				self.assertEqual(is_rtl_language(language), rtl)

	def test_every_actual_dialog_applies_the_central_direction_policy(self):
		for name, minimum in (("settings_panel.py", 1), ("ui.py", 2), ("text_dialog.py", 1)):
			source = (CORE / "nvda_adapter" / name).read_text(encoding="utf-8")
			self.assertGreaterEqual(source.count("SetLayoutDirection"), minimum, name)
			self.assertIn("is_rtl_language", source, name)

	def test_bilingual_help_is_semantic_current_and_packaged(self):
		package = ROOT / "dist" / f"awqati-{buildVars.addon_info['addon_version']}.nvda-addon"
		with zipfile.ZipFile(package) as archive:
			for language, direction in (("ar", "rtl"), ("en", "ltr")):
				name = f"doc/{language}/readme.html"
				self.assertIn(name, archive.namelist())
				text = archive.read(name).decode("utf-8")
				self.assertIn(f'lang="{language}"', text)
				self.assertIn(f'dir="{direction}"', text)
				self.assertNotIn("initial scaffold", text.casefold())
				self.assertNotIn("حزمة هيكلية أولية", text)
				self.assertNotIn("OnlinePrayerVerifier", text)
				outline = _DocumentOutline()
				outline.feed(text)
				self.assertGreaterEqual(len(outline.headings), 6)

	def test_package_has_only_arabic_locale_and_english_source_fallback(self):
		package = ROOT / "dist" / f"awqati-{buildVars.addon_info['addon_version']}.nvda-addon"
		with zipfile.ZipFile(package) as archive:
			names = archive.namelist()
			locale_roots = {name.split("/")[1] for name in names if name.startswith("locale/")}
			self.assertEqual(locale_roots, {"ar", "BABEL-LICENSE.txt", "NOTICE.txt", "UNICODE-LICENSE.txt"})
			arabic = gettext.GNUTranslations(io.BytesIO(archive.read("locale/ar/LC_MESSAGES/nvda.mo")))
			self.assertEqual(arabic.gettext(DEFAULT_DAILY_WIRD_TEXT), "لا تنس وردك اليومي.")
			self.assertEqual(
				arabic.gettext(LOCATION_REQUIRED_MESSAGE),
				"لم يتم تعيين الموقع. فضلًا عيّنه من إعدادات أوقاتي ثم حاول مرة أخرى.",
			)
			self.assertEqual(gettext.NullTranslations().gettext(DEFAULT_DAILY_WIRD_TEXT), DEFAULT_DAILY_WIRD_TEXT)


if __name__ == "__main__":
	unittest.main()
