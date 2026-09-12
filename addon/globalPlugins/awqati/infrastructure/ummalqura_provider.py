"""Validated access to the bundled ICU Umm al-Qura month-start table."""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from ..domain import CalendarDate, CalendarId, CalendarOutOfRangeError


class UmmAlQuraDataError(RuntimeError):
	"""Bundled Umm al-Qura data is absent, corrupt, or internally inconsistent."""


class UmmAlQuraProvider:
	calendar_id = CalendarId.HIJRI_UMM_AL_QURA

	def __init__(self, data_directory: Path | None = None) -> None:
		root = data_directory or Path(__file__).resolve().parents[1] / "data" / "calendars" / "ummalqura"
		try:
			metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
			table_bytes = (root / metadata["tableFile"]).read_bytes()
		except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
			raise UmmAlQuraDataError("Umm al-Qura data could not be read") from error
		if hashlib.sha256(table_bytes).hexdigest() != metadata.get("tableFileSha256"):
			raise UmmAlQuraDataError("Umm al-Qura table SHA-256 mismatch")
		try:
			table = json.loads(table_bytes.decode("utf-8"))
			self._first_year = int(table["firstHijriYear"])
			self._last_year = int(table["lastHijriYear"])
			self._first_date = date.fromisoformat(table["firstGregorianDate"])
			self._masks = tuple(int(value) for value in table["monthLengthMasks"])
		except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
			raise UmmAlQuraDataError("Umm al-Qura table has an invalid schema") from error
		if (self._first_year, self._last_year, len(self._masks)) != (1300, 1600, 301):
			raise UmmAlQuraDataError("Umm al-Qura table must cover 1300 through 1600 AH")
		if metadata.get("hijriDataVersion") != table.get("hijriDataVersion"):
			raise UmmAlQuraDataError("Umm al-Qura data versions do not agree")
		if any(mask < 0 or mask > 0xFFF for mask in self._masks):
			raise UmmAlQuraDataError("Umm al-Qura month mask exceeds twelve bits")
		self._metadata = metadata
		starts = [0]
		for year in range(self._first_year, self._last_year + 1):
			for month in range(1, 13):
				starts.append(starts[-1] + self.month_length(year, month))
		self._month_starts = tuple(starts)

	@property
	def hijri_data_version(self) -> str:
		return str(self._metadata["hijriDataVersion"])

	@property
	def metadata(self) -> dict[str, object]:
		return dict(self._metadata)

	@property
	def first_supported_gregorian_date(self) -> date:
		return self._first_date

	@property
	def last_supported_gregorian_date(self) -> date:
		return self._first_date + timedelta(days=self._month_starts[-1] - 1)

	def month_length(self, year: int, month: int) -> int:
		if not self._first_year <= year <= self._last_year:
			raise CalendarOutOfRangeError("Umm al-Qura year must be from 1300 through 1600")
		if not 1 <= month <= 12:
			raise ValueError("month must be from 1 through 12")
		mask = self._masks[year - self._first_year]
		return 30 if mask & (1 << (12 - month)) else 29

	def from_gregorian(self, value: date) -> CalendarDate:
		if not isinstance(value, date):
			raise TypeError("value must be a Gregorian date")
		offset = (value - self._first_date).days
		if offset < 0 or offset >= self._month_starts[-1]:
			raise CalendarOutOfRangeError("Gregorian date is outside Umm al-Qura years 1300 through 1600")
		index = bisect_right(self._month_starts, offset) - 1
		year, month_index = divmod(index, 12)
		return CalendarDate(self._first_year + year, month_index + 1,
			offset - self._month_starts[index] + 1, self.calendar_id)

	def to_gregorian(self, value: CalendarDate) -> date:
		if not isinstance(value, CalendarDate):
			raise TypeError("value must be a CalendarDate")
		if value.calendar_id is not self.calendar_id:
			raise ValueError("expected HIJRI_UMM_AL_QURA date")
		length = self.month_length(value.year, value.month)
		if value.day > length:
			raise ValueError("day exceeds the selected Umm al-Qura month")
		index = (value.year - self._first_year) * 12 + value.month - 1
		return self._first_date + timedelta(days=self._month_starts[index] + value.day - 1)

	def add_days(self, value: CalendarDate, days: int) -> CalendarDate:
		if not isinstance(days, int) or isinstance(days, bool):
			raise TypeError("days must be an integer")
		return self.from_gregorian(self.to_gregorian(value) + timedelta(days=days))
