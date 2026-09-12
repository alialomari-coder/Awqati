"""Small TZif-backed tzinfo fallback for trimmed Python runtimes without zoneinfo."""

from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
import re
import struct


@dataclass(frozen=True, slots=True)
class _TransitionType:
	offset: int
	is_dst: bool
	name: str


@dataclass(frozen=True, slots=True)
class _MonthRule:
	month: int
	week: int
	weekday: int
	hour: int = 2

	def local_datetime(self, year: int) -> datetime:
		first_weekday, days = monthrange(year, self.month)
		# POSIX Sunday=0; Python Monday=0.
		wanted = (self.weekday + 6) % 7
		day = 1 + (wanted - first_weekday) % 7 + (self.week - 1) * 7
		if self.week == 5 and day > days:
			day -= 7
		return datetime(year, self.month, day) + timedelta(hours=self.hour)


@dataclass(frozen=True, slots=True)
class _PosixRule:
	standard_name: str
	standard_offset: int
	dst_name: str | None = None
	dst_offset: int | None = None
	start: _MonthRule | None = None
	end: _MonthRule | None = None

	def type_for_utc(self, timestamp: int) -> _TransitionType:
		utc = datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
		if self.dst_name is None or self.start is None or self.end is None or self.dst_offset is None:
			return _TransitionType(self.standard_offset, False, self.standard_name)
		start = self.start.local_datetime(utc.year) - timedelta(seconds=self.standard_offset)
		end = self.end.local_datetime(utc.year) - timedelta(seconds=self.dst_offset)
		active = start <= utc < end if start < end else utc >= start or utc < end
		return _TransitionType(self.dst_offset if active else self.standard_offset, active,
			self.dst_name if active else self.standard_name)

	def type_for_local(self, local: datetime) -> _TransitionType:
		if self.dst_name is None or self.start is None or self.end is None or self.dst_offset is None:
			return _TransitionType(self.standard_offset, False, self.standard_name)
		start, end = self.start.local_datetime(local.year), self.end.local_datetime(local.year)
		active = start <= local < end if start < end else local >= start or local < end
		return _TransitionType(self.dst_offset if active else self.standard_offset, active,
			self.dst_name if active else self.standard_name)


