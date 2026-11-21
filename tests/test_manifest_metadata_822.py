"""Generate and validate current manifests, without rebuilding a release archive."""
import ast
import gettext
import hashlib
import io
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import buildVars
from babel.messages.pofile import read_po
from configobj import ConfigObj
from tools import build_translations as builder

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("summary", "description", "changelog")

# Frozen approved texts: independent of the metadata and translation sources.
EXPECTED_SUMMARY_AR = 'أوقاتي: مواقيت الصلاة والتقاويم والطقس والمعلومات الفلكية وأدوات الوقت.'
EXPECTED_SUMMARY_EN = 'Awqati: prayer times, calendars, weather, astronomical information and time tools.'
EXPECTED_DESCRIPTION_AR = 'أوقاتي إضافة متكاملة لقارئ الشاشة NVDA، تجمع بين مواقيت الصلاة والتقاويم والمعلومات الفلكية وأدوات إدارة الوقت، وتتيح الوصول إلى خدمات الطقس والأحداث التاريخية، من خلال واجهة ميسّرة تدعم العربية والإنجليزية.\n\nتتيح الإضافة معرفة مواقيت الصلوات الخمس، وأوقات الشروق ومنتصف الليل وبداية الثلث الأخير منه، مع إمكانية ضبط التنبيهات المرتبطة بدخول أوقات الصلاة والإقامة، وتحديد مواعيد التنبيه قبل الصلاة وبعدها. كما توفر التوقيت الزوالي والتوقيت الغروبي، وتتيح كذلك معرفة اتجاه القبلة.\n\nوتدعم خمسة تقاويم: الميلادي، والهجري القمري، والهجري الشمسي السعودي، والفارسي، والأفغاني، إلى جانب أدوات لتحويل التواريخ بين التقاويم المختلفة.\n\nوتقدم الإضافة معلومات فلكية يومية، بالإضافة إلى معلومات التقويم العربي التراثي.\n\nومن وظائفها تذكيرات الأذكار والأوراد، وتحديد ساعات الهدوء، فضلًا عن مجموعة من أدوات إدارة الوقت، تشمل المنبهات الشخصية، والمؤقتات التنازلية، وساعة الإيقاف، والساعة العالمية.\n\nكما توفر خدمة اختيارية للطقس، تتيح الاطلاع على الأحوال الجوية الحالية وتوقعات الساعات والأيام القادمة، والحصول على تقارير نصية ميسّرة.\n\nوتتضمن الإضافة أيضًا خدمة «حدث في مثل هذا اليوم»، التي تستقي معلوماتها من ويكيبيديا، وتعرض أبرز الأحداث التاريخية والمواليد والوفيات والأعياد والمناسبات، إما بالسرد المباشر أو في صفحات ويب مهيأة للتصفح باستخدام قارئ الشاشة، مع روابط إلى المقالات الأصلية.'
EXPECTED_DESCRIPTION_EN = 'Awqati is a comprehensive add-on for the NVDA screen reader, combining prayer times, calendars, astronomical information and time management tools. It also provides access to weather services and historical events through an accessible interface that supports Arabic and English.\n\nThe add-on provides the times of the five daily prayers, sunrise, midnight and the start of the last third of the night. It allows users to configure alerts for the start of prayer times and Iqama, and to set alerts before and after prayers. It also provides Zawali and Ghurubi time, as well as the Qibla direction.\n\nIt supports five calendars: Gregorian, Lunar Hijri, Saudi Solar Hijri, Persian Solar Hijri and Afghan Solar Hijri, along with tools for converting dates between the different calendars.\n\nThe add-on provides daily astronomical information, as well as information from the traditional Arabian calendar.\n\nIts features include reminders for adhkar and daily Wird, configurable quiet hours, and a range of time management tools, including personal alarms, countdown timers, a stopwatch and a world clock.\n\nIt also offers an optional weather service for checking current weather conditions and forecasts for the coming hours and days, with accessible text reports.\n\nThe add-on also includes an "On This Day" service that draws its information from Wikipedia and presents notable historical events, births, deaths, holidays and observances, either through direct narration or on web pages designed for browsing with a screen reader, with links to the original articles.'


