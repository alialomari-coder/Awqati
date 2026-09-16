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
		self.assertEqual(10, len(gestures))
		self.assertEqual(10, len(set(value.lower() for value in gestures)))
		self.assertEqual({
			"nvda+alt+a", "nvda+f11", "nvda+control+shift+f11", "nvda+f12",
			"nvda+shift+f11", "nvda+shift+f12", "nvda+alt+f12", "nvda+g", "nvda+h", "nvda+shift+h",
		}, {value.lower() for value in gestures})

	def test_fifteen_unassigned_commands(self):
		methods = []
		for node in ast.walk(self.tree):
			if isinstance(node, ast.FunctionDef) and node.name.startswith("script_"):
				decorator = next((d for d in node.decorator_list if isinstance(d, ast.Call)), None)
				if decorator is not None and not any(k.arg == "gesture" for k in decorator.keywords):
					methods.append(node.name)
		self.assertEqual(15, len(methods), methods)

	def test_one_dispatcher_and_no_legacy_defaults(self):
		self.assertEqual(1, self.source.count("MultiPressDispatcher("))
		self.assertEqual(1, self.source.lower().count('gesture="kb:nvda+shift+f11"'))

	def test_triple_press_announces_and_does_not_open_windows(self):
		f11 = self.source[self.source.index("def script_prayerInfo"):self.source.index("def script_toggleAllAlerts")]
		f12 = self.source[self.source.index("def script_timeDateInfo"):self.source.index("def script_repeatLastAlert")]
		self.assertNotIn("_show_text", f11)
		self.assertNotIn("_show_text", f12)
		self.assertNotIn("open_daily_prayer_times_window", f11)
		self.assertNotIn("open_daily_info_window", f12)

	def test_no_nvda_or_wx_import_in_domain(self):
		for path in (ROOT / "addon/globalPlugins/awqati/domain").glob("*.py"):
			text = path.read_text(encoding="utf-8")
			self.assertNotRegex(text, r"(^|\n)\s*(import|from)\s+(wx|globalPluginHandler|gui|ui)(\.|\s|$)")


if __name__ == "__main__":
	unittest.main()
