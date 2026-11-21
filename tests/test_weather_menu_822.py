"""Exercise retained production menu lifecycle with no NVDA installation changes."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, call
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'addon/globalPlugins/awqati/nvda_adapter/weather_control.py'


class Menu:
    def __init__(self):
        self.items = []
        self.bindings = []
        self.destroyed = []

    def Append(self, item_id, label):
        item = SimpleNamespace(label=label)
        self.items.append(item)
        return item

    def AppendSubMenu(self, menu, label):
        item = SimpleNamespace(label=label, menu=menu)
        self.items.append(item)
        return item

    def Bind(self, event, handler, item):
        self.bindings.append(handler)

    def DestroyItem(self, item):
        self.items.remove(item)
        self.destroyed.append(item)


class WeatherMenuTests(unittest.TestCase):
    def control(self, enabled=None, language='ar'):
        tree = ast.parse(SOURCE.read_text('utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)
                 and n.name in ('WeatherControl', 'WeatherPresses')]
        flag = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'TOOLS_MENU_ENABLED' for t in n.targets))
        self.assertIs(ast.literal_eval(flag.value), False)
        self.tools = Menu()
        # Any access to the Tools menu while disabled fails, including separators.
        tray = SimpleNamespace(toolsMenu=self.tools) if enabled else Mock()
        if not enabled:
            type(tray).toolsMenu = property(lambda obj: self.fail('Tools menu accessed while disabled'))
        self.factory = Mock(side_effect=Menu)
        self.service = Mock(enabled=False)
        self.unsubscribe = Mock()
        events = SimpleNamespace(subscribe=Mock(return_value=self.unsubscribe))
        settings = SimpleNamespace(events=events, runtime_settings=SimpleNamespace(weather=object(), location=None))
        self.dialog = SimpleNamespace(_instance=None)
        scope = dict(wx=SimpleNamespace(Menu=self.factory, CallAfter=Mock(), CallLater=Mock(),
                                        ID_ANY=-1, EVT_MENU=object()),
                     gui=SimpleNamespace(mainFrame=SimpleNamespace(sysTrayIcon=tray)),
                     WeatherService=Mock(return_value=self.service), OpenMeteoProvider=Mock(),
                     SettingsApplied=object(), WeatherTextDialog=self.dialog)
        exec(compile(ast.Module(body=[flag, *nodes], type_ignores=[]), str(SOURCE), 'exec'), scope)
        if enabled is not None:
            scope['TOOLS_MENU_ENABLED'] = enabled
        control = scope['WeatherControl'](settings, object(), lambda: language, Mock(), lambda: 500)
        return control

    def test_default_creates_neither_menu_nor_blank_item_or_separator_in_both_languages(self):
        for language in ('ar', 'en'):
            with self.subTest(language=language):
                control = self.control(language=language)
                self.factory.assert_not_called()
                self.assertEqual(self.tools.items, [])
                self.assertIsNone(control.menu_item)
                self.service.configure.assert_called_once()
                control.presses.press()
                self.service.cancel_speech.assert_called()
                control.close()
                control.close()
                self.service.close.assert_called_once()
                self.unsubscribe.assert_called_once()
                self.assertEqual(self.tools.destroyed, [])

    def test_hidden_close_stops_timer_and_closes_open_text_report(self):
        control = self.control()
        timer = control.timer = Mock()
        dialog = self.dialog._instance = Mock()
        control.close()
        timer.Stop.assert_called_once()
        dialog.Close.assert_called_once()
        self.unsubscribe.assert_called_once()

    def test_one_flag_restores_both_menus_and_all_five_original_commands(self):
        for language, labels in (
            ('ar', ['الحالة الحالية', 'توقعات اليوم', 'توقعات الأيام القادمة',
                    'فتح معلومات الطقس في نافذة نصية', 'تحديث الآن']),
            ('en', ['Current weather', "Today's forecast", 'Coming days forecast',
                    'Open weather information in a text window', 'Refresh now']),
        ):
            with self.subTest(language=language):
                control = self.control(enabled=True, language=language)
                self.assertEqual(len(self.tools.items), 1)
                self.assertEqual(self.tools.items[0].label, 'أوقاتي' if language == 'ar' else 'Awqati')
                self.assertEqual(len(control.menu.items), 1)
                self.assertEqual(control.menu.items[0].label, 'الطقس' if language == 'ar' else 'Weather')
                self.assertEqual([i.label for i in control.weather_menu.items], labels)
                control.select, control.show, control.refresh_now = Mock(), Mock(), Mock()
                # Bound methods for show/refresh are captured during original registration.
                for handler in control.menu.bindings:
                    handler(None)
                self.assertEqual(control.select.call_args_list[:3],
                                 [call('current'), call('today'), call('future')])
                self.assertEqual(control.select.call_args_list[-1].kwargs, {'force': True})
                control.close()
                control.close()
                self.assertEqual(self.tools.items, [])
                self.assertEqual(len(self.tools.destroyed), 1)

    def test_gestures_keep_their_original_routes_and_termination_guard(self):
        tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf-8'))
        methods = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        scope = dict(compat=SimpleNamespace(open_awqati_settings=Mock()), AwqatiSettingsPanel=object())
        expected = {'script_weather': 'kb:NVDA+w', 'script_weatherSettings': 'kb:NVDA+alt+w',
                    'script_weatherReport': None}
        for name, gesture in expected.items():
            method = methods[name]
            values = [k.value.value for d in method.decorator_list for k in d.keywords if k.arg == 'gesture']
            self.assertEqual(values, [gesture] if gesture else [])
            method.decorator_list = []
            exec(compile(ast.Module(body=[method], type_ignores=[]), name, 'exec'), scope)
        weather = SimpleNamespace(presses=SimpleNamespace(press=Mock()), show=Mock())
        obj = SimpleNamespace(_weather=weather, _terminated=False, _actions=Mock())
        scope['script_weather'](obj, None)
        weather.presses.press.assert_called_once()
        scope['script_weatherReport'](obj, None)
        weather.show.assert_called_once()
        obj._terminated = True
        scope['script_weather'](obj, None)
        scope['script_weatherReport'](obj, None)
        weather.presses.press.assert_called_once()
        weather.show.assert_called_once()
        section = object()
        scope['__package__'] = 'awqati.nvda_adapter'
        with patch.dict(sys.modules, {'awqati.nvda_adapter.settings_sections':
                        SimpleNamespace(SettingsSection=SimpleNamespace(WEATHER=section))}):
            scope['script_weatherSettings'](obj, None)
        obj._actions.invalidate_feedback.assert_called_once()
        scope['compat'].open_awqati_settings.assert_called_once_with(scope['AwqatiSettingsPanel'], section)


if __name__ == '__main__':
    unittest.main()
