from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import ArabicQiblaFormatter, EnglishQiblaFormatter, QiblaService  # noqa: E402
from awqati.domain import (  # noqa: E402
	Coordinates,
	KAABA_COORDINATES,
	Location,
	QiblaDirection,
	QiblaUndefinedError,
	describe_qibla_bearing,
	initial_qibla_bearing,
)


class QiblaBearingTests(unittest.TestCase):
	def test_independent_reference_cities_across_regions_and_hemispheres(self) -> None:
		# Static spherical regression values plus an independent WGS84 Vincenty
		# inverse solution (Survey Review 23(176), 1975, pp. 88-93).
		samples = {
			"Riyadh": (24.7136, 46.6753, 243.7978),
			"London": (51.5074, -0.1278, 118.9872),
			"New York": (40.7128, -74.0060, 58.4817),
			"Sydney": (-33.8688, 151.2093, 277.4996),
			"Cape Town": (-33.9249, 18.4241, 23.3526),
			"Tokyo": (35.6762, 139.6503, 292.9987),
			"Lima": (-12.0464, -77.0428, 72.0266),
		}
		for name, (latitude, longitude, expected) in samples.items():
			with self.subTest(city=name):
				actual = initial_qibla_bearing(Coordinates(latitude, longitude))
				self.assertGreaterEqual(actual, 0)
				self.assertLess(actual, 360)
				self.assertAlmostEqual(actual, expected, places=3)
				self.assertAlmostEqual(
					actual,
					_vincenty_initial_bearing(latitude, longitude, 21.422487, 39.826206),
					delta=0.5,
				)

	def test_kaaba_coordinates_are_single_exact_core_constant(self) -> None:
		self.assertEqual(KAABA_COORDINATES, Coordinates(21.422487, 39.826206))

	def test_cardinals_quadrants_wrap_and_tie_policy_are_central(self) -> None:
		cases = (
			(0, QiblaDirection.NORTH, None, 0),
			(360, QiblaDirection.NORTH, None, 0),
			(10, QiblaDirection.NORTH, QiblaDirection.EAST, 10),
			(350, QiblaDirection.NORTH, QiblaDirection.WEST, 10),
			(45, QiblaDirection.EAST, QiblaDirection.NORTH, 45),
			(90, QiblaDirection.EAST, None, 0),
			(135, QiblaDirection.SOUTH, QiblaDirection.EAST, 45),
			(180, QiblaDirection.SOUTH, None, 0),
			(225, QiblaDirection.WEST, QiblaDirection.SOUTH, 45),
			(270, QiblaDirection.WEST, None, 0),
			(315, QiblaDirection.NORTH, QiblaDirection.WEST, 45),
		)
		for bearing, direction, lean, amount in cases:
			with self.subTest(bearing=bearing):
				result = describe_qibla_bearing(bearing)
				self.assertEqual(result.direction, direction)
				self.assertEqual(result.lean_direction, lean)
				self.assertAlmostEqual(result.lean_degrees, amount)
				self.assertGreaterEqual(result.bearing_degrees, 0)
				self.assertLess(result.bearing_degrees, 360)

	def test_norm_and_non_finite_inputs(self) -> None:
		self.assertEqual(describe_qibla_bearing(-1).bearing_degrees, 359)
		self.assertEqual(describe_qibla_bearing(721).bearing_degrees, 1)
		for value in (math.nan, math.inf, -math.inf):
			with self.assertRaises(ValueError):
				describe_qibla_bearing(value)

	def test_coincident_and_antipodal_singularities_raise(self) -> None:
		with self.assertRaises(QiblaUndefinedError):
			initial_qibla_bearing(KAABA_COORDINATES)
		with self.assertRaises(QiblaUndefinedError):
			initial_qibla_bearing(Coordinates(-21.422487, -140.173794))

	def test_service_uses_the_effective_location(self) -> None:
		location = Location("riyadh", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh")
		result = QiblaService().calculate(location)
		self.assertAlmostEqual(result.bearing_degrees, 243.7978, places=3)


class QiblaFormatterTests(unittest.TestCase):
	def test_required_243_8_example_and_one_decimal_rounding(self) -> None:
		result = describe_qibla_bearing(243.797831989)
		self.assertEqual(result.direction, QiblaDirection.WEST)
		self.assertEqual(result.lean_direction, QiblaDirection.SOUTH)
		self.assertAlmostEqual(result.lean_degrees, 26.202168011)
		self.assertEqual(
			ArabicQiblaFormatter().format(result),
			"اتجاه القبلة نحو الغرب، مع الميل إلى الجنوب بمقدار 26.2 درجة؛ "
			"أي ما يعادل 243.8 درجة من الشمال الحقيقي.",
		)
		self.assertEqual(
			EnglishQiblaFormatter().format(result),
			"The Qibla is toward west, leaning 26.2 degrees toward south; "
			"243.8 degrees clockwise from true north.",
		)

	def test_exact_cardinal_omits_a_false_lean(self) -> None:
		result = describe_qibla_bearing(90)
		self.assertEqual(
			ArabicQiblaFormatter().format(result),
			"اتجاه القبلة نحو الشرق؛ أي ما يعادل 90.0 درجة من الشمال الحقيقي.",
		)
		self.assertEqual(
			EnglishQiblaFormatter().format(result),
			"The Qibla is toward east; 90.0 degrees clockwise from true north.",
		)


def _vincenty_initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	"""Independent test-only WGS84 inverse bearing; not product code."""
	flattening = 1 / 298.257223563
	u1 = math.atan((1 - flattening) * math.tan(math.radians(lat1)))
	u2 = math.atan((1 - flattening) * math.tan(math.radians(lat2)))
	l = math.radians(lon2 - lon1)
	lam = l
	for _ in range(100):
		sin_lam, cos_lam = math.sin(lam), math.cos(lam)
		sin_sigma = math.hypot(
			math.cos(u2) * sin_lam,
			math.cos(u1) * math.sin(u2) - math.sin(u1) * math.cos(u2) * cos_lam,
		)
		cos_sigma = math.sin(u1) * math.sin(u2) + math.cos(u1) * math.cos(u2) * cos_lam
		sigma = math.atan2(sin_sigma, cos_sigma)
		sin_alpha = math.cos(u1) * math.cos(u2) * sin_lam / sin_sigma
		cos2_alpha = 1 - sin_alpha**2
		cos2_sigma_m = (
			cos_sigma - 2 * math.sin(u1) * math.sin(u2) / cos2_alpha
			if cos2_alpha > 1e-15 else 0.0
		)
		c = flattening / 16 * cos2_alpha * (4 + flattening * (4 - 3 * cos2_alpha))
		previous = lam
		lam = l + (1 - c) * flattening * sin_alpha * (
			sigma + c * sin_sigma * (
				cos2_sigma_m + c * cos_sigma * (-1 + 2 * cos2_sigma_m**2)
			)
		)
		if abs(lam - previous) < 1e-12:
			break
	else:
		raise AssertionError("Vincenty reference did not converge")
	return math.degrees(math.atan2(
		math.cos(u2) * math.sin(lam),
		math.cos(u1) * math.sin(u2) - math.sin(u1) * math.cos(u2) * math.cos(lam),
	)) % 360


if __name__ == "__main__":
	unittest.main()
