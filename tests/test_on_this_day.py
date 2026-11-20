"""Offline acceptance tests; fixtures are real, unmodified Action API responses."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from addon.globalPlugins.awqati.application.on_this_day import OnThisDayService
from addon.globalPlugins.awqati.application.operation import CancellationToken
from addon.globalPlugins.awqati.domain.on_this_day import Failure, OnThisDayError, SECTION_KEYS
from addon.globalPlugins.awqati.infrastructure.on_this_day_cache import DayCache
from addon.globalPlugins.awqati.infrastructure.on_this_day_links import safe_wikipedia_url
from addon.globalPlugins.awqati.infrastructure.on_this_day_wikipedia import (
    LABELS, WikipediaDayProvider, WikipediaTransport, parse_document,
)

FIXTURES = Path(__file__).parent / "fixtures/on_this_day"
CASES = (("ar_0.json", date(2026, 11, 11), (17, 27, 18, 6)),
         ("ar_1.json", date(2026, 3, 15), (21, 33, 18, 7)),
         ("ar_2.json", date(2026, 1, 1), (79, 75, 30, 7)),
         ("en_3.json", date(2026, 11, 11), (75, 233, 115, 27)),
         ("ar_4.json", date(2028, 2, 29), (9, 23, 8, 2)),
         ("en_5.json", date(2028, 2, 29), (43, 133, 64, 5)))


def fixture(name="ar_0.json"):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def synthetic(body=None, missing=()):
    # Small explicit edge cases supplement, never replace, the captured pages.
    body = body or {"events": "<ul><li>44 ق.م. – حدث أصلي<sup class='reference'>[1]</sup></li></ul>",
                    "births": "<ul><li>1900 – <ul><li>شخص أول</li><li>شخص ثان</li></ul></li></ul>",
                    "deaths": "<ul><li>2000 – شخص</li></ul>",
                    "observances": "<ul><li>مناسبة<ul><li>بلد أول</li><li>بلد ثان</li></ul></li></ul>"}
    toc, html = [], []
    for key, label in zip(SECTION_KEYS, LABELS["ar"]):
        if key in missing:
            continue
        toc.append(dict(hLevel=2, line=label))
        html.append(f"<h2>{label}</h2>{body[key]}")
    return {"parse": dict(title="11 نوفمبر", revid=123, tocdata=dict(sections=toc), text="".join(html))}


def parse(document):
    return parse_document(document, date(2026, 11, 11), "ar")


class IndependentListAudit(HTMLParser):
    """Independent streaming inventory: record every readable LI's own text.

    Unlike production's tree walker this tracks open LI strings directly and
    counts each source item before any year interpretation or flattening.
    """
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.current = None
        self.heading = None
        self.items = {}
        self.open_items = []
        self.suppressed = 0
        self.anchor = None
        self.link_inventory = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h2":
            self.heading = []
        if tag in {"sup", "style", "script"}:
            self.suppressed += 1
        if tag == "li" and self.current:
            self.open_items.append([])
        if tag == "a" and self.open_items and not self.suppressed:
            self.anchor = (attrs.get("href"), [])

    def handle_data(self, value):
        if self.heading is not None:
            self.heading.append(value)
        if self.open_items and not self.suppressed:
            self.open_items[-1].append(value)
        if self.anchor is not None and not self.suppressed:
            self.anchor[1].append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            href, words = self.anchor
            self.link_inventory.setdefault(self.current, []).append((" ".join("".join(words).split()), href))
            self.anchor = None
        if tag in {"sup", "style", "script"}:
            self.suppressed -= 1
        if tag == "h2":
            self.current = "".join(self.heading).strip()
            self.items[self.current] = []
            self.heading = None
        if tag == "li" and self.open_items:
            own = " ".join("".join(self.open_items.pop()).replace("\u200e", "").replace("\u200f", "").split())
            self.items[self.current].append(own)


class ExtractionTests(unittest.TestCase):
    def test_all_six_captured_pages_four_sections_and_metadata(self):
        for name, day, counts in CASES:
            with self.subTest(name=name):
                document = fixture(name)
                result = parse_document(document, day, name[:2])
                self.assertEqual(tuple(len(s.entries) for s in result.sections), counts)
                self.assertTrue(all(s.failure is None for s in result.sections))
                self.assertEqual(result.revision, document["parse"]["revid"])
                self.assertIn(str(result.revision), result.source_url)
                self.assertEqual(result.local_date, day)

    def test_every_readable_source_list_item_is_preserved(self):
        for name, day, _ in CASES:
            with self.subTest(name=name):
                document = fixture(name)
                inventory = IndependentListAudit(document["parse"]["text"])
                result = parse_document(document, day, name[:2])
                for section, label in zip(result.sections, LABELS[name[:2]]):
                    # Source items consisting only of a year are structural parents;
                    # every child's effective year is tested separately below.
                    expected = [item for item in inventory.items[label] if not re.fullmatch(r"\d+\s*[-–—]?", item)]
                    self.assertCountEqual([e.text for e in section.entries], expected, (name, section.key))

    def test_fixture_sha256_matches_capture_manifest(self):
        for record in json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8")):
            self.assertEqual(hashlib.sha256((FIXTURES / record["file"]).read_bytes()).hexdigest(), record["sha256"])

    def test_bce_year_and_reference_removal(self):
        entry = parse(synthetic()).section("events").entries[0]
        self.assertEqual(entry.year, "44 ق.م.")
        self.assertEqual(entry.text, "44 ق.م. – حدث أصلي")
        self.assertEqual(parse(fixture("ar_1.json")).section("deaths").entries[0].year, "44 ق.م")

    def test_nested_shared_year_and_holiday_context(self):
        result = parse(synthetic())
        self.assertEqual([e.year for e in result.section("births").entries], ["1900", "1900"])
        self.assertEqual([e.text for e in result.section("births").entries], ["شخص أول", "شخص ثان"])
        self.assertEqual(result.section("observances").entries[1].context[0].text, "مناسبة")

    def test_year_inheritance_does_not_escape_parent(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("<li>شخص ثان</li></ul></li>", "<li>شخص ثان</li></ul></li><li>شخص بلا سنة</li>")
        result = parse(doc).section("births")
        self.assertEqual(result.failure, Failure.EXTRACTION)
        self.assertEqual(result.entries, ())

    def test_missing_section_preserves_other_sections(self):
        result = parse(synthetic(missing=("births",)))
        self.assertEqual(result.section("births").failure, Failure.UNAVAILABLE)
        self.assertTrue(all(result.section(k).entries for k in ("events", "deaths", "observances")))

    def test_empty_section_is_unavailable(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("<ul><li>2000 – شخص</li></ul>", "")
        self.assertEqual(parse(doc).section("deaths").failure, Failure.UNAVAILABLE)

    def test_table_or_prose_rejects_whole_section(self):
        for replacement in ("<table><tr><td>1900 – معلومة</td></tr></table>", "<p>معلومة غير متوقعة</p>"):
            doc = synthetic()
            doc["parse"]["text"] = doc["parse"]["text"].replace("<ul><li>2000 – شخص</li></ul>", replacement)
            self.assertEqual(parse(doc).section("deaths").failure, Failure.EXTRACTION)
            self.assertEqual(parse(doc).section("deaths").entries, ())

    def test_duplicate_heading_and_toc_mismatch(self):
        for change in (lambda d: d["parse"].update(text=d["parse"]["text"] + "<h2>أحداث</h2>"),
                       lambda d: d["parse"]["tocdata"]["sections"][0].update(hLevel=3)):
            doc = synthetic()
            change(doc)
            self.assertEqual(parse(doc).section("events").failure, Failure.EXTRACTION)

    def test_renamed_html_heading_with_original_toc_is_extraction_error(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("<h2>أحداث</h2>", "<h2>عنوان متغير</h2>")
        self.assertEqual(parse(doc).section("events").failure, Failure.EXTRACTION)

    def test_malformed_html_and_invalid_response(self):
        doc = synthetic()
        doc["parse"]["text"] += "<div>"
        with self.assertRaises(OnThisDayError) as caught:
            parse(doc)
        self.assertEqual(caught.exception.kind, Failure.EXTRACTION)
        for document in ([], {}, {"parse": {}}, {"warnings": {"parse": "deprecated"}}):
            with self.assertRaises(OnThisDayError):
                parse(document)

    def test_css_changes_and_transparent_wrapper_do_not_change_data(self):
        doc = fixture("en_3.json")
        original = parse_document(doc, date(2026, 11, 11), "en")
        # Only strip presentation attributes; semantic reference markers remain.
        doc["parse"]["text"] = "<section>" + doc["parse"]["text"].replace('class="mw-parser-output"', 'class="different-style"') + "</section>"
        changed = parse_document(doc, date(2026, 11, 11), "en")
        self.assertEqual(original.sections, changed.sections)


class TransportTests(unittest.TestCase):
    def invoke_error(self, error, expected):
        with patch("addon.globalPlugins.awqati.infrastructure.network_services.urlopen", side_effect=error):
            with self.assertRaises(OnThisDayError) as caught:
                WikipediaTransport().read_json("https://ar.wikipedia.org/w/api.php", timeout=1, cancellation=CancellationToken())
        self.assertEqual(caught.exception.kind, expected)
        return caught.exception

    def test_http_403(self):
        self.invoke_error(HTTPError("https://ar.wikipedia.org", 403, "denied", {}, None), Failure.ACCESS)

    def test_http_429_honors_retry_after(self):
        error = self.invoke_error(HTTPError("https://ar.wikipedia.org", 429, "limit", {"Retry-After": "120"}, None), Failure.RATE_LIMIT)
        self.assertEqual(error.retry_after, 120)

    def test_http_5xx(self):
        for code in (500, 502, 503):
            self.invoke_error(HTTPError("https://ar.wikipedia.org", code, "server", {}, None), Failure.SERVER)

    def test_offline_dns_timeout(self):
        for error in (URLError("offline"), URLError(socket.gaierror("DNS failed")), socket.timeout("timeout")):
            self.invoke_error(error, Failure.CONNECTION)

    def test_invalid_json(self):
        with patch.object(WikipediaTransport, "read_bytes", return_value=b"not json"):
            with self.assertRaises(OnThisDayError) as caught:
                WikipediaTransport().read_json("https://ar.wikipedia.org", timeout=1, cancellation=CancellationToken())
        self.assertEqual(caught.exception.kind, Failure.RESPONSE)

    def test_api_error_despite_http_success(self):
        for code, kind in (("missingtitle", Failure.UNAVAILABLE), ("maxlag", Failure.RATE_LIMIT),
                           ("ratelimited", Failure.RATE_LIMIT), ("badvalue", Failure.API)):
            with self.assertRaises(OnThisDayError) as caught:
                parse({"error": {"code": code}})
            self.assertEqual(caught.exception.kind, kind)

    def test_one_request_correct_parameters_local_dates_and_no_fallback(self):
        class Transport:
            def __init__(self):
                self.urls = []
            def read_json(self, url, **kwargs):
                self.urls.append(url)
                return fixture()
        transport = Transport()
        provider = WikipediaDayProvider(transport)
        for day, language, title in ((date(2028, 2, 29), "ar", "29 فبراير"),
                                     (date(2026, 12, 31), "en", "December 31"),
                                     (date(2027, 1, 1), "ar", "1 يناير")):
            provider.fetch(day, language, CancellationToken())
            url = urlsplit(transport.urls[-1])
            query = parse_qs(url.query)
            self.assertEqual(query["page"], [title])
            self.assertEqual(query["prop"], ["tocdata|text|revid"])
            self.assertEqual(url.hostname, language + ".wikipedia.org")
        self.assertEqual(len(transport.urls), 3)
        with self.assertRaises(OnThisDayError):
            provider.fetch(date.today(), "fr", CancellationToken())
        self.assertEqual(len(transport.urls), 3)


class LinkTests(unittest.TestCase):
    def test_link_text_target_offsets_and_speech_are_separate(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("حدث أصلي", "حدث <a href='/wiki/مقالة'>أصلي</a>")
        entry = parse(doc).section("events").entries[0]
        self.assertEqual(entry.text, "44 ق.م. – حدث أصلي")
        self.assertEqual(len(entry.links), 1)
        link = entry.links[0]
        self.assertEqual(link.text, "أصلي")
        self.assertEqual(link.url, "https://ar.wikipedia.org/wiki/مقالة")
        self.assertEqual(entry.text[link.start:link.end], link.text)
        self.assertNotIn("https", entry.text)

    def test_multiple_links_same_label_and_whitespace_have_exact_spans(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("حدث أصلي", "\n<a href='/wiki/A'> نفس <b>الاسم</b> </a> و <a href='//en.wikipedia.org/wiki/B'>نفس الاسم</a>")
        entry = parse(doc).section("events").entries[0]
        self.assertEqual([link.text for link in entry.links], ["نفس الاسم", "نفس الاسم"])
        self.assertNotEqual(entry.links[0].start, entry.links[1].start)
        for link in entry.links:
            self.assertEqual(entry.text[link.start:link.end], link.text)

    def test_year_parent_links_survive_with_each_child_context(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("1900 –", "<a href='/wiki/1900'>1900</a> –")
        entries = parse(doc).section("births").entries
        for entry in entries:
            self.assertEqual(entry.context[0].links[0].text, "1900")
            self.assertEqual(entry.context[0].links[0].url, "https://ar.wikipedia.org/wiki/1900")

    def test_all_sections_of_all_fixtures_have_safe_correct_link_spans(self):
        total = 0
        for name, day, _ in CASES:
            result = parse_document(fixture(name), day, name[:2])
            for section in result.sections:
                self.assertTrue(any(entry.links for entry in section.entries), (name, section.key))
                for entry in section.entries:
                    for content in (entry,) + entry.context:
                        for link in content.links:
                            total += 1
                            self.assertEqual(content.text[link.start:link.end], link.text)
                            self.assertEqual(safe_wikipedia_url(link.url, name[:2]), link.url)
        self.assertGreater(total, 1000)

    def test_every_safe_source_anchor_is_retained_with_its_label(self):
        for name, day, _ in CASES:
            document = fixture(name)
            inventory = IndependentListAudit(document["parse"]["text"])
            result = parse_document(document, day, name[:2])
            for section, label in zip(result.sections, LABELS[name[:2]]):
                expected = {(words, safe_wikipedia_url(href, name[:2])) for words, href in inventory.link_inventory[label]
                            if words and safe_wikipedia_url(href, name[:2])}
                actual = {(link.text, link.url) for entry in section.entries for content in (entry,) + entry.context
                          for link in content.links}
                self.assertEqual(actual, expected, (name, section.key))

    def test_external_malicious_and_nonarticle_destinations_rejected(self):
        for href in ("javascript:alert(1)", "data:text/html,test", "file:///C:/test", "https://evil.example/wiki/A",
                     "https://en.wikipedia.org.evil.example/wiki/A", "https://en.wikipedia.org@evil.example/wiki/A",
                     "https://evil@en.wikipedia.org/wiki/A", "https://en.wikipedia.org:443/wiki/A",
                     "https://en.wikipedia.org./wiki/A", "https://wikipedia.org/wiki/A", "/w/api.php",
                     "/w/index.php?title=X&action=edit", "/w/index.php?title=X&redlink=1",
                     "/wiki/A?%61ction=edit", "https://en.wikipedia.org/wiki/A%0aB",
                     "https://en.wikipedia.org\\evil.example/wiki/A", "#cite_note-1", ""):
            with self.subTest(href=href):
                self.assertIsNone(safe_wikipedia_url(href, "ar"))

    def test_valid_article_links_resolve_without_network(self):
        for href, expected in (("/wiki/A#B", "https://ar.wikipedia.org/wiki/A#B"),
                               ("//en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/A"),
                               ("http://fr.wikipedia.org/wiki/A", "https://fr.wikipedia.org/wiki/A"),
                               ("/w/index.php?title=A&oldid=123", "https://ar.wikipedia.org/w/index.php?title=A&oldid=123")):
            self.assertEqual(safe_wikipedia_url(href, "ar"), expected)

    def test_bad_link_keeps_its_readable_label_but_no_destination(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("حدث أصلي", "<a href='javascript:alert(1)'>حدث أصلي</a>")
        entry = parse(doc).section("events").entries[0]
        self.assertEqual(entry.text, "44 ق.م. – حدث أصلي")
        self.assertEqual(entry.links, ())

    def test_nested_anchors_refuse_section_without_partial_links(self):
        doc = synthetic()
        doc["parse"]["text"] = doc["parse"]["text"].replace("حدث أصلي", "<a href='/wiki/A'>حدث <a href='/wiki/B'>أصلي</a></a>")
        section = parse(doc).section("events")
        self.assertEqual(section.failure, Failure.EXTRACTION)
        self.assertEqual(section.entries, ())


class FakeProvider:
    def __init__(self):
        self.calls = 0
        self.block = False
        self.entered, self.release = threading.Event(), threading.Event()
        self.error = None
        self.threads = []

    def fetch(self, day, language, token):
        self.calls += 1
        self.threads.append(threading.get_ident())
        self.entered.set()
        if self.block and not self.release.wait(5):
            raise AssertionError("test did not release worker")
        if self.error:
            raise self.error
        return parse_document(fixture("ar_0.json" if language == "ar" else "en_3.json"), day, language)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = DayCache(Path(self.temp.name) / "on_this_day.json")
        self.provider = FakeProvider()
        self.day, self.lang, self.clock = date(2026, 11, 11), "ar", 0
        self.dispatched = []
        self.dispatch_event = threading.Event()
        self.service = self.make_service()
        self.addCleanup(self.service.close)

    def make_service(self):
        def dispatch(callback):
            self.dispatched.append(callback)
            self.dispatch_event.set()
        return OnThisDayService(self.provider, self.cache, language=lambda: self.lang,
                               today=lambda: self.day, dispatch=dispatch, monotonic=lambda: self.clock)

    def get(self, service=None):
        return (service or self.service).request().result(timeout=5)

    def test_memory_then_disk_restore_without_network(self):
        first = self.get()
        self.assertEqual(first, self.get())
        second = self.make_service()
        self.addCleanup(second.close)
        self.assertEqual(first, self.get(second))
        self.assertEqual(self.provider.calls, 1)
        self.assertNotEqual(self.provider.threads[0], threading.get_ident())

    def test_twenty_simultaneous_calls_share_one_request(self):
        self.provider.block = True
        with ThreadPoolExecutor(max_workers=8) as executor:
            requests = list(executor.map(lambda _: self.service.request(), range(20)))
        self.assertTrue(self.provider.entered.wait(2))
        self.provider.release.set()
        values = [future.result(5) for future in requests]
        self.assertTrue(all(value == values[0] for value in values))
        self.assertEqual(self.provider.calls, 1)

    def test_cancelled_subscriber_does_not_cancel_other_subscribers(self):
        self.provider.block = True
        cancelled = self.service.request()
        kept = self.service.request()
        self.assertTrue(self.provider.entered.wait(2))
        self.assertTrue(cancelled.cancel())
        self.provider.release.set()
        self.assertEqual(kept.result(5).language, "ar")
        self.assertTrue(cancelled.cancelled())
        self.assertEqual(self.provider.calls, 1)

    def test_date_language_aba_change_never_revives_obsolete_generation(self):
        self.provider.block = True
        old = self.service.request()
        self.assertTrue(self.provider.entered.wait(2))
        self.lang = "en"
        middle = self.service.request()
        self.lang = "ar"
        current = self.service.request()
        self.provider.release.set()
        for future in (old, middle):
            with self.assertRaises(OnThisDayError) as caught:
                future.result(5)
            self.assertEqual(caught.exception.kind, Failure.STALE)
        self.assertEqual(current.result(5).language, "ar")

    def test_cache_io_and_analysis_are_on_temporary_worker_only(self):
        threads = []
        original_load, original_save = self.cache.load, self.cache.save
        def load(*args):
            threads.append(threading.get_ident())
            return original_load(*args)
        def save(*args):
            threads.append(threading.get_ident())
            return original_save(*args)
        with patch.object(self.cache, "load", side_effect=load), patch.object(self.cache, "save", side_effect=save):
            self.get()
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(t != threading.get_ident() for t in threads))

    def test_day_month_year_and_language_changes_invalidate(self):
        self.get()
        for day in (date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 31), date(2027, 1, 1), date(2028, 2, 29)):
            self.day = day
            self.assertEqual(self.get().local_date, day)
        self.lang = "en"
        self.assertEqual(self.get().language, "en")
        self.assertEqual(self.provider.calls, 7)

    def test_date_change_during_fetch_suppresses_old_result(self):
        self.provider.block = True
        delivered = []
        future = self.service.request(delivered.append)
        self.assertTrue(self.provider.entered.wait(2))
        self.day = date(2026, 11, 12)
        self.provider.release.set()
        with self.assertRaises(OnThisDayError) as caught:
            future.result(5)
        self.assertEqual(caught.exception.kind, Failure.STALE)
        self.assertEqual(delivered, [])
        self.assertEqual(self.get().local_date, self.day)

    def test_language_change_during_fetch_and_new_request(self):
        self.provider.block = True
        future = self.service.request()
        self.assertTrue(self.provider.entered.wait(2))
        self.lang = "en"
        new_future = self.service.request()
        self.provider.release.set()
        with self.assertRaises(OnThisDayError):
            future.result(5)
        self.assertEqual(new_future.result(5).language, "en")
        self.assertEqual(self.provider.calls, 2)

    def test_delayed_dispatch_rechecks_date_and_close(self):
        values = []
        self.service.request(values.append).result(5)
        self.assertTrue(self.dispatch_event.wait(2))
        self.day = date(2026, 11, 12)
        self.dispatched.pop()()
        self.assertEqual(values, [])
        self.dispatch_event.clear()
        self.service.request(values.append).result(5)
        self.assertTrue(self.dispatch_event.wait(2))
        self.service.close()
        self.dispatched.pop()()
        self.assertEqual(values, [])

    def test_callback_delivered_only_via_dispatch(self):
        values = []
        expected = self.service.request(values.append).result(5)
        self.assertTrue(self.dispatch_event.wait(2))
        self.assertEqual(values, [])
        self.dispatched.pop()()
        self.assertEqual(values, [expected])

    def test_close_cancels_active_and_future_requests(self):
        self.provider.block = True
        future = self.service.request()
        self.assertTrue(self.provider.entered.wait(2))
        self.service.close()
        self.provider.release.set()
        for pending in (future, self.service.request()):
            with self.assertRaises(OnThisDayError) as caught:
                pending.result(5)
            self.assertEqual(caught.exception.kind, Failure.CANCELLED)

    def test_failure_cooldown_no_retry_loop_and_explicit_retry(self):
        self.provider.error = OnThisDayError(Failure.RATE_LIMIT, "429", retry_after=120)
        for clock in (0, 1, 119):
            self.clock = clock
            with self.assertRaises(OnThisDayError) as caught:
                self.get()
            self.assertEqual(caught.exception.kind, Failure.RATE_LIMIT)
        self.assertEqual(self.provider.calls, 1)
        self.clock = 121
        self.provider.error = None
        self.get()
        self.assertEqual(self.provider.calls, 2)

    def test_confirmed_missing_page_is_persisted_but_connection_failure_is_not(self):
        self.provider.error = OnThisDayError(Failure.UNAVAILABLE, "missingtitle")
        with self.assertRaises(OnThisDayError):
            self.get()
        second = self.make_service()
        self.addCleanup(second.close)
        with self.assertRaises(OnThisDayError) as caught:
            self.get(second)
        self.assertEqual(caught.exception.kind, Failure.UNAVAILABLE)
        self.assertEqual(self.provider.calls, 1)

    def test_network_failure_never_creates_absence_cache(self):
        self.provider.error = OnThisDayError(Failure.CONNECTION, "offline")
        with self.assertRaises(OnThisDayError):
            self.get()
        self.assertFalse(self.cache.path.exists())

    def test_corrupt_cache_recovered_and_storage_diagnostic_retained(self):
        self.cache.path.write_text("{broken", encoding="utf-8")
        self.get()
        self.assertEqual(self.service.storage_error.kind, Failure.STORAGE)
        self.assertEqual(self.provider.calls, 1)
        self.assertIsNotNone(self.cache.load(self.day, self.lang))

    def test_write_failure_keeps_success_in_memory(self):
        with patch.object(self.cache, "save", side_effect=OnThisDayError(Failure.STORAGE, "disk full")):
            first = self.get()
        self.assertEqual(self.service.storage_error.kind, Failure.STORAGE)
        self.assertEqual(self.get(), first)
        self.assertEqual(self.provider.calls, 1)

    def test_schema_mismatch_or_previous_day_never_used_as_today(self):
        self.get()
        raw = json.loads(self.cache.path.read_text(encoding="utf-8"))
        for field, value in (("schema", 99), ("date", "2026-11-10"), ("language", "en")):
            changed = deepcopy(raw)
            changed[field] = value
            self.cache.path.write_text(json.dumps(changed), encoding="utf-8")
            self.assertIsNone(self.cache.load(self.day, self.lang))

    def test_semantically_corrupt_cache_is_rejected(self):
        self.get()
        raw = json.loads(self.cache.path.read_text(encoding="utf-8"))
        raw["day"]["sections"][0]["entries"] = []
        self.cache.path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(OnThisDayError) as caught:
            self.cache.load(self.day, self.lang)
        self.assertEqual(caught.exception.kind, Failure.STORAGE)

    def test_cache_preserves_links_and_rejects_tampered_destinations_or_spans(self):
        first = self.get()
        self.assertEqual(self.cache.load(self.day, self.lang), first)
        raw = json.loads(self.cache.path.read_text(encoding="utf-8"))
        link = raw["day"]["sections"][0]["entries"][0]["links"][0]
        original = deepcopy(link)
        for field, bad in (("url", "javascript:alert(1)"), ("text", "wrong label"), ("start", -1)):
            link.update(original)
            link[field] = bad
            self.cache.path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(OnThisDayError) as caught:
                self.cache.load(self.day, self.lang)
            self.assertEqual(caught.exception.kind, Failure.STORAGE)

    def test_interrupted_atomic_replace_preserves_old_file(self):
        first = self.get()
        before = self.cache.path.read_bytes()
        with patch("addon.globalPlugins.awqati.infrastructure.on_this_day_cache.os.replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OnThisDayError):
                self.cache.save(self.day, self.lang, first)
        self.assertEqual(before, self.cache.path.read_bytes())
        self.assertEqual(list(self.cache.path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
