import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
if str(ADDON) not in sys.path:
	sys.path.insert(0, str(ADDON))

from globalPlugins.awqati.nvda_adapter import compat


class NativeRepeatDispatchTests(unittest.TestCase):
	def dispatch(self, count, size=3):
		calls = []
		handlers = tuple(lambda value=value: calls.append(value) for value in range(1, size + 1))
		with patch.dict(sys.modules, {"scriptHandler": SimpleNamespace(getLastScriptRepeatCount=lambda: count)}):
			compat.dispatch_repeated_script(handlers)
		return calls

	def test_first_press_runs_inside_first_call_without_timer(self):
		calls = []
		with patch.dict(sys.modules, {"scriptHandler": SimpleNamespace(getLastScriptRepeatCount=lambda: 0)}):
			compat.dispatch_repeated_script((lambda: calls.append("started"), lambda: calls.append("second")))
		self.assertEqual(["started"], calls)

	def test_native_repeat_count_selects_each_handler(self):
		self.assertEqual([1], self.dispatch(0))
		self.assertEqual([2], self.dispatch(1))
		self.assertEqual([3], self.dispatch(2))

	def test_repeat_count_is_capped_at_last_handler(self):
		self.assertEqual([3], self.dispatch(7))
		self.assertEqual([2], self.dispatch(4, size=2))

	def test_missing_or_invalid_nvda_api_falls_back_to_first_press(self):
		for module in (SimpleNamespace(), SimpleNamespace(getLastScriptRepeatCount=lambda: "invalid")):
			with self.subTest(module=module), patch.dict(sys.modules, {"scriptHandler": module}):
				self.assertEqual(0, compat.script_repeat_count())

	def test_empty_handler_sequence_is_rejected(self):
		with self.assertRaises(ValueError):
			compat.dispatch_repeated_script(())


if __name__ == "__main__":
	unittest.main()
