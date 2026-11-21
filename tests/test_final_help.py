"""Help fidelity and accessibility against the owner's approved Word guide."""
import ast
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = json.loads((ROOT / 'docs/help_822_verification.json').read_text('utf8'))


class GuideParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.blocks, self.links = [], [], []
        self.attributes, self.current, self.parts = {}, None, []
        self.levels, self.list_sizes = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.attributes = attrs
        if tag not in ('meta', 'br', 'hr', 'img', 'input', 'link'):
            self.stack.append(tag)
        if re.fullmatch(r'h[1-6]', tag) or tag in ('p', 'li'):
            assert self.current is None, (self.current, tag)
            self.current, self.parts = tag, []
        if tag == 'ul':
            self.list_sizes.append(0)
        if tag == 'li':
            self.list_sizes[-1] += 1
        if tag == 'br':
            self.parts.append('\n')
        if 'href' in attrs:
            self.links.append(attrs['href'])
        if re.fullmatch(r'h[1-6]', tag):
            self.levels.append(int(tag[1]))

    def handle_data(self, value):
        if self.current:
            self.parts.append(value)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, tag
        if tag == self.current:
            self.blocks.append((tag, ''.join(self.parts)))
            self.current, self.parts = None, []


def parse_guide(language):
    parser = GuideParser()
    parser.feed((ROOT / f'addon/doc/{language}/readme.html').read_text('utf8'))
    return parser


class FinalHelpTests(unittest.TestCase):
    def test_all_word_paragraphs_survive_in_order_with_exact_text(self):
        for language in ('ar', 'en'):
            with self.subTest(language=language):
                parser = parse_guide(language)
                expected = EVIDENCE['languages'][language]['paragraph_records']
                self.assertEqual(len(parser.blocks), 740)
                self.assertEqual(len(parser.blocks), len(expected))
                for index, ((tag, text), record) in enumerate(zip(parser.blocks, expected)):
                    self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), record['sha256'], (language, index, text))
                    expected_tag = 'h' + str(record['level']) if record['level'] else 'li' if record['list'] else 'p'
                    self.assertEqual(tag, expected_tag, (language, index))

    def test_semantic_outline_lists_links_and_language_match(self):
        parsers = [parse_guide(language) for language in ('ar', 'en')]
        for language, direction, parser in zip(('ar','en'), ('rtl','ltr'), parsers):
            self.assertEqual(parser.stack, [])
            self.assertEqual(parser.attributes, {'lang':language, 'dir':direction})
            self.assertEqual(parser.levels.count(1), 22)
            self.assertEqual(parser.levels.count(2), 184)
            self.assertEqual(set(parser.levels), {1, 2})
            self.assertEqual(sum(parser.list_sizes), 145)
            self.assertTrue(all(b <= a + 1 for a,b in zip(parser.levels,parser.levels[1:])))
            self.assertCountEqual(parser.links,EVIDENCE['languages'][language]['links'])
            for href in parser.links:
                target = urlsplit(href)
                self.assertIn(target.scheme, ('https', 'mailto'))
                if target.scheme == 'mailto':
                    self.assertRegex(target.path, r'^[^\s@]+@[^\s@]+$')
                else:
                    self.assertTrue(target.netloc)
        self.assertEqual(parsers[0].levels, parsers[1].levels)
        self.assertEqual(parsers[0].list_sizes, parsers[1].list_sizes)
        self.assertEqual(parsers[0].links, parsers[1].links)

    def test_canonical_sources_and_generated_html_match(self):
        from tools.build_release_docs import markdown_to_html
        for language, source, direction, title in (
            ('ar', 'دليل_أوقاتي_العربي_المعتمد.md', 'rtl', 'دليل استخدام أوقاتي 8.2.2'),
            ('en', 'awqati_user_guide_en.md', 'ltr', 'Awqati 8.2.2 user guide'),
        ):
            markdown = (ROOT / f'addon/doc/{language}/readme.md').read_text('utf8')
            self.assertEqual(markdown, (ROOT / 'docs' / source).read_text('utf8'))
            self.assertEqual(markdown_to_html(markdown, lang=language, direction=direction, title=title),
                             (ROOT / f'addon/doc/{language}/readme.html').read_text('utf8'))

    def test_every_current_default_is_in_the_shortcut_reference(self):
        tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf8'))
        gestures = [n.value.value.split(':',1)[1].lower().replace('control','ctrl')
                    for n in ast.walk(tree) if isinstance(n,ast.keyword) and n.arg == 'gesture']
        references = []
        for language, start, end in (
            ('ar', '# اختصارات لوحة المفاتيح', '# المساهمة والتواصل'),
            ('en', '# Keyboard Shortcuts', '# Contributing and Contact'),
        ):
            text = (ROOT / f'addon/doc/{language}/readme.md').read_text('utf8').replace('**','')
            section = text[text.index(start):text.index(end)].replace('**','')
            labels = re.findall(r'^- (NVDA\+[^:]+):', section, re.M)
            normalized = [label.lower() for label in labels]
            self.assertEqual(sorted(normalized), sorted(gestures))
            self.assertEqual(len(normalized), len(set(normalized)))
            self.assertEqual(len(re.findall(r'^## ',section,re.M)),14)
            references.append(normalized)
        self.assertEqual(*references)

    def test_single_release_line_and_no_missing_english_translation(self):
        ar = (ROOT / 'addon/doc/ar/readme.md').read_text('utf8')
        self.assertEqual(ar.count(EVIDENCE['added_arabic_line']), 1)
        self.assertLess(ar.index('الإصدار 8.2.2:'),ar.index('الإصدار 8.2.1'))
        en = (ROOT / 'addon/doc/en/readme.md').read_text('utf8').replace('**','')
        self.assertNotRegex(en, r'[\u0600-\u06ff]')
        self.assertIn('## Version 8.2.2:',en)
        self.assertTrue(EVIDENCE['arabic_only_exact_insertion'])

    def test_help_entrypoint_and_functional_version_remain_unchanged(self):
        from test_release_package import _addon_info
        self.assertEqual(_addon_info()['addon_docFileName'], 'readme.html')
        self.assertEqual(hashlib.sha256((ROOT/'buildVars.py').read_bytes().replace(b'"addon_version": "8.2.2"', b'"addon_version": "8.2.1"')).hexdigest(),
                         EVIDENCE['unchanged_buildvars_sha256'])
        self.assertEqual({p.name for p in (ROOT/'addon/doc').iterdir() if p.is_dir()}, {'ar','en'})

    def test_help_has_no_internal_script_names_or_development_instructions(self):
        tree = ast.parse((ROOT/'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf8'))
        names = [n.name[7:] for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('script_')]
        for language in ('ar','en'):
            text = (ROOT/f'addon/doc/{language}/readme.html').read_text('utf8')
            self.assertNotIn('Task 1.1',text)
            self.assertNotIn('5.0.0-dev10',text)
            for name in names:
                self.assertNotIn('<code>'+name+'</code>',text)
