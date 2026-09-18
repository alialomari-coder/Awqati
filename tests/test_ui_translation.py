"""Regression contract for the current bilingual settings UI and shipped gettext."""
import ast
import gettext
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from tools.build_translations import extract_catalog
import buildVars
from awqati.nvda_adapter.settings_sections import N_, is_rtl_language
from awqati import domain

ADAPTER = ROOT / "addon/globalPlugins/awqati/nvda_adapter"


class UiTranslationTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.catalog = extract_catalog()
		package = ROOT / "dist" / ("awqati-" + buildVars.addon_info["addon_version"] + ".nvda-addon")
		with zipfile.ZipFile(package) as archive:
			cls.names = archive.namelist()
			cls.ar = gettext.GNUTranslations(io.BytesIO(archive.read("locale/ar/LC_MESSAGES/nvda.mo")))
			cls.manifest_ar = archive.read("locale/ar/manifest.ini").decode("utf-8")
			cls.manifest = archive.read("manifest.ini").decode("utf-8")
		cls.en = gettext.NullTranslations()

	def test_recursive_extraction_includes_every_adapter_message_module(self):
		paths = {path for message in self.catalog for path, line in message.locations}
		for filename in ("plugin.py", "settings_panel.py", "ui.py"):
			self.assertIn("addon/globalPlugins/awqati/nvda_adapter/" + filename, paths)
		self.assertIn("Alert action before the event:", self.catalog)
		self.assertIn("Full", self.catalog)

	def test_shipped_arabic_has_source_compiled_and_manifest_resources(self):
		for name in ("locale/ar/LC_MESSAGES/nvda.po", "locale/ar/LC_MESSAGES/nvda.mo", "locale/ar/manifest.ini"):
			self.assertIn(name, self.names)
		self.assertIn('summary = "أوقاتي"', self.manifest_ar)
		self.assertIn('summary = "Awqati"', self.manifest)
		self.assertFalse(any(name.startswith("babel/") for name in self.names))


	def test_manifest_description_with_commas_is_quoted(self):
		for manifest in (self.manifest, self.manifest_ar):
			line = next(line for line in manifest.splitlines() if line.startswith("description = "))
			self.assertTrue(line.startswith('description = "') and line.endswith('"'))

	def test_format_fields_survive_translation(self):
		from string import Formatter
		def fields(text):
			return {field for _, field, _, _ in Formatter().parse(text) if field is not None}
		for message in self.catalog:
			if message.id:
				self.assertEqual(fields(message.id), fields(self.ar.gettext(message.id)))

	def test_every_extracted_message_has_real_arabic_translation(self):
		for message in self.catalog:
			if message.id:
				with self.subTest(message=message.id):
					translated = self.ar.gettext(message.id)
					self.assertNotEqual(translated, message.id)
					self.assertTrue(any("\u0600" <= char <= "\u06ff" for char in translated))

	def test_english_fallback_is_source_text(self):
		for message in self.catalog:
			if message.id:
				self.assertEqual(self.en.gettext(message.id), message.id)

	def test_supported_and_unsupported_locale_policy(self):
		localedir = str(ROOT / "build/awqati/locale")
		for language in ("ar", "ar_SA", "en", "en_GB", "fr"):
			with self.subTest(language=language), patch.dict(os.environ, {"LANGUAGE": "ar", "LANG": "ar_SA"}):
				translate = gettext.translation("nvda", localedir, languages=[language], fallback=True).gettext
				self.assertEqual(translate("Awqati"), "أوقاتي" if language.startswith("ar") else "Awqati")
				self.assertEqual(is_rtl_language(language), language.startswith("ar"))

	def test_deferred_labels_keep_enum_identities_and_all_main_lists(self):
		namespace = vars(domain).copy()
		from awqati.nvda_adapter import settings_sections
		namespace.update(vars(settings_sections))
		namespace["N_"] = N_
		tree = ast.parse((ADAPTER / "settings_panel.py").read_text(encoding="utf-8"))
		maps = {}
		for node in tree.body:
			if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id.endswith("_LABELS"):
				maps[node.targets[0].id] = eval(compile(ast.Expression(node.value), "labels", "eval"), namespace)
		self.assertEqual(len(maps), 8)
		self.assertEqual([self.ar.gettext(value) for value in maps["SECTION_LABELS"].values()], ["مواقيت الصلاة", "الساعة", "التاريخ", "تنبيهات الأذكار"])
		for labels in maps.values():
			keys_before = tuple(labels)
			for translate in (self.ar.gettext, self.en.gettext):
				self.assertTrue(all(translate(text) for label in labels.values() for text in (label if isinstance(label, tuple) else (label,))))
				self.assertEqual(tuple(labels), keys_before)
		self.assertEqual(domain.PrayerEventName.FAJR.value, "fajr")

	def test_direct_ui_labels_and_helper_arguments_are_marked(self):
		for path in (ADAPTER / "settings_panel.py", ADAPTER / "ui.py"):
			tree = ast.parse(path.read_text(encoding="utf-8"))
			for node in ast.walk(tree):
				if not isinstance(node, ast.Call):
					continue
				function = node.func.id if isinstance(node.func, ast.Name) else ""
				arguments = [keyword.value for keyword in node.keywords if keyword.arg in ("label", "title")]
				if function in ("_choice", "_spin", "AlertOutputEditor"):
					arguments += node.args[2:3]
				for argument in arguments:
					self.assertFalse(isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value, (path.name, node.lineno))

	def test_each_translating_module_initializes_official_gettext_before_classes(self):
		for name in ("ui.py", "plugin.py", "settings_panel.py"):
			tree = ast.parse((ADAPTER / name).read_text(encoding="utf-8"))
			initialization = next(node.lineno for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "initTranslation")
			self.assertLess(initialization, min(node.lineno for node in tree.body if isinstance(node, ast.ClassDef)))

	def test_country_and_calculation_labels_are_covered_without_mutating_data(self):
		for relative, key in (("locations/metadata.json", "countries"), ("calculation_methods/methods.json", "methods")):
			data = json.loads((ROOT / "addon/globalPlugins/awqati/data" / relative).read_text(encoding="utf-8"))
			for item in data[key]:
				self.assertNotEqual(self.ar.gettext(item["name"]), item["name"])

	def test_page_and_both_dialogs_use_nvda_language_for_direction(self):
		for name, count in (("settings_panel.py", 1), ("ui.py", 2)):
			tree = ast.parse((ADAPTER / name).read_text(encoding="utf-8"))
			calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "SetLayoutDirection"]
			self.assertEqual(len(calls), count)
			for call in calls:
				self.assertIn("languageHandler.getLanguage()", ast.unparse(call))


if __name__ == "__main__":
	unittest.main()
