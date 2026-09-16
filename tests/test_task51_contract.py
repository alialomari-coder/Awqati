import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py"


class Task51ContractTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.source = PLUGIN.read_text(encoding="utf-8")
		cls.tree = ast.parse(cls.source)

	def test_exact_default_gestures_are_unique(self):
		gestures = re.findall(r'gesture="kb:([^"]+)"', self.source)
		self.assertEqual(12, len(gestures))
		self.assertEqual(12, len(set(value.lower() for value in gestures)))
		self.assertEqual({
			"nvda+alt+a", "nvda+f11", "nvda+control+shift+f11", "nvda+f12",
			"nvda+shift+f11", "nvda+shift+f12", "nvda+alt+f12", "nvda+g", "nvda+h",
			"nvda+shift+h", "nvda+control+h", "nvda+shift+p",
		}, {value.lower() for value in gestures})

	def test_nine_commands_are_visible_without_default_gestures(self):
		methods = []
		for node in ast.walk(self.tree):
			if isinstance(node, ast.FunctionDef) and node.name.startswith("script_"):
				decorator = next((d for d in node.decorator_list if isinstance(d, ast.Call)), None)
				if decorator is not None and not any(k.arg == "gesture" for k in decorator.keywords):
					methods.append(node.name)
		self.assertEqual({
			"script_gregorianDate", "script_togglePrimaryCalendar", "script_zawaliTime",
			"script_toggleDhikrAlerts", "script_togglePrayerAlerts", "script_toggleClockAlert",
			"script_toggleQuietHours", "script_diagnostics", "script_dataUpdates",
		}, set(methods))

	def test_native_repeat_dispatch_is_single_and_has_no_private_wait_timer(self):
		self.assertEqual(1, self.source.count("def _press("))
		self.assertIn("compat.dispatch_repeated_script(handlers)", self.source)
		self.assertNotIn("MultiPressDispatcher", self.source)
		self.assertNotIn("timeout_ms", self.source)
		self.assertFalse((ROOT / "addon/globalPlugins/awqati/nvda_adapter/multipress.py").exists())

	def test_daily_information_window_opens_only_on_ctrl_h_third_press(self):
		block = self.source[self.source.index("def script_dailyInformation"):self.source.index("def script_prayerVerification")]
		self.assertEqual(1, block.count("self._showDailyInfo"))
		self.assertLess(block.index("scientific_info_text"), block.index("arabian_detailed"))
		self.assertLess(block.index("arabian_detailed"), block.index("self._showDailyInfo"))

	def test_shift_p_second_press_opens_prayer_window_and_first_stays_deferred(self):
		block = self.source[self.source.index("def script_prayerVerification"):self.source.index("def script_gregorianDate")]
		self.assertIn("self._press((self._deferred, self._showPrayerTimes))", block)
		self.assertNotIn("OnlinePrayerVerifier", self.source)

	def test_f12_triple_press_announces_and_does_not_open_window(self):
		block = self.source[self.source.index("def script_timeDateInfo"):self.source.index("def script_repeatLastAlert")]
		self.assertNotIn("_show_text", block)
		self.assertNotIn("_showDailyInfo", block)

	def test_no_nvda_or_wx_import_in_domain(self):
		for path in (ROOT / "addon/globalPlugins/awqati/domain").glob("*.py"):
			text = path.read_text(encoding="utf-8")
			self.assertNotRegex(text, r"(^|\n)\s*(import|from)\s+(wx|globalPluginHandler|gui|ui)(\.|\s|$)")


if __name__ == "__main__":
	unittest.main()
