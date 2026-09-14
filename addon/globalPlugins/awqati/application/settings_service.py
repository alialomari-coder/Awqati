"""Draft and commit orchestration for Awqati settings."""

from __future__ import annotations

from collections.abc import Container
from copy import deepcopy

from ..domain import (
	AwqatiSettings,
	LocationChanged,
	SettingsApplied,
	SettingsValidationError,
	validate_settings,
)
from .events import EventDispatcher
from .ports import NowProvider, SettingsRepository


class ClosedSettingsDraftError(RuntimeError):
	"""A discarded draft cannot be edited or applied."""


class SettingsDraft:
	"""A deep, disposable working copy with an independently refreshable base."""

	def __init__(self, settings: AwqatiSettings) -> None:
		self._base = deepcopy(settings)
		self._settings = deepcopy(settings)
		self._closed = False

	@property
	def settings(self) -> AwqatiSettings:
		if self._closed:
			raise ClosedSettingsDraftError("the settings draft has been discarded")
		return self._settings

	@property
	def base(self) -> AwqatiSettings:
		if self._closed:
			raise ClosedSettingsDraftError("the settings draft has been discarded")
		return deepcopy(self._base)

	def discard(self) -> None:
		self._closed = True

	def refresh_base(self, settings: AwqatiSettings) -> None:
		if self._closed:
			raise ClosedSettingsDraftError("the settings draft has been discarded")
		self._base = deepcopy(settings)


class SettingsService:
	"""Load runtime settings and apply fully validated drafts."""

	def __init__(self, repository: SettingsRepository, clock: NowProvider,
			events: EventDispatcher | None = None,
			valid_timezone_ids: Container[str] | None = None) -> None:
		self._repository = repository
		self._clock = clock
		self._events = events or EventDispatcher()
		self._valid_timezone_ids = valid_timezone_ids
		loaded = repository.load()
		self.validate(loaded)
		self._runtime = deepcopy(loaded)

	@property
	def events(self) -> EventDispatcher:
		return self._events

	@property
	def runtime_settings(self) -> AwqatiSettings:
		return deepcopy(self._runtime)

	def open_draft(self) -> SettingsDraft:
		return SettingsDraft(self._runtime)

	def validate(self, settings: AwqatiSettings) -> None:
		"""Run the single complete validation path, including deployed IANA data."""
		validate_settings(settings)
		if settings.location is not None and self._valid_timezone_ids is not None:
			timezone_id = settings.location.location.timezone_id
			if timezone_id not in self._valid_timezone_ids:
				raise SettingsValidationError(
					"location.location.timezoneId is not included in the bundled IANA data",
					path="location.location.timezoneId",
					code="invalidTimezone",
				)

	def apply(self, draft: SettingsDraft) -> AwqatiSettings:
		candidate = deepcopy(draft.settings)
		self.validate(candidate)
		previous_location = self._effective_location(self._runtime)
		current_location = self._effective_location(candidate)
		alerts_reenabled = (
			not self._runtime.general.all_automatic_alerts_enabled
			and candidate.general.all_automatic_alerts_enabled
		)
		self._repository.save(candidate)
		self._runtime = deepcopy(candidate)
		draft.refresh_base(candidate)
		now = self._clock.now()
		if previous_location != current_location:
			self._events.publish(LocationChanged(now, previous_location, current_location))
		self._events.publish(SettingsApplied(now, candidate.schema_version, now if alerts_reenabled else None))
		return deepcopy(candidate)

	@staticmethod
	def _effective_location(settings: AwqatiSettings):
		return settings.location.location if settings.location is not None else None
