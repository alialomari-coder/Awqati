"""Explicit, sequential live probe; save official responses for offline tests.

Run from the repository root. No retries and no scheduled requests.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CASES = (("ar", "11 نوفمبر"), ("ar", "15 مارس"), ("ar", "1 يناير"),
         ("en", "November 11"), ("ar", "29 فبراير"), ("en", "February 29"))


def main():
    destination = ROOT / "tests/fixtures/on_this_day"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, (language, title) in enumerate(CASES):
        query = urlencode(dict(action="parse", page=title, prop="tocdata|text|revid",
                              format="json", formatversion=2, redirects=1,
                              disableeditsection=1, maxlag=5))
        url = f"https://{language}.wikipedia.org/w/api.php?{query}"
        request = Request(url, headers={"User-Agent": "Awqati/4.0 (NVDA accessibility add-on; OnThisDay compatibility probe)",
                                        "Accept": "application/json"})
        with urlopen(request, timeout=45) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("response too large")
        document = json.loads(raw)
        if "error" in document or "warnings" in document:
            raise ValueError(document.get("error", document.get("warnings")))
        name = f"{language}_{index}.json"
        (destination / name).write_bytes(raw)
        parsed = document["parse"]
        manifest.append(dict(file=name, url=url, title=parsed["title"], revid=parsed["revid"],
                             fetched_at=datetime.now(timezone.utc).isoformat(),
                             sha256=hashlib.sha256(raw).hexdigest()))
        (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name, parsed["revid"], len(raw), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
