"""One isolated, validated JSON cache, atomically replaced beside its temp file."""
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from ..domain.on_this_day import Day, Entry, Context, Link, Section, Failure, OnThisDayError, SECTION_KEYS
from .on_this_day_links import safe_wikipedia_url

SCHEMA_VERSION = 2
MAX_CACHE_BYTES = 16 * 1024 * 1024


class DayCache:
    def __init__(self, path):
        self.path = Path(path)

    def load(self, local_date, language):
        try:
            if not self.path.exists():
                return None
            if self.path.stat().st_size > MAX_CACHE_BYTES:
                raise ValueError("cache too large")
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("invalid cache envelope")
            if (type(raw["schema"]) is not int or raw["schema"] != SCHEMA_VERSION or raw["date"] != local_date.isoformat()
                    or raw["language"] != language):
                return None
            if raw.get("unavailable") is True:
                datetime.fromisoformat(raw["fetched_at"])
                return OnThisDayError(Failure.UNAVAILABLE, "Wikipedia page absent (cached)")
            value = raw["day"]
            if (value["local_date"] != local_date.isoformat() or value["language"] != language
                    or not isinstance(value["title"], str) or not value["title"]
                    or type(value["revision"]) is not int or value["revision"] <= 0):
                raise ValueError("invalid day metadata")
            from urllib.parse import quote
            expected_url = f"https://{language}.wikipedia.org/w/index.php?title={quote(value['title'])}&oldid={value['revision']}"
            if value["source_url"] != expected_url:
                raise ValueError("invalid source URL")
            fetched = datetime.fromisoformat(value["fetched_at"])
            if fetched.tzinfo is None:
                raise ValueError("missing fetch timezone")
            if [s["key"] for s in value["sections"]] != list(SECTION_KEYS):
                raise ValueError("invalid section keys")
            sections = []
            for section in value["sections"]:
                failure = Failure(section["failure"]) if section["failure"] is not None else None
                if failure not in {None, Failure.UNAVAILABLE, Failure.EXTRACTION}:
                    raise ValueError("invalid cached section failure")
                if not isinstance(section["detail"], str) or not isinstance(section["entries"], list):
                    raise ValueError("invalid section")
                def links_for(content):
                    links = []
                    previous_end = 0
                    if not isinstance(content["links"], list):
                        raise ValueError("invalid links")
                    for link in content["links"]:
                        a, b = link["start"], link["end"]
                        if (type(a) is not int or type(b) is not int or not previous_end <= a < b <= len(content["text"])
                                or content["text"][a:b] != link["text"]
                                or safe_wikipedia_url(link["url"], language) != link["url"]):
                            raise ValueError("unsafe or mismatched cached link")
                        links.append(Link(link["text"], link["url"], a, b))
                        previous_end = b
                    return tuple(links)

                entries = []
                for entry in section["entries"]:
                    if (not isinstance(entry["text"], str) or not entry["text"].strip()
                            or (entry["year"] is not None and not isinstance(entry["year"], str))
                            or not isinstance(entry["context"], list)):
                        raise ValueError("invalid entry")
                    contexts = []
                    for context in entry["context"]:
                        if not isinstance(context["text"], str):
                            raise ValueError("invalid context text")
                        contexts.append(Context(context["text"], links_for(context)))
                    entries.append(Entry(entry["text"], entry["year"], tuple(contexts), links_for(entry)))
                if bool(entries) == bool(failure):
                    raise ValueError("inconsistent section status")
                sections.append(Section(section["key"], tuple(entries), failure, section["detail"]))
            return Day(local_date, language, value["title"], value["revision"], value["source_url"],
                       value["fetched_at"], tuple(sections))
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError) as error:
            raise OnThisDayError(Failure.STORAGE, "invalid or unreadable OnThisDay cache") from error

    def save(self, local_date, language, value):
        raw = dict(schema=SCHEMA_VERSION, date=local_date.isoformat(), language=language)
        if isinstance(value, OnThisDayError):
            if value.kind != Failure.UNAVAILABLE:
                raise ValueError("only confirmed absence may be cached")
            from datetime import timezone
            raw.update(unavailable=True, fetched_at=datetime.now(timezone.utc).isoformat())
        else:
            raw["day"] = asdict(value)
            raw["day"]["local_date"] = value.local_date.isoformat()
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=self.path.parent, prefix=f".{self.path.name}.",
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(raw, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, ValueError, TypeError) as error:
            raise OnThisDayError(Failure.STORAGE, "could not atomically save OnThisDay cache") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
