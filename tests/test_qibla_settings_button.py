"""Regression coverage for the settings Qibla button."""

from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]


class QiblaSettingsButtonTests(unittest.TestCase):
	def setUp(self) -> None:
		self.panel = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/settings_panel.py").read_text(encoding="utf-8")
		self.plugin = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text(encoding="utf-8")
		self.ui = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/ui.py").read_text(encoding="utf-8")

	def test_button_uses_the_same_qibla_command_path_as_the_existing_gesture(self) -> None:
		self.assertIn("show_qibla: Callable[[], None] | None = None", self.ui)
		self.assertIn("show_qibla=self._announce_qibla", self.plugin)
		self.assertIn("context.show_qibla()", self.panel)
		announce = self.plugin[
			self.plugin.index("def _announce_qibla"):
			self.plugin.index("def _press")
		]
		self.assertIn("self._say(lambda: self._content.qibla_text(self._language()))", announce)
		gesture = self.plugin[
			self.plugin.index("def script_ghurubiQibla"):
			self.plugin.index("def script_hijriCalendars")
		]
		self.assertIn("self._announce_qibla", gesture)
		self.assertNotIn("qibla_text", gesture)
		self.assertIn('gesture="kb:NVDA+g"', self.plugin)

	def test_button_is_created_after_location_controls_and_before_all_alerts(self) -> None:
		make = self.panel[self.panel.index("def makeSettings"):self.panel.index("def _register")]
		location = make.index("self.location_controls = LocationControls")
		button = make.index('self.show_qibla = wx.Button(self, label=_("Show Qibla direction"))')
		all_alerts = make.index('self.all_alerts = wx.CheckBox(self, label=_("Enable all automatic alerts"))')
		self.assertLess(location, button)
		self.assertLess(button, all_alerts)
		self.assertLess(make.index("self.SetLayoutDirection"), button)
		self.assertIn('self._register("showQibla", self.show_qibla)', make)

	def test_button_label_is_gettext_translated_exactly_to_arabic(self) -> None:
		tree = ast.parse(self.panel)
		labels = [
			node.args[0].value
			for node in ast.walk(tree)
			if isinstance(node, ast.Call)
			and isinstance(node.func, ast.Name)
			and node.func.id == "_"
			and node.args
			and isinstance(node.args[0], ast.Constant)
		]
		self.assertIn("Show Qibla direction", labels)
		catalog = (ROOT / "addon/locale/ar/LC_MESSAGES/nvda.po").read_text(encoding="utf-8")
		self.assertIn('msgid "Show Qibla direction"\nmsgstr "عرض اتجاه القبلة"', catalog)


if __name__ == "__main__":
	unittest.main()
