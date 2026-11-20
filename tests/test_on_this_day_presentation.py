"""Offline presentation acceptance using all six task-1 captures."""
import ast
from dataclasses import replace
from datetime import date, timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from addon.globalPlugins.awqati.application.on_this_day_presentation import (
    OnThisDayPresentation, section_tree, speech_lines, ERRORS,
)
from addon.globalPlugins.awqati.domain.on_this_day import Entry, Link, Failure, OnThisDayError, SECTION_KEYS
from addon.globalPlugins.awqati.domain.settings import default_settings, validate_settings
from addon.globalPlugins.awqati.infrastructure.on_this_day_html import render_html
from addon.globalPlugins.awqati.infrastructure.on_this_day_pages import LocalDayPages
from addon.globalPlugins.awqati.infrastructure.on_this_day_wikipedia import parse_document
from addon.globalPlugins.awqati.infrastructure.settings_repository import JsonSettingsRepository
from test_on_this_day import CASES, FIXTURES, synthetic

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py'


def sample(name='ar_0.json', day=date(2026, 11, 11)):
    return parse_document(json.loads((FIXTURES / name).read_text('utf8')), day, name[:2])


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags, self.text, self.anchors, self.stack = [], [], [], []
        self.current_anchor = None
        self.li_stack, self.items = [], []
        self.feed(text)
        if self.stack:
            raise AssertionError(self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag not in {'meta'}:
            self.stack.append(tag)
        if tag == 'li':
            self.li_stack.append([])
        if tag == 'a':
            self.current_anchor = [attrs['href'], '']

    def handle_endtag(self, tag):
        if self.stack.pop() != tag:
            raise AssertionError('unbalanced HTML')
        if tag == 'li':
            self.items.append(''.join(self.li_stack.pop()))
        if tag == 'a':
            self.anchors.append(tuple(self.current_anchor))
            self.current_anchor = None

    def handle_data(self, text):
        self.text.append(text)
        if self.li_stack:
            self.li_stack[-1].append(text)
        if self.current_anchor is not None:
            self.current_anchor[1] += text


class RenderTests(unittest.TestCase):
    def test_all_six_fixtures_all_sections_all_text_and_links(self):
        for name, day, counts in CASES:
            record = sample(name, day)
            for key in SECTION_KEYS:
                with self.subTest(name=name, key=key):
                    doc = Document(render_html(record, key, lambda s: s))
                    self.assertEqual(sum(tag == 'h1' for tag, _ in doc.tags), 1)
                    self.assertTrue({'main', 'ul', 'li'} <= {t for t, _ in doc.tags})
                    html = next(attrs for tag, attrs in doc.tags if tag == 'html')
                    self.assertEqual(html, {'lang': name[:2], 'dir': 'rtl' if name[:2] == 'ar' else 'ltr'})
                    sequence = speech_lines(record, key, lambda s: s)[1:]
                    for entry in record.section(key).entries:
                        self.assertTrue(entry.text in "".join(doc.text))
                        self.assertIn(entry.text, sequence)
                        for context in entry.context:
                            self.assertIn(context.text, "".join(doc.text))
                        for link in entry.links:
                            self.assertIn((link.url, link.text), doc.anchors)
                    self.assertFalse(any('https://' in line for line in sequence))
                    self.assertFalse({'script', 'iframe', 'object', 'embed', 'img', 'style'} & {t for t, _ in doc.tags})

    def test_context_is_nested_and_not_repeated(self):
        day = parse_document(synthetic(), date(2026, 11, 11), 'ar')
        tree = section_tree(day, 'births')
        self.assertEqual(len(tree), 1)
        self.assertEqual(len(tree[0][2]), 2)
        self.assertEqual(speech_lines(day, 'births', str)[1:], ['1900 –', 'شخص أول', 'شخص ثان'])
        tree = section_tree(day, 'observances')
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0][0], 'مناسبة')
        self.assertEqual(len(tree[0][2]), 2)

    def test_hostile_text_and_invalid_destinations_are_inert(self):
        day = sample()
        text = '<script>alert("x")</script> malicious article'
        for url in ('javascript:alert(1)', 'data:text/html,bad', 'file:///C:/bad.exe',
                    'https://ar.wikipedia.org.evil.test/wiki/Fake'):
            entry = Entry(text, '2026', (), (Link(text, url, 0, len(text)),))
            section = replace(day.section('events'), entries=(entry,))
            altered = replace(day, sections=(section,))
            html = render_html(altered, 'events', str)
            doc = Document(html)
            self.assertIn('&lt;script&gt;', html)
            self.assertFalse(any(tag == 'script' for tag, _ in doc.tags))
            self.assertEqual(len(doc.anchors), 1)  # original source only

    def test_link_offsets_and_duplicate_labels(self):
        day = sample()
        entry = Entry('same same', '2000', (), (
            Link('same', 'https://ar.wikipedia.org/wiki/First', 0, 4),
            Link('same', 'https://ar.wikipedia.org/wiki/Second', 5, 9),
            Link('wrong', 'https://ar.wikipedia.org/wiki/Wrong', 0, 5)))
        day = replace(day, sections=(replace(day.section('events'), entries=(entry,)),))
        doc = Document(render_html(day, 'events', str))
        self.assertEqual(doc.anchors[:2], [('https://ar.wikipedia.org/wiki/First', 'same'),
                                          ('https://ar.wikipedia.org/wiki/Second', 'same')])
        self.assertEqual(speech_lines(day, 'events', str)[1:], ['same same'])

    def test_failed_section_never_renders_partial_data(self):
        day = sample()
        for failure in (Failure.UNAVAILABLE, Failure.EXTRACTION):
            altered = replace(day, sections=(replace(day.section('events'), failure=failure),))
            for renderer in (render_html, speech_lines):
                with self.assertRaises(OnThisDayError):
                    renderer(altered, 'events', str)

    def test_pages_are_utf8_and_bounded_and_opened_as_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            opened = []
            pages = LocalDayPages(directory, opened.append)
            day = replace(sample(), title='../bad <title>')
            path = pages.open(day, 'events', str)
            self.assertEqual(path.name, 'ar-events.html')
            self.assertEqual(opened, [str(path.resolve())])
            self.assertIn('dir="rtl"', path.read_text('utf8'))
            pages.open(day, 'events', str)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.day = sample()
        self.date = self.day.local_date
        self.language = 'ar'
        self.web = False
        self.callbacks = []
        self.timers = []
        self.wait_timers = []
        self.spoken, self.opened, self.messages = [], [], []
        self.service = Mock()
        self.service.request.side_effect = self.callbacks.append
        self.presenter = OnThisDayPresentation(self.service, language=lambda: self.language,
            today=lambda: self.date, web_mode=lambda: self.web, translate=str,
            schedule=self.schedule, settle_ms=lambda: 600, speak=self.spoken.append,
            stop_speech=Mock(), message=self.messages.append,
            open_page=lambda day, key, tr: self.opened.append(key))

    def schedule(self, ms, callback):
        self.assertIn(ms, (600, 800))
        timer = Mock(callback=callback)
        (self.wait_timers if ms == 800 else self.timers).append(timer)
        return timer

    def test_four_choices_and_fifth_repeat_last_via_existing_dispatch(self):
        source = PLUGIN.read_text('utf8')
        tree = ast.parse(source)
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'script_onThisDay')
        self.assertIn('self._press', ast.get_source_segment(source, method))
        self.assertIn('kb:NVDA+windows+f12', source)
        for key in SECTION_KEYS:
            self.presenter.select(key)
            self.callbacks[-1](self.day)
            self.assertEqual(self.spoken[-1], speech_lines(self.day, key, str))
        self.assertEqual(len(self.spoken), 4)

    def test_rapid_web_presses_pending_network_open_only_final_section(self):
        self.web = True
        for key in SECTION_KEYS:
            self.presenter.select(key)
        for callback in self.callbacks:
            callback(self.day)
        for timer in self.timers:  # even a cancelled timer already queued cannot publish
            timer.callback()
        self.assertEqual(self.opened, ['observances'])
        self.assertTrue(all(t.Stop.called for t in self.timers[:-1]))

    def test_rapid_web_presses_cached_results_open_only_final_section(self):
        self.web = True
        for key in SECTION_KEYS:
            self.presenter.select(key)
            self.callbacks[-1](self.day)
        self.assertEqual(self.opened, [])
        for timer in self.timers:
            timer.callback()
        self.assertEqual(self.opened, ['observances'])

    def test_late_callback_does_not_speak_previous_section(self):
        self.presenter.select('events')
        self.presenter.select('births')
        self.callbacks[1](self.day)
        self.callbacks[0](self.day)
        self.assertEqual(self.spoken, [speech_lines(self.day, 'births', str)])
        self.assertEqual(self.presenter.stop_speech.call_count, 2)

    def test_date_language_and_mode_changes_invalidate_callbacks(self):
        for change in ('date', 'language', 'web'):
            self.presenter.select('events')
            old = getattr(self, change)
            setattr(self, change, {'date': self.date + timedelta(days=1), 'language': 'en', 'web': True}[change])
            self.callbacks[-1](self.day)
            setattr(self, change, old)
        self.assertEqual(self.spoken, [])
        self.assertEqual(self.opened, [])

    def test_all_errors_reported_without_opening_page(self):
        self.web = True
        for kind, message in ERRORS.items():
            self.presenter.select('events')
            self.callbacks[-1](OnThisDayError(kind, 'error'))
            self.timers[-1].callback()
            self.assertEqual(self.messages[-1], message)
        self.assertEqual(self.opened, [])

    def test_close_invalidates_pending_timer_and_results(self):
        self.web = True
        self.presenter.select('events')
        self.presenter.close()
        self.callbacks[-1](self.day)
        self.timers[-1].callback()
        self.assertEqual(self.opened, [])
        self.service.close.assert_called_once()
        self.timers[-1].Stop.assert_called_once()


