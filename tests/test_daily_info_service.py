from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import ArabianCalendarService, DailyInfoService  # noqa: E402
from awqati.domain import Location  # noqa: E402
from awqati.infrastructure import BundledArabianCalendarRepository  # noqa: E402


LOCATION = Location("riyadh", "Riyadh", 24.7, 46.7, "Asia/Riyadh")


class FakeAstronomy:
	def __init__(self, result="scientific", error: Exception | None = None) -> None:
		self.result = result
		self.error = error
		self.calls = 0

	def read(self, location):
		self.calls += 1
		if self.error:
			raise self.error
		return self.result


class FakeHeritage:
	def __init__(self, result="heritage", error: Exception | None = None) -> None:
		self.result = result
		self.error = error
		self.calls = 0

	def read(self, location):
		self.calls += 1
		if self.error:
			raise self.error
		return self.result


class DailyInfoServiceTests(unittest.TestCase):
	def test_heritage_only_does_not_need_astronomy(self) -> None:
		service = ArabianCalendarService(BundledArabianCalendarRepository())
		self.assertEqual(service.read_date(date(2024, 2, 27)).talaa.id, "saad_bula")

	def test_scientific_only_never_calls_heritage(self) -> None:
		astronomy = FakeAstronomy()
		heritage = FakeHeritage(error=AssertionError("heritage must not be called"))
		result = DailyInfoService(astronomy, heritage).read(LOCATION, include_arabian_calendar=False)
		self.assertEqual(result.scientific, "scientific")
		self.assertIsNone(result.heritage)
		self.assertEqual((astronomy.calls, heritage.calls), (1, 0))

	def test_combined_result_keeps_sections_separate(self) -> None:
		astronomy = FakeAstronomy(result={"kind": "scientific"})
		heritage = FakeHeritage(result={"kind": "heritage"})
		result = DailyInfoService(astronomy, heritage).read(LOCATION, include_arabian_calendar=True)
		self.assertEqual(result.scientific, {"kind": "scientific"})
		self.assertEqual(result.heritage, {"kind": "heritage"})
		self.assertIsNot(result.scientific, result.heritage)

	def test_astronomy_failure_does_not_block_independent_heritage_use_case(self) -> None:
		astronomy = FakeAstronomy(error=RuntimeError("astronomy failed"))
		with self.assertRaisesRegex(RuntimeError, "astronomy failed"):
			DailyInfoService(astronomy).read(LOCATION)
		service = ArabianCalendarService(BundledArabianCalendarRepository())
		self.assertEqual(service.read_date(date(2024, 8, 24)).suhail_day, 1)


if __name__ == "__main__":
	unittest.main()
