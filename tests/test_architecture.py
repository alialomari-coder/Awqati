from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
CORE_ROOT = PLUGIN_PACKAGES / "awqati"


def _module_name(path: Path) -> tuple[str, bool]:
	relative = path.relative_to(PLUGIN_PACKAGES).with_suffix("")
	parts = list(relative.parts)
	is_package = parts[-1] == "__init__"
	if is_package:
		parts.pop()
	return ".".join(parts), is_package


def _project_sources() -> dict[str, tuple[Path, bool]]:
	return {_module_name(path)[0]: (path, _module_name(path)[1]) for path in CORE_ROOT.rglob("*.py")}


def _imports(module: str, path: Path, is_package: bool) -> set[str]:
	tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
	result: set[str] = set()
	package = module if is_package else module.rpartition(".")[0]
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			result.update(alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom):
			if node.level:
				name = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
			elif node.module:
				name = node.module
			else:
				continue
			result.add(name)
	return result


def _layer(module: str) -> str | None:
	for name in ("domain", "application", "infrastructure", "nvda_adapter"):
		if module == f"awqati.{name}" or module.startswith(f"awqati.{name}."):
			return name
	if module == "awqati":
		return "nvda_adapter"
	return None


class ArchitectureTests(unittest.TestCase):
	def test_domain_has_no_platform_io_or_outer_layer_imports(self) -> None:
		for module, (path, is_package) in _project_sources().items():
			if _layer(module) != "domain":
				continue
			for imported in _imports(module, path, is_package):
				with self.subTest(module=module, imported=imported):
					self.assertNotIn(imported.split(".")[0], {
						"addonHandler", "api", "config", "ctypes", "globalPluginHandler",
						"gui", "os", "pathlib", "socket", "ui", "urllib", "winreg", "wx",
					})
					self.assertNotIn(_layer(imported), {"application", "infrastructure", "nvda_adapter"})

	def test_application_has_no_platform_nvda_or_io_imports(self) -> None:
		for module, (path, is_package) in _project_sources().items():
			if _layer(module) != "application":
				continue
			for imported in _imports(module, path, is_package):
				with self.subTest(module=module, imported=imported):
					self.assertNotIn(imported.split(".")[0], {
						"addonHandler", "api", "config", "ctypes", "globalPluginHandler", "gui",
						"os", "pathlib", "socket", "subprocess", "ui", "urllib", "winreg", "wx",
					})
					self.assertNotIn(_layer(imported), {"infrastructure", "nvda_adapter"})

	def test_dependency_direction_and_import_graph_are_acyclic(self) -> None:
		sources = _project_sources()
		allowed = {
			"domain": {"domain"},
			"application": {"domain", "application"},
			"infrastructure": {"domain", "application", "infrastructure"},
			"nvda_adapter": {"domain", "application", "infrastructure", "nvda_adapter"},
		}
		graph: dict[str, set[str]] = {module: set() for module in sources}
		for module, (path, is_package) in sources.items():
			origin_layer = _layer(module)
			for imported in _imports(module, path, is_package):
				target_layer = _layer(imported)
				if origin_layer and target_layer:
					with self.subTest(module=module, imported=imported):
						self.assertIn(target_layer, allowed[origin_layer])
				if imported in sources:
					graph[module].add(imported)
				else:
					candidates = [candidate for candidate in sources if imported.startswith(candidate + ".")]
					if candidates:
						graph[module].add(max(candidates, key=len))

		visiting: set[str] = set()
		visited: set[str] = set()

		def visit(module: str, trail: tuple[str, ...]) -> None:
			if module in visiting:
				self.fail("Circular import: " + " -> ".join((*trail, module)))
			if module in visited:
				return
			visiting.add(module)
			for dependency in graph[module]:
				visit(dependency, (*trail, module))
			visiting.remove(module)
			visited.add(module)

		for module in graph:
			visit(module, ())

	def test_domain_and_application_import_in_standalone_python(self) -> None:
		script = """
from datetime import datetime, timezone
import sys
from awqati.application import NowProvider
from awqati.domain import DomainEvent, Instant, Location
from support.event_clock import EventClock

first = Instant(datetime(2026, 1, 2, tzinfo=timezone.utc))
second = Instant(datetime(2026, 2, 3, tzinfo=timezone.utc))
location = Location('sa-riyadh', 'Riyadh', 24.7136, 46.6753, 'Asia/Riyadh')
event = DomainEvent(first)
clock = EventClock(first)
assert isinstance(clock, NowProvider)
assert clock.now() == event.occurred_at
clock.set(second)
assert clock.now() == second
assert location.timezone_id == 'Asia/Riyadh'
assert 'globalPluginHandler' not in sys.modules
assert 'wx' not in sys.modules
"""
		environment = os.environ.copy()
		environment["PYTHONPATH"] = os.pathsep.join((str(PLUGIN_PACKAGES), str(ROOT / "tests")))
		with tempfile.TemporaryDirectory() as working_directory:
			result = subprocess.run(
				[sys.executable, "-S", "-c", script],
				cwd=working_directory,
				env=environment,
				capture_output=True,
				text=True,
				check=False,
			)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
	unittest.main()
