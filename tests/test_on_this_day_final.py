"""Stable-release HTML and real service/presentation cache regression checks."""
from collections import Counter
from datetime import timedelta
import gettext
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from test_on_this_day import CASES, FakeProvider, synthetic
from test_on_this_day_presentation import sample, Document
import test_on_this_day_presentation as presentation_tests
from addon.globalPlugins.awqati.application.on_this_day import OnThisDayService
from addon.globalPlugins.awqati.application.on_this_day_presentation import OnThisDayPresentation
from addon.globalPlugins.awqati.infrastructure.on_this_day_cache import DayCache
from addon.globalPlugins.awqati.infrastructure.on_this_day_html import render_html
from addon.globalPlugins.awqati.infrastructure.on_this_day_wikipedia import parse_document


class FinalHtmlTests(unittest.TestCase):
    def test_every_capture_has_flat_history_and_exact_counts_and_link_order(self):
        for name, day, _ in CASES:
            record = sample(name, day)
            for key in ('events', 'births', 'deaths'):
                with self.subTest(name=name, section=key):
                    entries = record.section(key).entries
                    html = render_html(record, key, str)
                    doc = Document(html)
                    self.assertEqual(len(doc.items), len(entries))
                    self.assertEqual(sum(t == 'ul' for t, _ in doc.tags), 1)
                    self.assertFalse(any(t == 'h2' for t, _ in doc.tags))
                    unit = 'events' if key == 'events' else 'people'
                    self.assertIn(f': {len(entries)} {unit}', html)
                    expected = []
                    for entry, item in zip(entries, doc.items):
                        self.assertIn(entry.text, item)
                        self.assertIn(entry.year, item)
                        for context in entry.context:
                            self.assertIn(context.text, item)
                            expected.extend((link.url, link.text) for link in context.links)
                        expected.extend((link.url, link.text) for link in entry.links)
                    self.assertEqual(doc.anchors[:-1], expected)
                    self.assertEqual(doc.anchors[-1][0], record.source_url)

    def test_observance_groups_are_headings_and_only_leaves_are_counted(self):
        for name, date, _ in CASES:
            record = sample(name, date)
            html = render_html(record, 'observances', str)
            doc = Document(html)
            entries = record.section('observances').entries
            # Independently identify parents from descendant contexts.
            groups = {c.text for e in entries for c in e.context}
            leaves = [e for e in entries if e.text not in groups]
            self.assertEqual(doc.items, [e.text for e in leaves])
            self.assertIn(f': {len(leaves)} observances', html)
            expected = Counter((l.url, l.text) for e in entries for l in e.links)
            self.assertEqual(Counter(doc.anchors[:-1]), expected)
            self.assertEqual(sum(t == 'section' for t, _ in doc.tags), len(groups))

    def test_synthetic_shared_year_and_group_preserve_every_original_link(self):
        record = parse_document(synthetic(), sample().local_date, 'ar')
        doc = Document(render_html(record, 'births', str))
        self.assertEqual(doc.items, ['1900 – شخص أول', '1900 – شخص ثان'])
        doc = Document(render_html(record, 'observances', str))
        self.assertEqual(doc.items, ['بلد أول', 'بلد ثان'])
        self.assertIn('Holidays and observances: 2 observances', ''.join(doc.text))

    def test_arabic_catalog_wait_and_summary(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.build-deps'))
        from babel.messages.pofile import read_po
        from babel.messages.mofile import write_mo
        root = Path(__file__).resolve().parents[1]
        with (root / 'addon/locale/ar/LC_MESSAGES/nvda.po').open(encoding='utf8') as stream:
            catalog = read_po(stream)
        data = BytesIO()
        write_mo(data, catalog)
        data.seek(0)
        tr = gettext.GNUTranslations(data).gettext
        self.assertEqual(tr('Please wait.'), 'يُرْجَى الانتظار')
        html = render_html(sample(), 'events', tr)
        self.assertIn('الأحداث التاريخية، 17 حدثًا', html)


class WaitTests(unittest.TestCase):
    setUp = presentation_tests.SelectionTests.setUp
    schedule = presentation_tests.SelectionTests.schedule
    # Reuse the existing deterministic scheduler and callback harness.
    def test_immediate_results_are_silent_in_both_modes_even_before_web_settles(self):
        for web in (False, True):
            self.web = web
            self.presenter.select('events')
            self.callbacks[-1](self.day)
            self.wait_timers[-1].callback()
        self.assertEqual(self.messages, [])

    def test_slow_request_announces_once_across_section_changes(self):
        for key in ('events', 'births', 'deaths', 'observances'):
            self.presenter.select(key)
            self.wait_timers[-1].callback()
        self.assertEqual(self.messages, ['Please wait.'])

    def test_old_wait_callbacks_are_guarded_on_language_date_mode_and_close(self):
        for attribute, value in (('language', 'en'), ('date', self.date + timedelta(days=1)), ('web', True)):
            self.presenter.select('events')
            previous = getattr(self, attribute)
            setattr(self, attribute, value)
            self.wait_timers[-1].callback()
            setattr(self, attribute, previous)
        self.presenter.select('events')
        self.presenter.close()
        self.wait_timers[-1].callback()
        self.assertEqual(self.messages, [])


class CachePresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = FakeProvider()
        self.date, self.lang = sample().local_date, 'ar'
        self.cache = DayCache(Path(self.temp.name) / 'day.json')
        self.queue, self.timers, self.messages, self.spoken = [], [], [], []
        self.ready = threading.Event()
        self.new_presenter()

    def new_presenter(self):
        def dispatch(callback):
            self.queue.append(callback)
            self.ready.set()
        self.service = OnThisDayService(self.provider, self.cache, today=lambda: self.date,
            language=lambda: self.lang, dispatch=dispatch)
        self.addCleanup(self.service.close)
        def schedule(ms, callback):
            timer = Mock(callback=callback, ms=ms)
            self.timers.append(timer)
            return timer
        self.presenter = OnThisDayPresentation(self.service, today=lambda: self.date,
            language=lambda: self.lang, web_mode=lambda: False, translate=str,
            schedule=schedule, settle_ms=lambda: 600, speak=self.spoken.append,
            stop_speech=lambda: None, message=self.messages.append, open_page=Mock())

    def select(self, key):
        self.ready.clear()
        self.presenter.select(key)
        self.assertTrue(self.ready.wait(5))
        self.queue.pop(0)()
        # Simulate even an already queued, cancelled wx timer.
        self.timers[-1].callback()

    def test_new_day_four_sections_and_repeats_use_one_fetch_then_memory(self):
        with patch.object(self.cache, 'load', wraps=self.cache.load) as load:
            for key in ('events', 'births', 'deaths', 'observances', 'events', 'events'):
                self.select(key)
            self.assertEqual(self.provider.calls, 1)
            self.assertEqual(load.call_count, 1)
        self.assertEqual(len(self.spoken), 6)
        self.assertEqual(self.messages, [])

    def test_fast_disk_restore_after_service_recreation_is_silent(self):
        self.select('events')
        self.service.close()
        self.new_presenter()
        with patch.object(self.cache, 'load', wraps=self.cache.load) as load:
            self.select('births')
            self.assertEqual(load.call_count, 1)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(self.messages, [])

    def test_date_and_language_fetch_new_records_without_old_results(self):
        self.select('events')
        self.date += timedelta(days=1)
        self.select('births')
        self.lang = 'en'
        self.select('deaths')
        self.assertEqual(self.provider.calls, 3)
        self.assertIn(str(self.date.year), self.spoken[-1][0])
        self.assertTrue(self.spoken[-1][0].endswith('Deaths'))
        self.assertEqual(self.messages, [])
