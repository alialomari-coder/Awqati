"""Release help must cover live default commands in accessible HTML and Markdown."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class FinalHelpTests(unittest.TestCase):
    def test_time_tools_are_inside_clock_in_matching_order(self):
        for language, labels in (
            ('ar', ('الساعة', 'أدوات الوقت الأربع', 'المنبهات', 'المؤقتات', 'ساعة الإيقاف', 'الساعة العالمية', 'التقويم')),
            ('en', ('Clock', 'The four time tools', 'Alarms', 'Timers', 'Stopwatch', 'World clock', 'Calendar')),
        ):
            text = (ROOT / f'addon/doc/{language}/readme.md').read_text('utf8')
            headings = [('## ' if i in (0, 6) else '### ') + label
                        for i, label in enumerate(labels)]
            positions = [text.index('\n' + heading + '\n') for heading in headings]
            self.assertEqual(sorted(positions), positions)
            shortcut_section = text[text.index('# اختصارات لوحة المفاتيح المعتمدة' if language == 'ar' else '# Approved keyboard shortcuts'):]
            categories = (('اختصارات المنبهات', 'اختصارات المؤقتات', 'اختصارات ساعة الإيقاف', 'اختصارات الساعة العالمية')
                          if language == 'ar' else ('Alarm shortcuts', 'Timer shortcuts', 'Stopwatch shortcuts', 'World-clock shortcuts'))
            positions = [shortcut_section.index('## ' + label + '\n') for label in categories]
            self.assertEqual(sorted(positions), positions)

    def test_semantic_outline_links_and_bilingual_structure(self):
        outlines, links = [], []

        class GuideParser(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack, self.levels, self.links, self.ids = [], [], [], []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag not in ('meta', 'br', 'hr', 'img', 'input', 'link'):
                    self.stack.append(tag)
                if re.fullmatch(r'h[1-6]', tag):
                    self.levels.append(int(tag[1]))
                if 'href' in attrs:
                    self.links.append(attrs['href'])
                if 'id' in attrs:
                    self.ids.append(attrs['id'])

            def handle_endtag(self, tag):
                assert self.stack and self.stack.pop() == tag, tag

        for language in ('ar', 'en'):
            path = ROOT / f'addon/doc/{language}/readme.html'
            parser = GuideParser()
            parser.feed(path.read_text('utf8'))
            self.assertEqual(parser.stack, [])
            self.assertEqual(parser.levels[0], 1)
            self.assertTrue(set(parser.levels) == {1, 2, 3})
            self.assertTrue(all(b <= a + 1 for a, b in zip(parser.levels, parser.levels[1:])))
            self.assertEqual(len(parser.ids), len(set(parser.ids)))
            for href in parser.links:
                target = urlsplit(href)
                if target.scheme == 'mailto':
                    self.assertRegex(target.path, r'^[^\s@]+@[^\s@]+$')
                elif target.scheme in ('http', 'https'):
                    self.assertTrue(target.netloc)
                else:
                    self.assertFalse(target.scheme)
                    self.assertTrue((path.parent / target.path).is_file())
                    if target.fragment:
                        self.assertIn(target.fragment, parser.ids)
            outlines.append(parser.levels)
            links.append(parser.links)
        self.assertEqual(*outlines)
        self.assertEqual(*links)

    def test_ten_shortcut_categories_match_in_both_languages(self):
        groups = []
        for language, start, end, categories in (
            ('ar', '# اختصارات لوحة المفاتيح المعتمدة', '# تلقي ملاحظاتكم',
             ['الاختصارات العامة', 'اختصار الطقس', 'اختصارات مواقيت الصلاة', 'اختصارات الساعة والتوقيت',
              'اختصارات التقاويم والتواريخ', 'اختصارات التنبيهات والأذكار', 'اختصارات المنبهات',
              'اختصارات المؤقتات', 'اختصارات ساعة الإيقاف', 'اختصارات الساعة العالمية']),
            ('en', '# Approved keyboard shortcuts', '# Sending feedback',
             ['General shortcuts', 'Weather shortcut', 'Prayer-time shortcuts', 'Clock and time shortcuts',
              'Calendar and date shortcuts', 'Alert and adhkar shortcuts', 'Alarm shortcuts',
              'Timer shortcuts', 'Stopwatch shortcuts', 'World-clock shortcuts']),
        ):
            text = (ROOT / f'addon/doc/{language}/readme.md').read_text('utf8')
            section = text[text.index(start):text.index(end)]
            self.assertEqual(re.findall(r'^## (.+)$', section, re.M), categories)
            groups.append([re.findall(r'^- (NVDA\+[^:]+):', part, re.M)
                           for part in re.split(r'^## .+$', section, flags=re.M)[1:]])
            history = text[text.index('# سجل التغييرات' if language == 'ar' else '# Change log'):]
            self.assertIn('8.0.1', history.split('## ')[1])
            self.assertNotIn('-dev', history)
        self.assertEqual(*groups)
        self.assertEqual([len(g) for g in groups[0]], [1, 2, 3, 2, 3, 4, 3, 7, 6, 1])

    def test_no_unassigned_section_or_internal_command_names_and_generated_docs_match(self):
        from tools.build_release_docs import build_arabic_markdown, markdown_to_html
        tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf8'))
        names = [n.name[7:] for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name.startswith('script_')]
        self.assertEqual(
            build_arabic_markdown((ROOT / 'docs/دليل_أوقاتي_العربي_المعتمد.md').read_text('utf8')),
            (ROOT / 'addon/doc/ar/readme.md').read_text('utf8'),
        )
        for language, direction, title in (
            ('ar', 'rtl', 'دليل استخدام أوقاتي 8.0.1'),
            ('en', 'ltr', 'Awqati 8.0.1 user guide'),
        ):
            markdown = (ROOT / f'addon/doc/{language}/readme.md').read_text('utf8')
            html = (ROOT / f'addon/doc/{language}/readme.html').read_text('utf8')
            self.assertEqual(markdown_to_html(markdown, lang=language, direction=direction, title=title), html)
            for text in (markdown, html):
                self.assertNotIn('أوامر دون اختصار افتراضي', text)
                self.assertNotIn('Commands without a default shortcut', text)
                for name in names:
                    self.assertNotIn('`' + name + '`', text)
                    self.assertNotIn('<code>' + name + '</code>', text)

    def test_every_current_default_is_documented_once_in_each_language(self):
        tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf8'))
        gestures = [n.value.value.split(':', 1)[1] for n in ast.walk(tree)
                    if isinstance(n, ast.keyword) and n.arg == 'gesture']
        for language in ('ar', 'en'):
            for extension in ('md', 'html'):
                text = (ROOT / f'addon/doc/{language}/readme.{extension}').read_text('utf8').lower()
                for gesture in gestures:
                    label = gesture.lower().replace('control', 'ctrl') + ':'
                    self.assertEqual(text.count(label), 1, (language, extension, gesture))

    def test_help_has_semantic_lists_and_no_development_acceptance_instructions(self):
        for language in ('ar', 'en'):
            text = (ROOT / f'addon/doc/{language}/readme.html').read_text('utf8')
            self.assertIn('<ul>', text)
            self.assertNotIn('| --- |', text)
            self.assertNotIn('Task 1.1', text)
            self.assertNotIn('5.0.0-dev10', text)
            self.assertIn('5.0.0', text)

    def test_new_metadata_description_is_in_both_guides(self):
        from test_release_package import EXPECTED_ENGLISH_DESCRIPTION, EXPECTED_ARABIC_DESCRIPTION
        for language, description in (('ar', EXPECTED_ARABIC_DESCRIPTION), ('en', EXPECTED_ENGLISH_DESCRIPTION)):
            self.assertIn(description, (ROOT / f'addon/doc/{language}/readme.md').read_text('utf8'))
