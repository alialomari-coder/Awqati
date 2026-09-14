from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import SettingsService  # noqa: E402
from awqati.domain import Instant, SettingsApplied, default_settings  # noqa: E402


class Repository:
	def __init__(self, settings):
		self.value = deepcopy(settings)

	def load(self):
		return deepcopy(self.value)

	def save(self, settings):
		self.value = deepcopy(settings)


class Clock:
	def __init__(self, value):
		self.value = value

	def now(self):
		return self.value


class SettingsReactivationTests(unittest.TestCase):
	def test_false_to_true_rebuilds_from_now_and_never_requests_catch_up(self) -> None:
		settings = default_settings()
		settings.general.all_automatic_alerts_enabled = False
		now = Instant(datetime(2026, 9, 14, 10, 30, tzinfo=timezone.utc))
		service = SettingsService(Repository(settings), Clock(now))
		events: list[SettingsApplied] = []
		service.events.subscribe(SettingsApplied, events.append)
		draft = service.open_draft()
		draft.settings.general.all_automatic_alerts_enabled = True
		service.apply(draft)
		self.assertEqual(events[0].automatic_alerts_rebuild_from, now)
		self.assertFalse(any("catch" in name for name in events[0].__dataclass_fields__))
		service.apply(service.open_draft())
		self.assertIsNone(events[1].automatic_alerts_rebuild_from)

	def test_true_to_false_keeps_every_child_setting(self) -> None:
		settings = default_settings()
		service = SettingsService(Repository(settings), Clock(Instant(datetime.now(timezone.utc))))
		draft = service.open_draft()
		draft.settings.general.all_automatic_alerts_enabled = False
		before = deepcopy(draft.settings.prayer), deepcopy(draft.settings.clock), deepcopy(draft.settings.adhkar)
		applied = service.apply(draft)
		self.assertEqual(before, (applied.prayer, applied.clock, applied.adhkar))


if __name__ == "__main__":
	unittest.main()
