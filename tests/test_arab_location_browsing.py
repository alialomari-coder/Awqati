"""Acceptance tests for linguistic presentation and complete Arab-country browsing."""
from dataclasses import replace
import gzip
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "addon/globalPlugins"), str(ROOT / ".build-deps")]
from awqati.infrastructure import BundledLocationRepository
from awqati.application.ports import CountryInfo
from awqati.nvda_adapter.location_labels import (
    ARAB_COUNTRIES, city_name, collation_key, country_choices, fallback_key,
    location_choices, normalized_name, subdivisions,
)
from babel.messages.pofile import read_po


class ArabicCollationTests(unittest.TestCase):
    def test_real_arabic_alphabet(self):
        expected = list("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")
        for key in (collation_key("ar"), fallback_key):
            self.assertEqual(sorted(reversed(expected), key=key), expected)

    def test_alef_variants_and_vocalization(self):
        for value in ("أ", "إ", "آ", "ٱ"):
            self.assertEqual(normalized_name(value), "ا")
        for value in ("بُرَيدَة", "بــريدة", "  بريدة "):
            self.assertEqual(normalized_name(value), normalized_name("بريدة"))
        self.assertEqual(normalized_name("على"), normalized_name("علي"))
        self.assertEqual(normalized_name("أبو   عريش"), normalized_name("ابو عريش"))

    def test_buraydah_stays_between_alef_and_teh(self):
        for language in ("ar", "ar_SA"):
            items = sorted(["تبوك", "بُرَيدَة", "أبها", "بريدة"], key=collation_key(language))
            self.assertEqual(items[0], "أبها")
            self.assertEqual(items[-1], "تبوك")
            self.assertEqual(set(items[1:3]), {"بُرَيدَة", "بريدة"})

    def test_english_order(self):
        self.assertEqual(sorted(["Zimbabwe", "Belgium", "Aruba", "Algeria"], key=collation_key("en")),
                         ["Algeria", "Aruba", "Belgium", "Zimbabwe"])

    def test_country_sort_uses_display_not_identity(self):
        countries = (CountryInfo("AA", "Z", 1), CountryInfo("ZZ", "A", 1), CountryInfo("BB", "B", 1))
        names = {"Z": "تونس", "A": "جيبوتي", "B": "أروبا"}
        self.assertEqual([c.code for c in country_choices(countries, "ar", names.__getitem__)], ["BB", "AA", "ZZ"])
        self.assertEqual([c.code for c in country_choices(countries, "en", lambda s:s)], ["ZZ", "BB", "AA"])


class ArabBrowsingTests(unittest.TestCase):
    def setUp(self):
        self.repo = BundledLocationRepository()

    def test_no_macroregions_in_actual_country_data_and_translation(self):
        with (ROOT / "addon/locale/ar/LC_MESSAGES/nvda.po").open("rb") as f:
            catalog = read_po(f)
        banned = {"europe", "asia", "africa", "americas", "أوربا", "أوروبا", "آسيا", "أفريقيا", "الأمريكتان"}
        for country in self.repo.countries():
            self.assertNotEqual(country.code, "EU")
            self.assertNotIn(country.name.casefold(), banned)
            self.assertNotIn(catalog[country.name].string, banned)
        self.assertEqual(next(c.name for c in self.repo.countries() if c.code == "AW"), "Aruba")

    def test_one_country_cache(self):
        self.repo.browse("SA")
        self.repo.browse("AE")
        self.assertEqual(list(self.repo._cache), ["AE"])

    def test_search_grade_precedes_display_name(self):
        seed = self.repo.get("SA", "108410")
        matches = (replace(seed, match_strength=3, arabic_names=("أبها",)),
                   replace(seed, match_strength=0, arabic_names=("ينبع",)),
                   replace(seed, match_strength=1, arabic_names=("تبوك",)),
                   replace(seed, match_strength=1, arabic_names=("بريدة",)))
        class Service:
            def countries(self): return (CountryInfo("SA", "Saudi Arabia", 4),)
            def search(self, *args): return matches
        result = location_choices(Service(), "SA", "x", "ar")
        self.assertEqual([m.arabic_names[0] for m in result], ["ينبع", "بريدة", "تبوك", "أبها"])

    def test_arabic_english_aliases_keep_identity(self):
        for country, identity, queries in (("SA", "108410", ("الرياض", "Riyadh")),
                                           ("AE", "292223", ("دبي", "Dubai"))):
            for query in queries:
                self.assertIn(identity, [m.location.location_id for m in location_choices(self.repo, country, query, "ar")])

    def test_ties_use_admin_then_identity(self):
        seed = self.repo.get("SA", "108410")
        a = replace(seed, location=replace(seed.location, location_id="100"), arabic_names=("مدينة",), arabic_admin1_names=("ب",))
        b = replace(a, location=replace(a.location, location_id="200"), arabic_admin1_names=("أ",))
        class Service:
            def countries(self): return (CountryInfo("SA", "Saudi Arabia", 2),)
            def browse(self,*args): return (a,b)
        self.assertEqual([m.location.location_id for m in location_choices(Service(), "SA", "", "ar")], ["200", "100"])

    def test_admin_codes_and_unknown_arab_admins_omitted(self):
        seed = self.repo.get("SA", "108410")
        for cc in ("SA", "AW"):
            value = replace(seed, country_code=cc, admin1_name="00", admin2_name="001", arabic_admin1_names=(), arabic_admin2_names=())
            self.assertEqual(subdivisions(value, "ar"), ())
            self.assertEqual(subdivisions(value, "en"), ())
        value = replace(seed, admin1_name="Unknown Proper Name", admin2_name="", arabic_admin1_names=(), arabic_admin2_names=())
        self.assertEqual(subdivisions(value, "ar"), ())

    def test_mixed_primary_name_is_not_shown(self):
        seed = self.repo.get("SA", "108410")
        value = replace(seed, arabic_names=("الرياض / Riyadh", "الرياض"))
        self.assertEqual(city_name(value, "ar"), "الرياض")
        self.assertEqual(city_name(replace(value, arabic_names=()), "ar"), seed.location.name)

    def test_non_arab_initial_list_remains_bounded_and_sorted(self):
        result = location_choices(self.repo, "US", "", "en")
        self.assertEqual(len(result), 40)
        key = collation_key("en")
        self.assertTrue(all(key(city_name(a,"en")) <= key(city_name(b,"en")) for a,b in zip(result,result[1:])))


