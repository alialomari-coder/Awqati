"""Regression checks for the narrowly approved opening shortcut change."""
import ast
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py'


class StopwatchClosureTests(unittest.TestCase):
    def test_opening_gesture_is_the_only_production_method_change_since_dev8(self):
        previous = subprocess.check_output(['git', 'show', '10d4548:' + PLUGIN.relative_to(ROOT).as_posix()], cwd=ROOT).decode('utf-8')
        old = ast.parse(previous)
        new = ast.parse(PLUGIN.read_text(encoding='utf-8'))
        # Dev19's approved custom-location repair changes composition only;
        # keep the full historical stopwatch comparison after removing that
        # precise startup branch, helper and its two imports.
        cls = next(node for node in new.body if isinstance(node, ast.ClassDef))
        cls.body = [node for node in cls.body if not (isinstance(node, ast.FunctionDef)
                    and node.name == '_show_custom_method_setup')]
        for node in ast.walk(new):
            if isinstance(node, ast.ImportFrom) and node.module == 'ui':
                node.names = [name for name in node.names if name.name not in
                              ('custom_calculation_method_required', 'choose_custom_calculation_method')]
            if (isinstance(node, ast.If) and isinstance(node.test, ast.Call)
                    and isinstance(node.test.func, ast.Name) and node.test.func.id == 'first_run_location_required'):
                self.assertEqual(len(node.orelse), 1)
                branch = node.orelse[0]
                self.assertEqual(branch.test.func.id, 'custom_calculation_method_required')
                node.orelse = []
        from multipress_history import restore_dev17_plugin
        new = restore_dev17_plugin(new)
        for tree in (old, new):
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
            method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'script_stopwatchWindow')
            # Description and gesture metadata are the only permitted changes.
            method.decorator_list = []
        # Task 2.2 adds countdown commands and lifecycle wiring only. Strip
        # those exact additions, then retain the full dev8 AST comparison.
        class CountdownWiring(ast.NodeTransformer):
            def visit_ImportFrom(self, node):
                return None if node.module == 'countdown_control' else node
            def visit_FunctionDef(self, node):
                if node.name == '_showCountdowns' or node.name.startswith('script_countdown'):
                    return None
                return self.generic_visit(node)
            def visit_Assign(self, node):
                if any(isinstance(t, ast.Attribute) and t.attr == '_countdowns' for t in node.targets):
                    return None
                return self.generic_visit(node)
            def visit_If(self, node):
                if isinstance(node.test, ast.Attribute) and node.test.attr == '_countdowns':
                    return None
                return self.generic_visit(node)
            def visit_Call(self, node):
                node.keywords = [k for k in node.keywords if k.arg != 'show_countdowns']
                return self.generic_visit(node)
        # The clock-page follow-up changes window routing only; every
        # other plugin node still passes the full historical comparison.
        from time_tools_history import restore_plugin_window_routing, strip_world_clock_wiring
        new = strip_world_clock_wiring(self, new)
        new = restore_plugin_window_routing(new, old)
        new = CountdownWiring().visit(new)
        self.assertEqual(ast.dump(old), ast.dump(new))
        unchanged = [
            'application/stopwatch.py', 'infrastructure/stopwatch.py',
            'nvda_adapter/stopwatch_control.py', 'nvda_adapter/stopwatch_dialog.py',
            'nvda_adapter/stopwatch_formatter.py', 'nvda_adapter/stopwatch_gestures.py',
            'nvda_adapter/audio_service.py',
        ]
        core = ROOT / 'addon/globalPlugins/awqati'
        # Dev11 explicitly authorizes gain/pitch changes, but retains the
        # byte-exact historical waveform and all durations as regression checks.
        from sound_history import assert_updated_stopwatch_sound
        for path in (core / 'sounds/stopwatch').glob('*.wav'):
            original = subprocess.check_output(['git', 'show', '10d4548:' + path.relative_to(ROOT).as_posix()], cwd=ROOT)
            assert_updated_stopwatch_sound(self, original, path)
        for relative in unchanged:
            with self.subTest(relative=relative):
                path = core / relative
                original = subprocess.check_output(['git', 'show', '10d4548:' + path.relative_to(ROOT).as_posix()], cwd=ROOT)
                from multipress_history import legacy_gestures_bytes, legacy_control_bytes
                current = legacy_gestures_bytes() if relative.endswith('stopwatch_gestures.py') else path.read_bytes()
                if relative.endswith('stopwatch_control.py'):current = legacy_control_bytes(current)
                if path.suffix == '.py':
                    original, current = original.replace(b'\r\n', b'\n'), current.replace(b'\r\n', b'\n')
                if relative == 'nvda_adapter/stopwatch_dialog.py':
                    from time_tools_history import restore_dialog_constructor
                    self.assertEqual(ast.dump(ast.parse(original)), ast.dump(restore_dialog_constructor(ast.parse(current), 'StopwatchDialog')))
                else:
                    self.assertEqual(original, current)

    def test_runtime_changes_are_limited_to_countdown_reservation_and_discard_hooks(self):
        relative = 'addon/globalPlugins/awqati/nvda_adapter/runtime.py'
        old = subprocess.check_output(['git', 'show', '10d4548:' + relative], cwd=ROOT).decode('utf-8')
        current = (ROOT / relative).read_text(encoding='utf-8')
        block = '\tdef _discard(self, event, outcome):\n\t\tself.alarms.discarded(event, outcome)\n\t\tif getattr(self, "countdowns", None):\n\t\t\ttry:\n\t\t\t\tself.countdowns.handled(event, outcome)\n\t\t\texcept OSError:\n\t\t\t\t# The timer controller reports its storage_error. A failed\n\t\t\t\t# timer write must not prevent expiry of unrelated alerts.\n\t\t\t\tpass\n\n'
        hook = '\t\tif getattr(self, "countdowns", None):\n\t\t\tself.countdowns.handled(event)\n'
        self.assertEqual(1, current.count(block))
        self.assertEqual(1, current.count(hook))
        normalized = current.replace(block, '').replace(hook, '').replace('on_discard=self._discard', 'on_discard=self.alarms.discarded')
        self.assertEqual(ast.dump(ast.parse(old)), ast.dump(ast.parse(normalized)))

    def test_command_queues_same_window_helper_and_old_default_is_absent(self):
        tree = ast.parse(PLUGIN.read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'script_stopwatchWindow')
        metadata = {keyword.arg: keyword.value.value for keyword in method.decorator_list[0].keywords if isinstance(keyword.value, ast.Constant)}
        self.assertEqual('kb:NVDA+control+j', metadata['gesture'])
        source = PLUGIN.read_text(encoding='utf-8').lower()
        self.assertNotIn('gesture="kb:nvda+alt+j"', source)
        method.decorator_list = []
        queued, opened = [], []
        namespace = {'wx': SimpleNamespace(CallAfter=queued.append)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(PLUGIN), 'exec'), namespace)
        driver = SimpleNamespace(_showStopwatch=lambda: opened.append(True))
        namespace['script_stopwatchWindow'](driver, None)
        self.assertEqual([], opened)
        self.assertEqual([driver._showStopwatch], queued)
        queued[0]()
        self.assertEqual([True], opened)

    def test_official_version_audit_has_no_existing_default_conflicts(self):
        audit = json.loads((ROOT / 'docs/stopwatch_open_gesture_audit.json').read_text(encoding='utf-8'))
        self.assertTrue(audit['safeForRequestedDefault'])
        self.assertEqual([], audit['awqatiExistingConflictsBeforeChange'])
        self.assertEqual(['2026.1', '2026.2', '2026.3'], [row['version'] for row in audit['nvda']])
        for row in audit['nvda']:
            self.assertEqual([], row['targetFindings'])
            self.assertGreaterEqual(row['sourcePyAndIniFiles'], 500)
            self.assertEqual(40, len(row['commit']))
            self.assertEqual(64, len(row['archiveSha256']))


if __name__ == '__main__':
    unittest.main()
