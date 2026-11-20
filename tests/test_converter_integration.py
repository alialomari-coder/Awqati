"""Deterministic gesture races, cancellation and active date context."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace as NS
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from calendar_converter_launcher import prepare_wx
prepare_wx()
from awqati.nvda_adapter.calendar_converter_control import ConverterPresses, CalendarConverterControl


class Timer:
	def __init__(self, delay, callback):
		self.delay, self.callback, self.stopped = delay, callback, False
	def Stop(self):
		self.stopped = True


class GestureTests(unittest.TestCase):
	def setUp(self):
		self.timers, self.opened = [], []
		self.bound = True
		def schedule(delay, callback):
			timer = Timer(delay, callback)
			self.timers.append(timer)
			return timer
		self.control = ConverterPresses(schedule, lambda: 500, lambda ids: self.bound, self.opened.append)

	def press(self, repeat=0, ids=('kb:nvda+shift+f9',)):
		self.control.press(ids, repeat)

	def test_single_waits_and_double_never_opens_basic(self):
		self.press()
		self.assertEqual(self.opened, [])
		self.assertEqual(self.timers[-1].delay, 530)
		self.press(1)
		self.timers[0].callback()  # even a queued cancelled callback is harmless
		self.assertEqual(self.opened, [])
		self.timers[-1].callback()
		self.assertEqual(self.opened, [True])

	def test_single_and_separated_presses(self):
		for _ in range(3):
			self.press()
			self.timers[-1].callback()
		self.assertEqual(self.opened, [False] * 3)

	def test_rapid_many_coalesce(self):
		for i in range(20):
			self.press(i)
		for timer in self.timers:
			timer.callback()
		self.assertEqual(self.opened, [True])

	def test_different_binding_and_intervening_script_reset(self):
		self.press()
		self.press(1, ('kb:nvda+f10',))
		self.timers[-1].callback()
		self.assertEqual(self.opened, [False])
		self.press()
		self.press(0)
		self.timers[-1].callback()
		self.assertEqual(self.opened, [False, False])

	def test_removed_binding_cancels_pending(self):
		self.press()
		self.bound = False
		self.timers[-1].callback()
		self.assertEqual(self.opened, [])

	def test_close_and_explicit_open_invalidate_queued_callbacks(self):
		self.press()
		self.control.cancel()
		self.timers[-1].callback()
		self.press()
		self.control.close()
		self.timers[-1].callback()
		self.press(1)
		self.assertEqual(self.opened, [])
		self.assertEqual(len(self.timers), 2)


class ContextTests(unittest.TestCase):
	def test_source_integration_catalogs_match_and_labels_are_translated(self):
		import gettext
		import sys
		sys.path.insert(0, str(ROOT / '.build-deps'))
		from babel.messages.pofile import read_po
		folder = ROOT / 'addon/locale/ar/LC_MESSAGES'
		for domain in ('nvda', 'calendar_converter'):
			with (folder / (domain + '.po')).open('rb') as stream:
				catalog = read_po(stream, locale='ar')
			with (folder / (domain + '.mo')).open('rb') as stream:
				translate = gettext.GNUTranslations(stream).gettext
			for message in catalog:
				if message.id and isinstance(message.id, str) and message.string:
					self.assertEqual(translate(message.id), message.string)
		translate = gettext.translation('nvda', ROOT / 'addon/locale', languages=['ar']).gettext
		self.assertEqual(translate('Calendar'), 'التقويم')
		self.assertEqual(translate('Open date converter'), 'فتح محوّل التاريخ')
		self.assertEqual(translate('Advanced conversion...'), 'التحويل المتقدم...')

	def test_saved_location_is_read_each_time_without_adjustment(self):
		settings = NS(runtime_settings=NS(location=NS(location=NS(timezone_id='east'))))
		now = NS(now=lambda: NS(value=datetime(2026, 11, 13, 23, 30, tzinfo=timezone.utc)))
		zones = NS(get_timezone=lambda key: timezone(timedelta(hours=3 if key == 'east' else -5)))
		control = CalendarConverterControl(settings, now, zones, None, lambda: 'en', lambda text: None, None)
		self.assertEqual(str(control.today()), '2026-11-14')
		settings.runtime_settings.location.location.timezone_id = 'west'
		self.assertEqual(str(control.today()), '2026-11-13')

	def test_command_has_no_default_and_keeps_existing_gestures(self):
		import ast
		path = ROOT / 'addon/globalPlugins/awqati/nvda_adapter/plugin.py'
		tree = ast.parse(path.read_text(encoding='utf-8'))
		method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'script_openDateConverter')
		self.assertFalse(any(k.arg in ('gesture', 'gestures') for k in method.decorator_list[0].keywords))
		self.assertIn('getLastScriptRepeatCount', ast.unparse(method))


if __name__ == '__main__':
	unittest.main()
