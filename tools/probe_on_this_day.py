"""Opt-in live service smoke test; never loaded by the NVDA add-on."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from addon.globalPlugins.awqati.application.on_this_day import OnThisDayService
from addon.globalPlugins.awqati.infrastructure.on_this_day_cache import DayCache
from addon.globalPlugins.awqati.infrastructure.on_this_day_wikipedia import WikipediaDayProvider, WikipediaTransport


class CountedTransport(WikipediaTransport):
    def __init__(self):
        self.requests = 0

    def read_json(self, *args, **kwargs):
        self.requests += 1
        return super().read_json(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="authorize two explicit Wikipedia requests")
    args = parser.parse_args()
    if not args.live:
        parser.error("pass --live to run two real requests; offline tests use unittest")
    records = []
    for language in ("ar", "en"):
        transport = CountedTransport()
        with tempfile.TemporaryDirectory() as directory:
            def create():
                return OnThisDayService(WikipediaDayProvider(transport), DayCache(Path(directory) / "cache.json"),
                                       language=lambda: language, dispatch=lambda callback: None)
            service = create()
            try:
                first = service.request().result(timeout=60)
                assert first == service.request().result(timeout=10)
            finally:
                service.close()
            restored = create()
            try:
                assert first == restored.request().result(timeout=10)
            finally:
                restored.close()
            assert transport.requests == 1
            assert all(s.failure is None for s in first.sections)
            records.append(dict(language=language, local_date=first.local_date.isoformat(), title=first.title,
                                revision=first.revision, source_url=first.source_url, fetched_at=first.fetched_at,
                                requests=transport.requests, restored_without_network=True,
                                counts={s.key: len(s.entries) for s in first.sections},
                                links={s.key: sum(len(e.links) for e in s.entries) for s in first.sections}))
    destination = ROOT / "docs/on_this_day_live_probe.json"
    destination.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
