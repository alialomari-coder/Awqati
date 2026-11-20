"""Clock-page integration contracts, plus byte-exact dev11 behavior regressions."""
import ast
import hashlib
from copy import deepcopy
import subprocess
from types import SimpleNamespace
import unittest
from time_tools_driver import ROOT, ADAPTER, definitions
import sys
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from time_tools_history import restore_dialog_constructor


class View:
    def __init__(self, *args):
        self.shown, self.focus, self.selection = True, False, 0
        self.values = {}
    def Hide(self): self.shown = False
    def Show(self): self.shown = True
    def MoveAfterInTabOrder(self, other): self.after = other
    def SetSelection(self, index): self.selection = index
    def GetSelection(self): return self.selection
    def SetFocus(self): self.focus = True


def host_driver():
    wx = SimpleNamespace(Panel=object)
    dialog = SimpleNamespace()
    for name in ('_build_controls', 'selected', 'refresh', 'edit', 'change', 'delete', 'toggle', 'enable_all',
                 'update_buttons', 'preview', 'change_mode', 'tick'):
        setattr(dialog, name, lambda *args: None)
    ns = definitions('time_tools.py', {'wx': wx, '_': lambda text: text,
        'AlarmManager': dialog, 'CountdownDialog': dialog, 'StopwatchDialog': dialog})
    state = ns['TimeToolsState'](object(), SimpleNamespace(service=object()), SimpleNamespace(watch=object()))
    host = ns['TimeToolsHost'].__new__(ns['TimeToolsHost'])
    host.state, host.choice, host.views, host.parent = state, View(), {}, None
    host.sizer = SimpleNamespace(Add=lambda *a, **kw: None)
    host.layout = lambda: None
    ns.update(AlarmPanel=View, CountdownPanel=View, StopwatchPanel=View, wx=SimpleNamespace(EXPAND=1))
    return host, state, ns


