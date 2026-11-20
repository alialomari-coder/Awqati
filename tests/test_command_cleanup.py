"""Dev20 visibility and saved bindings against local official NVDA sources."""
import ast
import __future__
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from test_multi_press_execution import plugin_driver
from test_stopwatch import ROOT
from awqati.nvda_adapter import compat
from awqati.nvda_adapter.legacy_commands import DUPLICATE_COMMANDS, configure_legacy_visibility


def gesture_map(rows=()):
    return NS(getScriptsForAllGestures=lambda: iter(rows))


def described_plugin():
    obj, _ = plugin_driver()
    cls = type(obj)
    tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf8'))
    obj._gestureMap = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith('script_'):
            continue
        script = getattr(cls, node.name)
        for decorator in node.decorator_list:
            for keyword in decorator.keywords:
                if keyword.arg == 'description':
                    script.__doc__ = keyword.value.args[0].value
                elif keyword.arg == 'category':
                    script.category = 'Awqati'
                elif keyword.arg == 'gesture':
                    obj._gestureMap[keyword.value.value] = script
    return obj


def native_collector(version):
    source = (ROOT / f'development_baseline/multipress-audit/{version}/inputCore.py').read_text('utf8')
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name in ('_AllGestureMappingsRetriever', 'AllGesturesScriptInfo')]
    for cls in classes:
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)]
        if cls.name == '_AllGestureMappingsRetriever':
            cls.body = [n for n in cls.body if n.name in
                        ('addResult', 'addGlobalMap', 'makeNormalScriptInfo', 'getScriptCategory', 'addObj')]
    space = {'SCRCAT_MISC': 'Miscellaneous'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=classes, type_ignores=[])),
                 'official NVDA inputCore', 'exec', flags=__future__.annotations.compiler_flag), space)
    cls = space['_AllGestureMappingsRetriever']
    result = cls.__new__(cls)
    result.results, result.scriptInfo, result.handledGestures = {}, {}, set()
    return result


class CommandCleanupTests(unittest.TestCase):
    def test_native_dialog_hides_only_five_unassigned_duplicates(self):
        for version in ('2026.1', '2026.2', '2026.3'):
            with self.subTest(version=version):
                obj = described_plugin()
                configure_legacy_visibility(type(obj), (gesture_map(), gesture_map()))
                collector = native_collector(version)
                collector.addObj(obj)
                names = {name for cls, name in collector.scriptInfo}
                self.assertEqual(48, len(names))
                self.assertIn("openDateConverter", names)
                self.assertFalse(names & DUPLICATE_COMMANDS.keys())
                self.assertTrue({'stopwatchCount', 'countdownCount', 'gregorianDate', 'toggleDhikrAlerts',
                                 'stopPersonalAlarm', 'stopwatchCopy', 'countdownNearest'} <= names)
                self.assertEqual(33, sum(bool(info.gestures) for info in collector.scriptInfo.values()))

    def test_saved_aliases_stay_visible_editable_and_resolve_in_native_nvda(self):
        for version in ('2026.1', '2026.2', '2026.3'):
            for name in DUPLICATE_COMMANDS:
                with self.subTest(version=version, name=name):
                    obj = described_plugin()
                    rows = [(type(obj), 'kb:nvda+alt+shift+1', name)]
                    saved = gesture_map(rows)
                    configure_legacy_visibility(type(obj), (saved, gesture_map()))
                    collector = native_collector(version)
                    collector.addGlobalMap(saved)
                    collector.addObj(obj)
                    info = collector.scriptInfo[type(obj), name]
                    self.assertTrue(info.displayName)
                    self.assertEqual(['kb:nvda+alt+shift+1'], info.gestures)
                    self.assertEqual(49, len(collector.scriptInfo))
                    # Native resolution depends on the old name, not visibility.
                    source = (ROOT / f'development_baseline/multipress-audit/{version}/scriptHandler.py').read_text('utf8')
                    node = next(n for n in ast.parse(source).body
                                if isinstance(n, ast.FunctionDef) and n.name == '_getObjScript')
                    ns = {}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), 'official resolver', 'exec',
                                 flags=__future__.annotations.compiler_flag), ns)
                    resolved = ns['_getObjScript'](obj, None, [(type(obj), name)])
                    self.assertEqual(getattr(obj, 'script_' + name), resolved)
                    self.assertEqual(rows, list(saved.getScriptsForAllGestures()))

    def test_reload_restores_descriptions_and_other_plugins_do_not_expose_aliases(self):
        obj = described_plugin()
        configure_legacy_visibility(type(obj), (gesture_map(),))
        class Other:
            pass
        configure_legacy_visibility(type(obj), (gesture_map([(Other, 'kb:1', 'stopwatchToggle')]),))
        self.assertIsNone(obj.script_stopwatchToggle.__doc__)
        configure_legacy_visibility(type(obj), (gesture_map([(type(obj), 'kb:1', 'stopwatchToggle')]),))
        self.assertTrue(obj.script_stopwatchToggle.__doc__)
        configure_legacy_visibility(type(obj), (gesture_map(),))
        self.assertIsNone(obj.script_stopwatchToggle.__doc__)

    def test_failed_map_inspection_retains_all_descriptions(self):
        obj = described_plugin()
        configure_legacy_visibility(type(obj), (gesture_map(),))
        with self.assertRaises(OSError):
            configure_legacy_visibility(type(obj), (NS(getScriptsForAllGestures=Mock(side_effect=OSError)),))
        self.assertTrue(all(getattr(obj, 'script_' + name).__doc__ for name in DUPLICATE_COMMANDS))

    def test_legacy_and_default_commands_call_same_operations_and_repeat_policy(self):
        for name, (default, press) in DUPLICATE_COMMANDS.items():
            calls = []
            for command, count in ((name, 0), (default, press)):
                obj, _ = plugin_driver()
                obj._stopwatch = NS(**{method: Mock(side_effect=lambda m=method: calls.append(m))
                                      for method in ('toggle', 'lap', 'status', 'last_lap', 'total', 'current_lap')})
                obj._say = lambda producer: calls.append(producer())
                obj._content = NS(clock_text=lambda *args: 'civil time', primary_date=lambda *args: 'date',
                                  daily_info_text=lambda *args: 'daily info')
                obj._language = lambda: 'en'
                # These enums are normally imported by the full plugin module.
                from awqati.domain import ClockType
                getattr(type(obj), 'script_' + command).__globals__['ClockType'] = ClockType
                with patch.object(compat, 'script_repeat_count', return_value=count):
                    getattr(obj, 'script_' + command)(None)
            self.assertEqual(2, len(calls), name)
            self.assertEqual(calls[0], calls[1], name)


if __name__ == '__main__':
    unittest.main()
