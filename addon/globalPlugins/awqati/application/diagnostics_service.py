"""Privacy-preserving technical diagnostics report."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
	awqati_version: str
	nvda_version: str
	python_version: str
	windows_version: str
	settings_schema_version: int
	location_data_version: str
	tz_data_version: str
	hijri_data_version: str
	calculation_method_data_version: str
	arabian_calendar_data_version: str
	timezone_id: str | None
	location_id: str | None
	calculation_method: str
	high_latitude_rule: str
	scheduler_status: str
	alerts_status: str


class DiagnosticsService:
	"""Format only approved support fields; no settings graph is accepted."""

	_FIELDS = (
		("Awqati version", "awqati_version"), ("NVDA version", "nvda_version"),
		("Python version", "python_version"), ("Windows version", "windows_version"),
		("Settings schemaVersion", "settings_schema_version"),
		("locationDataVersion", "location_data_version"), ("tzDataVersion", "tz_data_version"),
		("hijriDataVersion", "hijri_data_version"),
		("calculationMethodDataVersion", "calculation_method_data_version"),
		("arabianCalendarDataVersion", "arabian_calendar_data_version"),
		("Time zone", "timezone_id"), ("Location ID", "location_id"),
		("Calculation method", "calculation_method"),
		("High-latitude rule", "high_latitude_rule"),
		("Scheduler", "scheduler_status"), ("Alerts", "alerts_status"),
	)

	def create_report(self, snapshot: DiagnosticsSnapshot,
			labels: Mapping[str, str] | None = None) -> str:
		labels = labels or {}
		lines = [labels.get("title", "Awqati diagnostics")]
		for label, attribute in self._FIELDS:
			value = getattr(snapshot, attribute)
			lines.append(
				f"{labels.get(attribute, label)}: "
				f"{value if value not in (None, '') else labels.get('notAssigned', 'not assigned')}"
			)
		return "\n".join(lines)
