"""Immutable Wikipedia records. No NVDA imports or translated/generated history."""
from dataclasses import dataclass
from datetime import date
from enum import Enum


class Failure(str, Enum):
    UNAVAILABLE = "unavailable"
    CONNECTION = "connection"
    SERVER = "server"
    RATE_LIMIT = "rate_limit"
    ACCESS = "access"
    RESPONSE = "response"
    API = "api"
    EXTRACTION = "extraction"
    STORAGE = "storage"
    STALE = "stale"
    CANCELLED = "cancelled"


class OnThisDayError(RuntimeError):
    def __init__(self, kind: Failure, detail: str, *, retry_after: float = 60):
        super().__init__(detail)
        self.kind = kind
        self.retry_after = retry_after


SECTION_KEYS = ("events", "births", "deaths", "observances")


@dataclass(frozen=True)
class Link:
    text: str
    url: str
    # Python string offsets into the corresponding readable text, end exclusive.
    start: int
    end: int


@dataclass(frozen=True)
class Context:
    text: str
    links: tuple[Link, ...] = ()


@dataclass(frozen=True)
class Entry:
    # text retains the original year prefix when one is present.
    text: str
    year: str | None = None
    context: tuple[Context, ...] = ()
    links: tuple[Link, ...] = ()


@dataclass(frozen=True)
class Section:
    key: str
    entries: tuple[Entry, ...] = ()
    failure: Failure | None = None
    detail: str = ""


@dataclass(frozen=True)
class Day:
    local_date: date
    language: str
    title: str
    revision: int
    source_url: str
    fetched_at: str
    sections: tuple[Section, ...]

    def section(self, key: str) -> Section:
        return next(section for section in self.sections if section.key == key)
