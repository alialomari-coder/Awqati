"""Offline regressions for the diagnosed November 21 separator and recovery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import ANY, Mock, patch

from test_on_this_day import IndependentListAudit, synthetic
from test_on_this_day_presentation import Document
from addon.globalPlugins.awqati.application.on_this_day import OnThisDayService, EXTRACTION_RETRY_SECONDS
from addon.globalPlugins.awqati.application.on_this_day_presentation import speech_lines, OnThisDayPresentation
from addon.globalPlugins.awqati.domain.on_this_day import Failure, OnThisDayError, SECTION_KEYS
from addon.globalPlugins.awqati.infrastructure.on_this_day_cache import DayCache
from addon.globalPlugins.awqati.infrastructure.on_this_day_html import render_html
from addon.globalPlugins.awqati.infrastructure.on_this_day_links import safe_wikipedia_url
from addon.globalPlugins.awqati.infrastructure.on_this_day_wikipedia import parse_document, LABELS

CAPTURES = Path(__file__).parent / "fixtures/on_this_day/november21"
TODAY = date(2026, 11, 21)


def capture(language):
    return json.loads((CAPTURES / f"{language}.json").read_text(encoding="utf-8"))


class November21Tests(unittest.TestCase):
    def test_both_languages_four_sections_and_every_source_item_and_anchor(self):
        for language, counts, revision in (("ar", (17, 22, 18, 2), 72745142),
                                           ("en", (70, 208, 117, 13), 1386714068)):
            source = capture(language)
            day = parse_document(source, TODAY, language)
            self.assertEqual(day.revision, revision)
            self.assertEqual(tuple(len(s.entries) for s in day.sections), counts)
            audit = IndependentListAudit(source["parse"]["text"])
            for section, label in zip(day.sections, LABELS[language]):
                with self.subTest(language=language, section=section.key):
                    self.assertIsNone(section.failure)
                    # Include year-only parents through context, once per real
                    # source group. They are not separate historical events.
                    self.assertCountEqual(speech_lines(day, section.key, str)[1:], audit.items[label])
                    if section.key == "events":
                        self.assertEqual([e.text for e in section.entries], audit.items[label])
                    expected = {(words, safe_wikipedia_url(href, language))
                                for words, href in audit.link_inventory[label]
                                if words and safe_wikipedia_url(href, language)}
                    actual = {(link.text, link.url) for e in section.entries
                              for c in (e,) + e.context for link in c.links}
                    self.assertEqual(actual, expected)
                    for e in section.entries:
                        for content in (e,) + e.context:
                            for link in content.links:
                                self.assertEqual(content.text[link.start:link.end], link.text)
            first = day.section("events").entries[0]
            if language == "ar":
                self.assertEqual(first.year, "235")
                self.assertIn("ـ", first.text)
                self.assertEqual(first.links[0].text, "235")

    def test_capture_hashes(self):
        for record in json.loads((CAPTURES / "manifest.json").read_text(encoding="utf-8")):
            self.assertEqual(hashlib.sha256((CAPTURES / record["file"]).read_bytes()).hexdigest(), record["sha256"])

    def test_year_forms_separators_linked_years_and_shared_year_preserve_text(self):
        for year in ("235", "١٩٠٠", "44 ق.م.", "44 ق . م", "44 BC", "44 BCE."):
            for separator in ("ـ", "–", "—", "−", "-"):
                for spacing in ("", " "):
                    with self.subTest(year=year, separator=separator, spacing=spacing):
                        source = synthetic()
                        body = f"<a href='/wiki/Year'>{year}</a>{spacing}{separator}{spacing}حدث أصلي"
                        source["parse"]["text"] = source["parse"]["text"].replace(
                            "44 ق.م. – حدث أصلي<sup class='reference'>[1]</sup>", body)
                        source["parse"]["text"] = source["parse"]["text"].replace("1900 –", "1900 ـ")
                        day = parse_document(source, TODAY, "ar")
                        entry = day.section("events").entries[0]
                        self.assertEqual(entry.year, year)
                        self.assertEqual(entry.text, f"{year}{spacing}{separator}{spacing}حدث أصلي")
                        self.assertEqual(entry.links[0].text, year)
                        self.assertEqual([e.year for e in day.section("births").entries], ["1900", "1900"])

    def test_unknown_separator_still_rejects_entire_section(self):
        source = synthetic()
        source["parse"]["text"] = source["parse"]["text"].replace("44 ق.م. –", "44 ق.م. :")
        section = parse_document(source, TODAY, "ar").section("events")
        self.assertEqual(section.failure, Failure.EXTRACTION)
        self.assertFalse(section.entries)

    def test_speech_html_all_sections_keep_text_context_and_links(self):
        for language in ("ar", "en"):
            day = parse_document(capture(language), TODAY, language)
            for section in day.sections:
                with self.subTest(language=language, section=section.key):
                    lines = speech_lines(day, section.key, str)
                    page = Document(render_html(day, section.key, str))
                    for e in section.entries:
                        self.assertIn(e.text, lines)
                        self.assertTrue(any(e.text in item for item in page.items) or e.text in "".join(page.text))
                        for content in (e,) + e.context:
                            for link in content.links:
                                self.assertIn((link.url, link.text), page.anchors)
                    self.assertEqual(page.anchors[-1][0], day.source_url)

    def test_both_presentation_modes_pass_the_selected_section_to_the_service(self):
        for web in (False, True):
            service = Mock()
            presenter = OnThisDayPresentation(service, language=lambda: "ar", today=lambda: TODAY,
                web_mode=lambda: web, translate=str, schedule=lambda *args: Mock(), settle_ms=lambda: 600,
                speak=Mock(), stop_speech=Mock(), message=Mock(), open_page=Mock())
            for section in SECTION_KEYS:
                presenter.select(section)
                service.request.assert_called_with(ANY, section=section)
            presenter.close()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "day.json"
        self.clock = 0.0
        self.wall = 1800000000.0
        self.good = parse_document(capture("ar"), TODAY, "ar")
        self.partial = replace(self.good, sections=(replace(self.good.sections[0], entries=(),
            failure=Failure.EXTRACTION, detail="old extractor"),) + self.good.sections[1:])
        self.answer = self.partial
        self.calls = 0
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.service = self.make_service()

    def fetch(self, *args):
        self.calls += 1
        self.entered.set()
        if self.block:
            self.assertTrue(self.release.wait(5))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def make_service(self):
        owner = self
        class Provider:
            fetch = owner.fetch
        service = OnThisDayService(Provider(), DayCache(self.path), language=lambda: "ar", today=lambda: TODAY,
            dispatch=lambda callback: callback(), monotonic=lambda: self.clock, now=lambda: self.wall)
        self.addCleanup(service.close)
        return service

    def get(self, section="events"):
        return self.service.request(section=section).result(5)

    def advance(self, seconds):
        self.clock += seconds
        self.wall += seconds

    def restart(self):
        self.service.close()
        self.service = self.make_service()

    def test_memory_and_disk_wait_then_recover_and_cache_success_all_day(self):
        self.assertEqual(self.get(), self.partial)
        self.answer = self.good
        for elapsed in (1, 400, 498):
            self.advance(elapsed)
            self.assertEqual(self.get(), self.partial)
        self.assertEqual(self.calls, 1)
        self.restart()
        self.assertEqual(self.get(), self.partial)
        self.assertEqual(self.calls, 1)
        self.advance(1)
        self.assertEqual(self.get(), self.good)
        self.assertEqual(self.calls, 2)
        self.assertEqual(DayCache(self.path).load(TODAY, "ar"), self.good)
        self.advance(7200)
        self.restart()
        for section in SECTION_KEYS:
            self.assertEqual(self.get(section), self.good)
        self.assertEqual(self.calls, 2)
        self.assertNotIn("retry_at", json.loads(self.path.read_text(encoding="utf-8")))

    def test_successful_sections_never_trigger_retry_of_another_section(self):
        self.get()
        self.answer = self.good
        self.advance(EXTRACTION_RETRY_SECONDS + 1)
        self.restart()
        for section in SECTION_KEYS[1:]:
            self.assertEqual(self.get(section).section(section), self.good.section(section))
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.get(), self.good)
        self.assertEqual(self.calls, 2)

    def test_no_automatic_fetch_when_time_passes(self):
        self.get()
        self.advance(7200)
        self.assertEqual(self.calls, 1)

    def test_legacy_partial_cache_recovers_once_without_discarding_healthy_sections(self):
        DayCache(self.path).save(TODAY, "ar", self.partial)
        self.answer = self.good
        self.assertEqual(self.get("births"), self.partial)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.get(), self.good)
        self.assertEqual(self.calls, 1)

    def test_repeated_extraction_failure_renews_deadline_across_restart(self):
        self.get()
        self.advance(EXTRACTION_RETRY_SECONDS)
        self.get()
        self.assertEqual(self.calls, 2)
        self.restart()
        self.answer = self.good
        self.advance(EXTRACTION_RETRY_SECONDS - 1)
        self.assertEqual(self.get(), self.partial)
        self.assertEqual(self.calls, 2)
        self.advance(1)
        self.assertEqual(self.get(), self.good)
        self.assertEqual(self.calls, 3)

    def test_refresh_network_errors_preserve_good_sections_and_retry_after_on_disk(self):
        for failure in (Failure.CONNECTION, Failure.RATE_LIMIT, Failure.EXTRACTION, Failure.UNAVAILABLE):
            with self.subTest(failure=failure):
                self.answer = self.partial
                self.get()
                self.advance(EXTRACTION_RETRY_SECONDS)
                self.answer = OnThisDayError(failure, "temporary", retry_after=1800)
                before = self.calls
                self.assertEqual(self.get(), self.partial)
                self.assertEqual(self.calls, before + 1)
                self.restart()
                self.answer = self.good
                self.advance(1799)
                self.assertEqual(self.get(), self.partial)
                self.assertEqual(self.calls, before + 1)
                self.advance(1)
                self.assertEqual(self.get(), self.good)
                self.assertEqual(self.calls, before + 2)
                # Start the next scenario with a new partial cache.
                self.service.close()
                DayCache(self.path).save(TODAY, "ar", self.partial)
                self.service = self.make_service()

    def test_simultaneous_retry_requests_share_one_fetch(self):
        self.get()
        self.advance(EXTRACTION_RETRY_SECONDS)
        self.answer, self.block = self.good, True
        self.entered.clear()
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = list(executor.map(lambda _: self.service.request(section="events"), range(20)))
        self.assertTrue(self.entered.wait(2))
        self.release.set()
        self.assertTrue(all(f.result(5) == self.good for f in futures))
        self.assertEqual(self.calls, 2)

    def test_partial_cache_write_failure_keeps_memory_throttle_and_recovers(self):
        with patch.object(self.service.cache, "save", side_effect=OnThisDayError(Failure.STORAGE, "disk full")):
            self.assertEqual(self.get(), self.partial)
        self.assertEqual(self.service.storage_error.kind, Failure.STORAGE)
        self.answer = self.good
        self.advance(899)
        self.assertEqual(self.get(), self.partial)
        self.assertEqual(self.calls, 1)
        self.advance(1)
        self.assertEqual(self.get(), self.good)

    def test_worse_refresh_never_replaces_previously_successful_section(self):
        self.get()
        self.advance(EXTRACTION_RETRY_SECONDS)
        self.answer = replace(self.good, sections=(self.good.sections[0],
            replace(self.good.sections[1], entries=(), failure=Failure.EXTRACTION)) + self.good.sections[2:])
        self.assertEqual(self.get(), self.partial)
        self.assertEqual(DayCache(self.path).load(TODAY, "ar"), self.partial)

    def test_reserved_deadline_is_saved_before_network_retry(self):
        self.get()
        self.advance(EXTRACTION_RETRY_SECONDS)
        self.answer, self.block = self.good, True
        self.entered.clear()
        future = self.service.request(section="events")
        self.assertTrue(self.entered.wait(2))
        cache = DayCache(self.path)
        self.assertEqual(cache.load(TODAY, "ar"), self.partial)
        self.assertEqual(cache.retry_at, self.wall + EXTRACTION_RETRY_SECONDS)
        self.release.set()
        self.assertEqual(future.result(5), self.good)

    def test_invalid_retry_metadata_is_rejected(self):
        self.get()
        original = json.loads(self.path.read_text(encoding="utf-8"))
        for deadline in ("later", True, -1, float("nan"), float("inf")):
            with self.subTest(deadline=deadline):
                changed = dict(original, retry_at=deadline)
                self.path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(OnThisDayError) as caught:
                    DayCache(self.path).load(TODAY, "ar")
                self.assertEqual(caught.exception.kind, Failure.STORAGE)


if __name__ == "__main__":
    unittest.main()