class TzifTimezone(tzinfo):
	"""Timezone implementation backed by transitions plus the TZif POSIX footer."""

	def __init__(self, key: str, transitions: tuple[int, ...], indices: tuple[int, ...],
			types: tuple[_TransitionType, ...], future_rule: _PosixRule | None) -> None:
		self.key, self._transitions, self._indices, self._types = key, transitions, indices, types
		self._future_rule = future_rule
		self._default_index = next((i for i, item in enumerate(types) if not item.is_dst), 0)
		self._standard_offset = (future_rule.standard_offset if future_rule else
			next((item.offset for item in reversed(types) if not item.is_dst), types[0].offset))

	@classmethod
	def from_bytes(cls, data: bytes, key: str) -> "TzifTimezone":
		if len(data) < 44 or data[:4] != b"TZif":
			raise ValueError("not a TZif file")
		version = data[4:5]
		header = 0
		if version in (b"2", b"3", b"4"):
			header = 44 + _section_size(struct.unpack(">6I", data[20:44]), 4)
		if data[header:header + 4] != b"TZif":
			raise ValueError("invalid TZif header")
		counts = struct.unpack(">6I", data[header + 20:header + 44])
		ttisgmtcnt, ttisstdcnt, leapcnt, timecnt, typecnt, charcnt = counts
		time_size = 8 if version in (b"2", b"3", b"4") else 4
		cursor = header + 44
		format_code = ">" + ("q" if time_size == 8 else "i") * timecnt
		transitions = struct.unpack(format_code, data[cursor:cursor + timecnt * time_size]) if timecnt else ()
		cursor += timecnt * time_size
		indices = tuple(data[cursor:cursor + timecnt]); cursor += timecnt
		raw_types = []
		for _ in range(typecnt):
			raw_types.append(struct.unpack(">iBB", data[cursor:cursor + 6])); cursor += 6
		abbreviations = data[cursor:cursor + charcnt]; cursor += charcnt
		types = tuple(_TransitionType(value, bool(is_dst), _abbreviation(abbreviations, index))
			for value, is_dst, index in raw_types)
		if not types or any(index >= len(types) for index in indices):
			raise ValueError("invalid TZif transition types")
		cursor += leapcnt * (time_size + 4) + ttisstdcnt + ttisgmtcnt
		footer = data[cursor:].strip(b"\n").decode("ascii", errors="strict") if cursor < len(data) else ""
		return cls(key, tuple(transitions), indices, types, _parse_posix(footer) if footer else None)

	def _type_at_utc_timestamp(self, timestamp: int) -> _TransitionType:
		if self._future_rule is not None and (not self._transitions or timestamp > self._transitions[-1]):
			return self._future_rule.type_for_utc(timestamp)
		position = bisect_right(self._transitions, timestamp) - 1
		return self._types[self._indices[position] if position >= 0 else self._default_index]

	def _type_for_local(self, value: datetime) -> _TransitionType:
		naive = value.replace(tzinfo=None)
		seconds = int((naive - datetime(1970, 1, 1)).total_seconds())
		if self._future_rule is not None and (not self._transitions or seconds > self._transitions[-1] + 86400):
			return self._future_rule.type_for_local(naive)
		item = self._types[self._default_index]
		for _ in range(3):
			item = self._type_at_utc_timestamp(seconds - item.offset)
		return item

	def utcoffset(self, dt: datetime | None) -> timedelta:
		return timedelta(seconds=self._standard_offset if dt is None else self._type_for_local(dt).offset)

	def dst(self, dt: datetime | None) -> timedelta:
		if dt is None: return timedelta(0)
		item = self._type_for_local(dt)
		return timedelta(seconds=item.offset - self._standard_offset) if item.is_dst else timedelta(0)

	def tzname(self, dt: datetime | None) -> str:
		return self.key if dt is None else self._type_for_local(dt).name

	def fromutc(self, dt: datetime) -> datetime:
		if dt.tzinfo is not self: raise ValueError("fromutc requires this timezone")
		stamp = int((dt.replace(tzinfo=timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())
		return (dt + timedelta(seconds=self._type_at_utc_timestamp(stamp).offset)).replace(tzinfo=self)


def _section_size(counts: tuple[int, ...], time_size: int) -> int:
	ttisgmtcnt, ttisstdcnt, leapcnt, timecnt, typecnt, charcnt = counts
	return timecnt * time_size + timecnt + typecnt * 6 + charcnt + leapcnt * (time_size + 4) + ttisstdcnt + ttisgmtcnt


def _abbreviation(block: bytes, start: int) -> str:
	end = block.find(b"\0", start)
	return block[start:end if end >= 0 else len(block)].decode("ascii", errors="replace")


_POSIX = re.compile(r"(?P<std><[^>]+>|[A-Za-z]+)(?P<offset>[+-]?\d+)(?P<dst><[^>]+>|[A-Za-z]+)?(?P<dstoff>[+-]?\d+)?(?P<rest>.*)")
_MONTH = re.compile(r"M(\d+)\.(\d+)\.(\d+)(?:/(-?\d+))?")


def _parse_posix(value: str) -> _PosixRule:
	match = _POSIX.fullmatch(value)
	if match is None:
		raise ValueError("unsupported TZif POSIX footer")
	standard_name = match.group("std").strip("<>")
	standard_offset = -int(match.group("offset")) * 3600
	dst_name = match.group("dst")
	dst_offset_text = match.group("dstoff")
	rest = match.group("rest")
	if dst_name is None:
		return _PosixRule(standard_name, standard_offset)
	dst_name = dst_name.strip("<>")
	if not rest.startswith(","):
		raise ValueError("unsupported DST footer")
	parts = rest[1:].split(",")
	if len(parts) != 2:
		raise ValueError("unsupported DST rules")
	dst_offset = -int(dst_offset_text) * 3600 if dst_offset_text is not None else standard_offset + 3600
	return _PosixRule(standard_name, standard_offset, dst_name, dst_offset,
		_parse_month(parts[0]), _parse_month(parts[1]))


def _parse_month(value: str) -> _MonthRule:
	match = _MONTH.fullmatch(value)
	if match is None: raise ValueError("unsupported POSIX month rule")
	return _MonthRule(*(int(item) if item is not None else 2 for item in match.groups()))