def parsed_manifest(path):
    return ConfigObj(str(path), encoding="utf-8", interpolation=False,
                     raise_errors=True)


class ManifestMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="awqati-manifest-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.staging = Path(cls.temporary.name)
        builder.build_manifest_metadata(cls.staging, pot_path=cls.staging / "messages.pot")
        cls.english_path = cls.staging / "manifest.ini"
        cls.arabic_path = cls.staging / "locale/ar/manifest.ini"
        cls.english = parsed_manifest(cls.english_path)
        cls.arabic = parsed_manifest(cls.arabic_path)
        cls.translator = gettext.GNUTranslations(io.BytesIO(
            (cls.staging / "locale/ar/LC_MESSAGES/nvda.mo").read_bytes()))
        with (ROOT / "addon/locale/ar/LC_MESSAGES/nvda.po").open("rb") as stream:
            cls.catalog = read_po(stream, locale="ar")

    def test_both_manifests_parse_with_the_nvda_config_parser(self):
        self.assertEqual(set(self.arabic), set(KEYS))
        self.assertEqual(set(self.english), {
            "name", "summary", "description", "author", "url", "version", "changelog",
            "docFileName", "minimumNVDAVersion", "lastTestedNVDAVersion", "updateChannel",
        })
        for key in KEYS:
            self.assertIsInstance(self.english[key], str)
            self.assertIsInstance(self.arabic[key], str)
            self.assertTrue(self.english[key].strip())
            self.assertTrue(self.arabic[key].strip())

    def test_approved_summaries_match_exactly_in_both_languages(self):
        self.assertEqual(self.english["summary"], EXPECTED_SUMMARY_EN)
        self.assertEqual(self.arabic["summary"], EXPECTED_SUMMARY_AR)

    def test_approved_descriptions_match_exactly_in_both_languages(self):
        self.assertEqual(self.english["description"], EXPECTED_DESCRIPTION_EN)
        self.assertEqual(self.arabic["description"], EXPECTED_DESCRIPTION_AR)
        for manifest in (self.english, self.arabic):
            self.assertEqual(len(manifest["description"].split("\n\n")), 7)

    def test_optional_weather_and_wikipedia_delivery_are_preserved(self):
        for manifest, terms in (
            (self.english, ("optional weather service", "accessible text reports", "Wikipedia",
                            "direct narration", "screen reader", "links to the original articles")),
            (self.arabic, ("خدمة اختيارية للطقس", "تقارير نصية ميسّرة", "ويكيبيديا",
                           "بالسرد المباشر", "قارئ الشاشة", "روابط إلى المقالات الأصلية")),
        ):
            for term in terms:
                with self.subTest(term=term):
                    self.assertIn(term, manifest["description"])

    def test_all_three_fields_are_extracted_and_compiled_without_fallback(self):
        extracted = builder.extract_catalog()
        for key in builder.MANIFEST_TRANSLATION_KEYS:
            with self.subTest(key=key):
                source = buildVars.addon_info[key]
                self.assertIn(source, extracted)
                self.assertIn(source, self.catalog)
                self.assertFalse(self.catalog[source].fuzzy)
                expected = self.catalog[source].string
                self.assertNotEqual(source, expected)
                self.assertEqual(self.translator.gettext(source), expected)
                self.assertEqual(self.arabic[key.removeprefix("addon_")], expected)
                self.assertEqual(self.english[key.removeprefix("addon_")], source)

    def test_arabic_manifest_has_no_english_fallback_or_unexpanded_placeholder(self):
        for key, value in self.arabic.items():
            with self.subTest(key=key):
                self.assertRegex(value, r"[\u0600-\u06ff]")
                # NVDA is the sole Latin name in the owner's verbatim Arabic text.
                self.assertEqual(re.findall(r"[A-Za-z]+", value), ["NVDA"] if key == "description" else [])
                self.assertNotRegex(value, r"\{addon_\w+\}")
        self.assertEqual(self.translator.gettext("Awqati"), "أوقاتي")

    def test_changelog_is_short_bilingual_and_includes_the_wikipedia_correction(self):
        for language, notes, markers in (
            ("en", self.english["changelog"], ("November 21", "15 minutes", "restart", "request limits")),
            ("ar", self.arabic["changelog"], ("21 نوفمبر", "15 دقيقة", "إعادة التشغيل", "قيود طلبات")),
        ):
            with self.subTest(language=language):
                self.assertIn("8.2.2", notes)
                self.assertEqual(notes.splitlines()[0], "Version 8.2.2" if language == "en" else "الإصدار 8.2.2")
                self.assertNotRegex(notes, r"قيد الإعداد|in preparation")
                self.assertLess(len(notes), 900)
                self.assertEqual(sum(line.startswith("- ") for line in notes.splitlines()), 3)
                for marker in markers:
                    self.assertIn(marker, notes)
                self.assertNotRegex(notes, r"AWQATI_|SHA-256|test_|\d+ tests")

    def test_identity_version_and_compatibility_are_preserved(self):
        self.assertEqual(self.english["name"], "awqati")
        self.assertEqual(self.english["version"], buildVars.addon_info["addon_version"])
        self.assertEqual(self.english["version"], "8.2.2")
        self.assertEqual(self.english["minimumNVDAVersion"], "2026.1.0")
        self.assertEqual(self.english["lastTestedNVDAVersion"], "2026.3.1")
        self.assertEqual(self.english["updateChannel"], "stable")
        self.assertEqual(self.english["docFileName"], "readme.html")

    def test_multiline_punctuation_roundtrips_without_list_splitting(self):
        for path, manifest in ((self.english_path, self.english), (self.arabic_path, self.arabic)):
            text = path.read_text(encoding="utf-8")
            for key in ("description", "changelog"):
                with self.subTest(path=path.name, key=key):
                    self.assertRegex(text, rf'(?ms)^{key} = """.+"""\s*$')
                    self.assertIn("\n", manifest[key])
                    self.assertNotIn('"""', manifest[key])

    def test_missing_changelog_translation_stops_generation(self):
        def without_changelog(stream, **kwargs):
            catalog = read_po(stream, **kwargs)
            source = buildVars.addon_info["addon_changelog"]
            if source in catalog:
                catalog.delete(source)
            return catalog
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(builder, "read_po", side_effect=without_changelog):
                with self.assertRaisesRegex(ValueError, "Incomplete Arabic catalog"):
                    builder.build_manifest_metadata(path, pot_path=path / "messages.pot")
            self.assertFalse((path / "locale/ar/manifest.ini").exists())

    def test_history_keeps_prior_release_and_technical_archive(self):
        history = (ROOT / "changelog.md").read_text(encoding="utf-8")
        self.assertTrue(history.startswith("# 8.2.2 — 21 نوفمبر 2026\n"))
        self.assertNotIn("قيد الإعداد", history.split("# 8.2.1", 1)[0])
        for marker in ("# 8.2.1", "# 8.0.2", "8.0.1", "7.1.0", "development_changelog_pre5.md"):
            self.assertIn(marker, history)
        archive = (ROOT / "docs/release/8.2.1-manifest-changelog.txt").read_text(encoding="utf-8")
        self.assertTrue(archive.startswith("Version 8.2.1 refines"))
        self.assertIn("Version 8.0.0", archive)
        self.assertIn("Version 6", archive)
        self.assertTrue(archive.rstrip().endswith("optional manual network services."))
        self.assertEqual(hashlib.sha256(archive.rstrip("\n").encode("utf-8")).hexdigest(),
                         "c5f5742056c04d9610da2822c9d86ca88ee2fe7f5dd964eb674d821de06ae2f6")

    def test_packaging_uses_the_same_metadata_generator(self):
        tree = ast.parse((ROOT / "sconstruct").read_text(encoding="utf-8"))
        package = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_build_package")
        calls = [n for n in ast.walk(package) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertEqual(sum(n.func.id == "build_manifest_metadata" for n in calls), 1)
        self.assertIn('{addon_changelog}', (ROOT / "manifest-translated.ini.tpl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
