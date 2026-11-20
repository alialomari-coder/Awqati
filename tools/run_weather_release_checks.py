"""Run weather and focused regressions without building or changing stable packages."""
from pathlib import Path
import sys
import unittest
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "addon/globalPlugins")]

if __name__ == "__main__":
    installation = Path(sys.executable).parent
    pth = installation / "python313._pth"
    if pth.exists() and "--worker" not in sys.argv:
        with tempfile.TemporaryDirectory(prefix="awqati-weather-python-") as temporary:
            target = Path(temporary)
            shutil.copy2(sys.executable, target / "python.exe")
            for dll in installation.glob("*.dll"): shutil.copy2(dll, target / dll.name)
            paths = [str((installation / line).resolve()) for line in pth.read_text().splitlines() if line and not line.startswith(("#", "import "))]
            paths += [str(ROOT), str(ROOT / "tests"), str(ROOT / "addon/globalPlugins"), str(ROOT / ".build-deps")]
            (target / pth.name).write_text("\n".join(paths) + "\n")
            raise SystemExit(subprocess.call([str(target / "python.exe"), "-B", str(Path(__file__).resolve()), "--worker"]))
    suite = unittest.TestSuite()
    for pattern in ("test_release_package.py", "test_final_help.py", "test_scaffold.py", "test_weather*.py", "test_settings_repository.py", "test_settings_service.py",
                    "test_daily_info_service.py", "test_daily_info_formatters.py", "test_daily_synopsis_integration.py", "test_architecture.py",
                    "test_settings_schema.py", "test_settings_architecture.py", "test_task33_settings.py", "test_task34_settings.py",
                    "test_settings_reactivation.py", "test_settings_ui_followup.py", "test_task51_multipress.py", "test_command_cleanup.py"):
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