class ReviewedArabDataTests(unittest.TestCase):
    def test_three_new_saudi_seats_and_corrected_admins(self):
        repo=BundledLocationRepository()
        for identity,name in (("106273","الحائط"),("108051","السليمي"),("110281","العيدابي")):
            self.assertEqual(city_name(repo.get("SA",identity),"ar"),name)
        self.assertEqual(city_name(repo.get("SA","397513"),"ar"),"الفويلق")
        for identity,region in (("106102","Tabuk Region"),("12546009","Mecca Region"),("107746","Najran Region")):
            self.assertEqual(repo.get("SA",identity).admin1_name,region)

    def test_uae_examples_are_arabic_and_searchable_in_both_languages(self):
        repo=BundledLocationRepository()
        rows=json.loads((ROOT / "data_sources/arabic_reviewed_names.v1.json").read_text("utf-8"))["names"]
        for row in rows:
            match=repo.get(row["countryCode"],row["geonameId"])
            self.assertEqual(city_name(match,"ar"),row["arabicName"])
            for query in (row["arabicName"],match.location.name):
                self.assertIn(row["geonameId"],[m.location.location_id for m in location_choices(repo,"AE",query,"ar")])
        self.assertIn("القطاع 3",subdivisions(repo.get("AE","13118432"),"ar"))

    def test_wikidata_extraction_is_complete_and_geonames_linked(self):
        payload=json.loads((ROOT / "data_sources/wikidata_arabic_names.v1.json").read_text("utf-8"))
        ids=[]
        for batch in payload["batches"]:
            self.assertTrue(batch["complete"])
            self.assertNotIn("LIMIT",batch["query"].upper())
            ids.extend(batch["requestedIds"])
            for row in batch["names"]:
                self.assertIn(row["geonameId"],batch["requestedIds"])
                self.assertRegex(row["entity"],r"^Q[0-9]+$")
        self.assertEqual(len(ids),payload["requestedCount"])
        self.assertEqual(len(ids),len(set(ids)))

    def test_build_rejects_incomplete_wikidata_snapshot(self):
        import tempfile
        from tools.build_locations import apply_arabic_names,BuildLocationError
        payload={"schemaVersion":1,"license":"CC0-1.0","batches":[{"complete":False}]}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"names.json";path.write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(BuildLocationError):apply_arabic_names(path,None,{})


def complete_country_test(code):
    def test(self):
        count = next(c.city_count for c in self.repo.countries() if c.code == code)
        for language in ("ar", "en"):
            matches = location_choices(self.repo, code, "", language)
            self.assertEqual(len(matches), count)
            self.assertEqual(len({m.location.location_id for m in matches}), count)
            key = collation_key(language)
            self.assertTrue(all(key(city_name(a,language)) <= key(city_name(b,language)) for a,b in zip(matches,matches[1:])))
            self.assertEqual(len(self.repo._cache), 1)
    return test

for code in sorted(ARAB_COUNTRIES):
    setattr(ArabBrowsingTests, "test_complete_" + code, complete_country_test(code))
