"""Optional scientific synopsis facts; no presentation or heritage dependency."""
from dataclasses import dataclass

from .astronomy import SeasonalDaylight, SunDistance
from .lunar_distance import LunarDistance
from .lunar_horizon import LunarHorizonEvents
from .lunar_phases import UpcomingLunarPhases
from .lunar_transit import LunarTransitDay


@dataclass(frozen=True, slots=True)
class DailyAstronomyDetails:
    daylight: SeasonalDaylight | None
    sun_distance: SunDistance | None
    horizon: LunarHorizonEvents | None
    transit: LunarTransitDay | None
    lunar_distance: LunarDistance | None
    phases: UpcomingLunarPhases | None