class TimeToolsIntegrationTests(unittest.TestCase):
    def test_only_selected_view_shown_and_cached(self):
        host, state, _ = host_driver()
        for name in ('alarms', 'timers', 'stopwatch', 'alarms'):
            host.select(name)
            self.assertEqual([name], [key for key, view in host.views.items() if view.shown])
            self.assertEqual(name, state.selected)
            self.assertTrue(host.choice.focus)
            self.assertIs(host.choice, host.views[name].after)
        self.assertEqual(3, len(host.views))

    def test_switch_does_not_rebuild_or_lose_selection_or_uncommitted_values(self):
        host, _, _ = host_driver()
        host.select('timers')
        view = host.views['timers']
        view.selection, view.values['edit'] = 4, 'unfinished value'
        host.select('stopwatch'); host.select('timers')
        self.assertIs(view, host.views['timers'])
        self.assertEqual((4, 'unfinished value'), (view.selection, view.values['edit']))

    def test_last_tool_remembered_without_schema_fields(self):
        host, state, ns = host_driver()
        host.select('stopwatch')
        self.assertEqual('stopwatch', state.selected)
        state.panel = lambda: SimpleNamespace(show_time_tool=lambda name: host.select(name))
        state.request('timers')
        self.assertEqual('timers', state.selected)
        self.assertIsNone(state.requested)
        with self.assertRaises(ValueError): state.request('worldClock')

    def test_choice_event_restores_focus_and_skips(self):
        host, state, _ = host_driver()
        host.choice.SetSelection(1)
        calls = []
        host.on_choice(SimpleNamespace(Skip=lambda: calls.append('skip')))
        self.assertEqual(('timers', True, ['skip']), (state.selected, host.choice.focus, calls))

    def test_destruction_detaches_ui_and_stops_display_timer_only(self):
        _, _, ns = host_driver()
        calls = []
        view = ns['EmbeddedView']()
        control = SimpleNamespace(dialog=view, running=True)
        view.control, view.timer = control, SimpleNamespace(Stop=lambda: calls.append('display'))
        event = SimpleNamespace(GetEventObject=lambda: view, Skip=lambda: None)
        view._detach(event)
        self.assertIsNone(control.dialog)
        self.assertTrue(control.running)
        self.assertEqual(['display'], calls)

    def test_nested_child_destruction_does_not_detach_view(self):
        _, _, ns = host_driver()
        view = ns['EmbeddedView'](); view.control = SimpleNamespace(dialog=view)
        view._detach(SimpleNamespace(GetEventObject=lambda: object(), Skip=lambda: None))
        self.assertIs(view, view.control.dialog)

    def test_selector_is_last_addition_to_unchanged_clock_controls(self):
        current = ast.parse((ADAPTER/'settings_panel.py').read_text('utf-8'))
        old = ast.parse(subprocess.check_output(['git','show','1a977d9:addon/globalPlugins/awqati/nvda_adapter/settings_panel.py'],cwd=ROOT))
        method = lambda tree: next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_build_clock')
        a,b = method(old),deepcopy(method(current))
        # Exactly two new statements before the original return.
        self.assertEqual('TimeToolsHost', b.body[-2].value.func.id)
        del b.body[-3:-1]
        self.assertEqual(ast.dump(a),ast.dump(b))

    def test_every_dialog_control_and_handler_is_preserved_from_dev11(self):
        for filename, name in (('alarm_dialogs.py','AlarmManager'), ('countdown_dialog.py','CountdownDialog'), ('stopwatch_dialog.py','StopwatchDialog')):
            with self.subTest(filename=filename):
                previous = ast.parse(subprocess.check_output(['git','show','1a977d9:'+ (ADAPTER/filename).relative_to(ROOT).as_posix()],cwd=ROOT))
                current = restore_dialog_constructor(ast.parse((ADAPTER/filename).read_text('utf-8')),name)
                if filename == 'countdown_dialog.py':
                    # Task 3 permits exactly this two-statement accessibility fix.
                    dialog_class = next(n for n in current.body if isinstance(n, ast.ClassDef) and n.name == name)
                    builder = next(n for n in dialog_class.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
                    label = ast.parse('set_list_name(self.list, _("Timers list"))').body[0]
                    matches = [n for n in builder.body if ast.dump(n) == ast.dump(label)]
                    self.assertEqual(1, len(matches))
                    builder.body.remove(matches[0])
                    names = [n for n in ast.walk(builder) if isinstance(n, ast.keyword) and n.arg == 'name'
                             and isinstance(n.value, ast.Call) and n.value.args and isinstance(n.value.args[0], ast.Constant)
                             and n.value.args[0].value == 'Timers list']
                    self.assertEqual(1, len(names))
                    names[0].value.args[0].value = 'Countdown timers'
                    imports = [n for n in current.body if isinstance(n, ast.ImportFrom) and n.module == 'native_accessibility']
                    self.assertEqual(1, len(imports))
                    self.assertEqual(['set_list_name'], [n.name for n in imports[0].names])
                    current.body.remove(imports[0])
                    # dev18 adds selection synchronization in refresh only.
                    old_class = next(n for n in previous.body if isinstance(n, ast.ClassDef) and n.name == name)
                    old_refresh = next(n for n in old_class.body if isinstance(n, ast.FunctionDef) and n.name == 'refresh')
                    dialog_class.body = [old_refresh if isinstance(n, ast.FunctionDef) and n.name == 'refresh' else n for n in dialog_class.body]
                self.assertEqual(ast.dump(previous),ast.dump(current))

    def test_engines_storage_sounds_and_controllers_unchanged_from_dev11(self):
        paths = subprocess.check_output(['git','ls-tree','-r','--name-only','1a977d9','addon/globalPlugins/awqati'],cwd=ROOT).decode().splitlines()
        checked = 0
        for relative in paths:
            if any('/'+part+'/' in relative for part in ('application','domain','infrastructure','sounds')) or relative.endswith(('stopwatch_control.py','countdown_control.py')):
                previous = subprocess.check_output(['git','show','1a977d9:'+relative],cwd=ROOT)
                current = (ROOT/relative).read_bytes()
                # The completed, owner-approved synopsis supersedes the
                # stage-1.1-only pins for these five specific files.
                from daily_synopsis_baseline import APPROVED_SYNOPSIS_SHA256
                if relative in APPROVED_SYNOPSIS_SHA256:
                    self.assertEqual(APPROVED_SYNOPSIS_SHA256[relative], hashlib.sha256(current).hexdigest(), relative)
                    checked += 1
                    continue
                if relative.endswith('countdown_control.py'):
                    # dev18 intentionally extends this controller. Dedicated
                    # dev18 tests cover it; retain this historical comparison.
                    current = subprocess.check_output(['git','show','0e8348d:'+relative],cwd=ROOT)
                if relative.endswith('stopwatch_control.py'):
                    from multipress_history import legacy_control_bytes
                    current=legacy_control_bytes(current)
                if relative.endswith('.py'):
                    from on_this_day_history import strip_day_settings
                    self.assertEqual(ast.dump(ast.parse(previous)),ast.dump(strip_day_settings(ast.parse(current))),relative)
                else:
                    self.assertEqual(previous,current,relative)
                checked += 1
        self.assertEqual(84,checked)

    def test_all_script_commands_and_gestures_unchanged(self):
        current = ast.parse((ADAPTER/'plugin.py').read_text('utf-8'))
        from multipress_history import restore_dev17_plugin
        current=restore_dev17_plugin(current)
        previous = ast.parse(subprocess.check_output(['git','show','1a977d9:'+ (ADAPTER/'plugin.py').relative_to(ROOT).as_posix()],cwd=ROOT))
        scripts=lambda tree: [ast.dump(n) for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('script_') and n.name!='script_worldClock']
        self.assertEqual(scripts(previous),scripts(current))
        extra=[n for n in ast.walk(current) if isinstance(n,ast.FunctionDef) and n.name=='script_worldClock']
        self.assertEqual(1,len(extra))
        self.assertIn('kb:NVDA+control+f12',ast.unparse(extra[0]))

    def test_open_commands_request_corresponding_embedded_tool(self):
        ns = {'wx':SimpleNamespace(), 'compat':SimpleNamespace(open_awqati_settings=lambda cls: calls.append('settings')), 'AwqatiSettingsPanel':object}
        tree = ast.parse((ADAPTER/'plugin.py').read_text('utf-8'))
        methods = [n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in ('_showAlarms','_showCountdowns','_showStopwatch','_openTimeTool')]
        cls = ast.ClassDef(name='Driver', bases=[], keywords=[], body=methods, decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'plugin','exec'),ns)
        driver=ns['Driver'](); driver._terminated=False; driver._countdowns=driver._stopwatch=True
        calls=[]; state=SimpleNamespace(requested=None, request=lambda tool:calls.append(tool))
        driver._context=SimpleNamespace(time_tools=state)
        driver._actions=SimpleNamespace(invalidate_feedback=lambda:None)
        for method,tool in (('_showAlarms','alarms'),('_showCountdowns','timers'),('_showStopwatch','stopwatch')):
            calls.clear(); getattr(driver,method)()
            self.assertEqual(['settings',tool],calls)
            self.assertEqual(tool,state.requested)


    def test_sections_retain_controls_and_pending_input_across_page_switches(self):
        from awqati.nvda_adapter.settings_sections import SettingsSection
        namespace = {'wx': SimpleNamespace(LEFT=1,RIGHT=2,BOTTOM=4,EXPAND=8), 'SettingsSection':SettingsSection}
        tree = ast.parse((ADAPTER/'settings_panel.py').read_text('utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_render_section')
        exec(compile(ast.Module(body=[method],type_ignores=[]),'section','exec'),namespace)
        driver = SimpleNamespace(_section_panel=None,_section_panels={},section_choice=View(),
            _settings_sizer=SimpleNamespace(Add=lambda *a,**k:None),_layout=lambda:None)
        for name in ('prayer','clock','date','adhkar'):
            setattr(driver,'_build_'+name,lambda:View())
        driver._section=SettingsSection.CLOCK; namespace['_render_section'](driver)
        original=driver._section_panel; original.values['pending']='not committed'
        driver._section=SettingsSection.DATE; namespace['_render_section'](driver)
        self.assertFalse(original.shown)
        driver._section=SettingsSection.CLOCK; namespace['_render_section'](driver)
        self.assertIs(original,driver._section_panel)
        self.assertEqual('not committed',original.values['pending'])
        self.assertTrue(original.shown)

    def test_existing_nvda_settings_dialog_activates_awqati_without_reopening(self):
        import sys
        from unittest.mock import patch
        from awqati.nvda_adapter.compat import open_awqati_settings
        class Panel: pass
        calls=[]
        class Dialog:
            categoryClasses=[object,Panel]
            currentCategory=object()
            def IsBeingDeleted(self): return False
            def _doCategoryChange(self,index): calls.append(('category',index))
            def Raise(self): calls.append('raise')
            catListCtrl=SimpleNamespace(Select=lambda i:calls.append(('select',i)),Focus=lambda i:None)
        dialog=Dialog()
        with patch.dict(sys.modules,{'wx':SimpleNamespace(GetTopLevelWindows=lambda:[dialog]),
                'gui':SimpleNamespace(), 'gui.settingsDialogs':SimpleNamespace(NVDASettingsDialog=Dialog)}):
            open_awqati_settings(Panel)
        self.assertEqual([('category',1),('select',1),'raise'],calls)


if __name__=='__main__': unittest.main()
