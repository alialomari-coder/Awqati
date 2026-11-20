"""Run only task-5 checks; never build, install, or launch NVDA.

The embedded Python ignores PYTHONPATH. A temporary interpreter entry point
with an explicit search path lets existing subprocess tests import Awqati,
without modifying the installed interpreter or existing tests.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/historical_converter_task5"
MODULES = (
	"test_converter_integration", "test_settings_schema", "test_settings_repository", "test_calendar_prayer_integration",
	"test_advanced_converter", "test_conversion_result_dialog", "test_calendar_converter_entries", "test_calendar_converter_dialog", "test_historical_conversion", "test_historical_calendars", "test_calendar_providers",
	"test_calendar_service", "test_calendar_architecture", "test_calendar_data",
)


def run_checks() -> int:
	sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "addon/globalPlugins")]
	OUTPUT.mkdir(parents=True, exist_ok=True)
	suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in MODULES)
	with (OUTPUT / "tests.log").open("w", encoding="utf-8") as stream:
		result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
	summary = {
		"python": sys.version, "modules": MODULES, "tests": result.testsRun,
		"passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
		"failures": len(result.failures), "errors": len(result.errors),
		"skipped": len(result.skipped), "successful": result.wasSuccessful(),
	}
	(OUTPUT / "test_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
	print(json.dumps(summary, indent=2))
	return 0 if result.wasSuccessful() else 1


def main() -> int:
	if "--worker" in sys.argv:
		return run_checks()
	installation = Path(sys.executable).resolve().parent
	pth = installation / f"python{sys.version_info.major}{sys.version_info.minor}._pth"
	if not pth.exists():
		return run_checks()
	with tempfile.TemporaryDirectory(prefix="awqati-history-checks-") as working:
		working = Path(working)
		shutil.copy2(sys.executable, working / "python.exe")
		for dll in installation.glob("*.dll"):
			shutil.copy2(dll, working / dll.name)
		paths = [str((installation / line).resolve()) for line in pth.read_text().splitlines()
			if line.strip() and not line.startswith("#") and not line.startswith("import ")]
		paths.extend((str(ROOT / "addon/globalPlugins"), str(ROOT / "tests")))
		(working / pth.name).write_text("\n".join(paths) + "\n", encoding="utf-8")
		return subprocess.run([str(working / "python.exe"), "-B", str(Path(__file__).resolve()), "--worker"], cwd=ROOT).returncode


if __name__ == "__main__":
	raise SystemExit(main())
