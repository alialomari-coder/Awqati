"""Build-time only: complete bounded GeoNames-ID batches from Wikidata (CC0)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import time
import urllib.error
from pathlib import Path
import urllib.parse
import urllib.request

ARAB_COUNTRIES = frozenset("SA AE BH KW QA OM YE IQ JO PS LB SY EG SD SO DJ KM LY TN DZ MA MR".split())


def extract(data, admin_paths, output):
    identities = set()
    for code in sorted(ARAB_COUNTRIES):
        records = json.loads(gzip.decompress((data / "countries" / (code + ".json.gz")).read_bytes()))["cities"]
        identities.update(r["i"] for r in records)
    for path in admin_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) >= 4 and fields[0].split(".")[0] in ARAB_COUNTRIES:
                identities.add(fields[3])
    ids = sorted(identities, key=int)
    batches = [ids[i:i + 1000] for i in range(0, len(ids), 1000)]
    def fetch(batch):
        query = 'SELECT ?id ?item ?label WHERE { VALUES ?id { ' + ' '.join(json.dumps(i) for i in batch) + ' } ?item wdt:P1566 ?id; rdfs:label ?label. FILTER(LANG(?label)="ar") }'
        url = "https://query.wikidata.org/sparql"
        body = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"User-Agent": "Awqati-build/0.4 (offline Arabic place-name audit)", "Accept": "application/sparql-results+json"})
        for attempt in range(4):
            try:
                raw = urllib.request.urlopen(request, timeout=55).read()
                break
            except urllib.error.HTTPError as error:
                if error.code not in (429, 502, 503, 504) or attempt == 3:
                    raise
                time.sleep(65)
        print("Validated batch", batch[0], "bytes", len(raw), flush=True)
        time.sleep(61)  # Respect the endpoint's outage limit of one request/minute.
        result = json.loads(raw)  # Truncated JSON is a hard failure; never use partial responses.
        assert set(result["head"]["vars"]) == {"id", "item", "label"}
        names = []
        for row in result["results"]["bindings"]:
            assert row["id"]["value"] in batch and row["label"].get("xml:lang") == "ar"
            names.append({"geonameId": row["id"]["value"], "entity": row["item"]["value"].rsplit("/", 1)[-1], "ar": row["label"]["value"]})
        return {"requestedIds": batch, "query": query, "responseSha256": hashlib.sha256(raw).hexdigest(), "names": names, "complete": True}
    with ThreadPoolExecutor(max_workers=1) as executor:
        results = list(executor.map(fetch, batches))
    document = {"schemaVersion": 1, "version": "wikidata-arab-2026-09-15.1", "retrievedAt": "2026-09-15", "license": "CC0-1.0", "source": "https://query.wikidata.org/sparql", "licenseUrl": "https://www.wikidata.org/wiki/Wikidata:Licensing", "countries": sorted(ARAB_COUNTRIES), "requestedCount": len(ids), "batches": results}
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Complete batches:", len(results), "requested IDs:", len(ids), "Arabic labels:", sum(len(r["names"]) for r in results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--admin1", type=Path, required=True)
    parser.add_argument("--admin2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    extract(args.data, (args.admin1, args.admin2), args.output)
