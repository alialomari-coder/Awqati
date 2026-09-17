import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py"


class Task54ReliabilityRegressionTests(unittest.TestCase):
	def test_global_plugin_contains_all_known_local_data_failures(self):
		tree = ast.parse(PLUGIN.read_text(encoding="utf-8"))
		initializer = next(
			node for node in ast.walk(tree)
			if isinstance(node, ast.FunctionDef) and node.name == "__init__"
		)
		handled = set()
		for handler in (node for node in initializer.body if isinstance(node, ast.Try)):
			for branch in handler.handlers:
				type_node = branch.type
				if isinstance(type_node, ast.Tuple):
					handled.update(
						item.id for item in type_node.elts if isinstance(item, ast.Name)
					)
		self.assertTrue({
			"ArabianCalendarDataError",
			"CalculationMethodDataError",
			"LocationDataError",
			"TimezoneDataError",
			"UmmAlQuraDataError",
		}.issubset(handled))

	def test_data_failure_is_reported_without_logging_a_traceback(self):
		source = PLUGIN.read_text(encoding="utf-8")
		self.assertIn('logHandler.log.error("Awqati local data could not be loaded: %s", error)', source)
		self.assertNotIn('logHandler.log.exception("Awqati local data', source)
		self.assertIn("Awqati data error", source)
		self.assertIn("Reinstall the add-on or restore the data, then restart NVDA.", source)


if __name__ == "__main__":
	unittest.main()
