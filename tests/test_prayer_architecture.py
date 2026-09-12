from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
PACKAGE = ROOT / "dist" / "awqati-0.0.0.nvda-addon"


class PrayerArchitectureTests(unittest.TestCase):
	def test_pure_engine_imports_and_runs_with_python_s_and_no_nvda_or_network(self) -> None:
		script = """
from datetime import date, timezone
import sys
from awqati.domain import *
definition = CalculationMethodDefinition(CalculationMethod.MWL, 'MWL', 18, isha_angle=17)
request = PrayerCalculationRequest(date(2026, 1, 15), 24.6877, 46.7219, 'Etc/UTC',
    CalculationMethod.MWL, AsrMethod.STANDARD, HighLatitudeRule.AUTO)
result = PrayerCalculator().calculate(request, definition, timezone.utc,
    effective_method=CalculationMethod.MWL)
assert result.fajr < result.sunrise < result.dhuhr < result.asr < result.maghrib < result.isha
assert 'globalPluginHandler' not in sys.modules and 'wx' not in sys.modules and 'config' not in sys.modules
"""
		environment = os.environ.copy()
		environment["PYTHONPATH"] = str(PACKAGES)
		with tempfile.TemporaryDirectory() as working:
			result = subprocess.run([sys.executable, "-S", "-c", script], cwd=working,
				env=environment, capture_output=True, text=True, check=False)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_method_angles_and_offsets_exist_only_in_versioned_data(self) -> None:
		data = (ROOT / "addon/globalPlugins/awqati/data/calculation_methods/methods.json").read_text(encoding="utf-8")
		self.assertIn('"fajrAngle": 19.5', data)
		calculator = (ROOT / "addon/globalPlugins/awqati/domain/prayer.py").read_text(encoding="utf-8")
		for code in ("MAKKAH", "EGYPT", "PORTUGAL", "JORDAN", "TURKEY"):
			self.assertNotIn(f"CalculationMethod.{code}", calculator)

	def test_package_contains_engine_and_all_method_data(self) -> None:
		with zipfile.ZipFile(PACKAGE) as archive:
			names = set(archive.namelist())
		for name in (
			"globalPlugins/awqati/domain/clock.py",
			"globalPlugins/awqati/domain/prayer.py",
			"globalPlugins/awqati/domain/prayer_timeline.py",
			"globalPlugins/awqati/application/clock_service.py",
			"globalPlugins/awqati/application/prayer_service.py",
			"globalPlugins/awqati/application/prayer_state.py",
			"globalPlugins/awqati/infrastructure/calculation_method_repository.py",
			"globalPlugins/awqati/infrastructure/tzif_timezone.py",
			"globalPlugins/awqati/data/calculation_methods/methods.json",
			"globalPlugins/awqati/data/calculation_methods/country_methods.json",
			"globalPlugins/awqati/data/calculation_methods/NOTICE.txt",
		):
			self.assertIn(name, names)


if __name__ == "__main__":
	unittest.main()