class SettingsAndGesturesTests(unittest.TestCase):
    def test_native_2026_repeat_engines_choose_four_sections_and_repeat_fourth(self):
        from types import SimpleNamespace as NS
        import sys
        import weakref
        from unittest.mock import patch
        from test_multi_press_execution import plugin_driver
        for version in ('2026.1', '2026.2', '2026.3'):
            driver, _ = plugin_driver()
            chosen = []
            driver._on_this_day = NS(select=chosen.append)
            source = ROOT / f'development_baseline/multipress-audit/{version}/scriptHandler.py'
            nodes = [n for n in ast.parse(source.read_text('utf8')).body
                     if isinstance(n, ast.FunctionDef) and n.name in {'executeScript', 'getLastScriptRepeatCount'}]
            clock = [100.0]
            errors = []
            namespace = dict(_lastScriptRef=None, _isScriptRunning=False, _lastScriptTime=0, _lastScriptCount=0,
                time=NS(time=lambda: clock[0]), weakref=weakref,
                config=NS(conf={'keyboard': {'multiPressTimeout': 500}}),
                willSayAllResume=lambda gesture: False,
                log=NS(exception=lambda *args: errors.append(args)))
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
            with patch.dict(sys.modules, scriptHandler=NS(getLastScriptRepeatCount=namespace['getLastScriptRepeatCount'])):
                for _ in range(6):
                    clock[0] += .1
                    namespace['executeScript'](driver.script_onThisDay, NS(displayName='On This Day'))
                self.assertEqual(chosen, ['events', 'births', 'deaths', 'observances', 'observances', 'observances'])
                clock[0] += 1
                namespace['executeScript'](driver.script_onThisDay, NS(displayName='On This Day'))
                self.assertEqual(chosen[-1], 'events')
            self.assertFalse(errors)

    def test_default_old_file_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            repo = JsonSettingsRepository(path)
            settings = repo.load()
            self.assertFalse(settings.calendar.on_this_day_web_page)
            repo.save(settings)
            original = json.loads(path.read_text('utf8'))
            del original['calendar']['onThisDayWebPage']
            path.write_text(json.dumps(original), encoding='utf8')
            before = path.read_bytes()
            self.assertFalse(repo.load().calendar.on_this_day_web_page)
            self.assertEqual(path.read_bytes(), before)
            settings.calendar.on_this_day_web_page = True
            repo.save(settings)
            self.assertEqual(repo.load(), settings)
            settings.calendar.on_this_day_web_page = 'false'
            with self.assertRaises(ValueError):
                validate_settings(settings)

    def test_existing_default_gestures_unchanged_and_new_one_unique(self):
        import subprocess
        previous = subprocess.check_output(['git', 'show', 'HEAD:addon/globalPlugins/awqati/nvda_adapter/plugin.py'], cwd=ROOT).decode('utf8')
        def gestures(source):
            result = {}
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call):
                            for keyword in decorator.keywords:
                                if keyword.arg == 'gesture':
                                    result[node.name] = ast.literal_eval(keyword.value).casefold()
            return result
        old, new = gestures(previous), gestures(PLUGIN.read_text('utf8'))
        self.assertTrue(old.items() <= new.items())
        self.assertEqual(len(new.values()), len(set(new.values())))
        self.assertEqual(new['script_onThisDay'], 'kb:nvda+windows+f12')


if __name__ == '__main__':
    unittest.main()
