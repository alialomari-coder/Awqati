from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PLUGIN_PACKAGES) not in sys.path:
	sys.path.insert(0, str(PLUGIN_PACKAGES))

from awqati.application import CoordinateProvider, LocationDetectionError  # noqa: E402
from awqati.domain import LocationDetectionFailure  # noqa: E402
from awqati.infrastructure import WindowsLocationAdapter  # noqa: E402


class WindowsLocationAdapterTests(unittest.TestCase):
	def test_construction_is_inert_and_adapter_implements_port(self) -> None:
		calls: list[bool] = []
		adapter = WindowsLocationAdapter(native_reader=lambda: calls.append(True) or (1.0, 2.0))
		self.assertIsInstance(adapter, CoordinateProvider)
		self.assertEqual(calls, [])
		self.assertEqual((adapter.get_coordinates().latitude, adapter.get_coordinates().longitude), (1.0, 2.0))
		self.assertEqual(len(calls), 2)

	def test_invalid_coordinates_have_a_specific_failure(self) -> None:
		for coordinates in ((91, 0), (0, 181), (float("nan"), 0)):
			with self.subTest(coordinates=coordinates):
				with self.assertRaises(LocationDetectionError) as caught:
					WindowsLocationAdapter(native_reader=lambda value=coordinates: value).get_coordinates()
				self.assertEqual(caught.exception.failure, LocationDetectionFailure.INVALID_COORDINATES)

	def test_known_native_failure_is_preserved(self) -> None:
		def denied() -> tuple[float, float]:
			raise LocationDetectionError(LocationDetectionFailure.DENIED)
		with self.assertRaises(LocationDetectionError) as caught:
			WindowsLocationAdapter(native_reader=denied).get_coordinates()
		self.assertEqual(caught.exception.failure, LocationDetectionFailure.DENIED)

	def test_os_and_unknown_failures_are_contained(self) -> None:
		for error, reason in ((OSError("off"), LocationDetectionFailure.UNAVAILABLE), (RuntimeError("boom"), LocationDetectionFailure.API_ERROR)):
			def fail(value=error) -> tuple[float, float]:
				raise value
			with self.subTest(error=error), self.assertRaises(LocationDetectionError) as caught:
				WindowsLocationAdapter(native_reader=fail).get_coordinates()
			self.assertEqual(caught.exception.failure, reason)

	def test_timeout_configuration_rejects_nonpositive_values(self) -> None:
		for arguments in ({"timeout_seconds": 0}, {"poll_interval_seconds": 0}):
			with self.subTest(arguments=arguments), self.assertRaises(ValueError):
					WindowsLocationAdapter(**arguments)

	def test_public_adapter_import_does_not_require_zoneinfo(self) -> None:
		script = """
import importlib.abc
import sys

class BlockZoneinfo(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'zoneinfo':
            raise ModuleNotFoundError("blocked to emulate NVDA's trimmed runtime")
        return None

sys.meta_path.insert(0, BlockZoneinfo())
from awqati.infrastructure import WindowsLocationAdapter
assert WindowsLocationAdapter.__name__ == 'WindowsLocationAdapter'
assert 'zoneinfo' not in sys.modules
"""
		environment = os.environ.copy()
		environment["PYTHONPATH"] = str(PLUGIN_PACKAGES)
		result = subprocess.run(
			[sys.executable, "-c", script],
			env=environment,
			capture_output=True,
			text=True,
			check=False,
		)
		self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

	def test_source_has_no_network_reverse_geocoder_or_continuous_monitor(self) -> None:
		source = (PLUGIN_PACKAGES / "awqati/infrastructure/windows_location.py").read_text(encoding="utf-8").casefold()
		for forbidden in ("http://", "https://", "urllib", "requests", "socket", "positionchanged"):
			with self.subTest(forbidden=forbidden):
				self.assertNotIn(forbidden, source)
		self.assertIn("request_permissions", source)
		self.assertIn("register_for_report", source)
		self.assertIn("unregisterforreport", source)
		self.assertIn("done.wait", source)


if __name__ == "__main__":
	unittest.main()
