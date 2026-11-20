"""Acquire JPL geometric vectors explicitly, or replay SHA-256 checked evidence."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
import math
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addon/globalPlugins'))
from awqati.domain import lunar_distance, julian_day

OUTPUT = ROOT/'docs/lunar_distance_task23'
# Fixed before retrieval: compact Meeus series/time approximation versus DE441;
# 20 km is 2% of the requested display step (1000 km), not an accuracy guarantee.
TOLERANCE_KM = 20
MOMENTS = [datetime(2026, 11, 1, tzinfo=timezone.utc)+timedelta(days=i) for i in range(31)]
MOMENTS += [datetime(2026, 11, 19, h, tzinfo=timezone.utc) for h in (1, 6, 12, 18, 23)]
MOMENTS += [datetime(y, m, d, 12, tzinfo=timezone.utc) for y,m,d in
            ((1901,1,1),(1950,6,15),(2000,1,1),(2050,7,1),(2099,12,31))]
MOMENTS.sort()


def main():
    raw_path = OUTPUT/'horizons_vectors.json'
    meta_path = OUTPUT/'reference_request.json'
    if '--fetch' in sys.argv:
        params = dict(format='json', COMMAND="'301'", CENTER="'500@399'",
            EPHEM_TYPE="'VECTORS'", VEC_CORR="'NONE'", VEC_TABLE="'1'",
            OUT_UNITS="'KM-S'", TIME_TYPE="'UT'", CSV_FORMAT="'YES'",
            TLIST="'"+'\n'.join(str(julian_day(t)) for t in MOMENTS)+"'", TLIST_TYPE="'JD'")
        url = 'https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        result = json.loads(raw)['result']
        if '$$SOE' not in result:
            raise RuntimeError(result)
        raw_path.write_bytes(raw)
        meta_path.write_text(json.dumps(dict(url=url, parameters=params,
            fetched_at_utc=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(raw).hexdigest()), indent=2), encoding='utf-8')
    raw = raw_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == json.loads(meta_path.read_text())['sha256']
    result = json.loads(raw)['result']
    assert 'Earth (399)' in result and 'Moon (301)' in result
    records = list(csv.reader(result.split('$$SOE')[1].split('$$EOE')[0].strip().splitlines()))
    assert len(records) == len(MOMENTS)
    rows = []
    for moment, record in zip(MOMENTS, records):
        assert abs(float(record[0])-julian_day(moment)) < 1e-8
        reference = math.sqrt(sum(float(record[i])**2 for i in (2,3,4)))
        calculated = lunar_distance(moment).distance_km
        rows.append(dict(utc=moment.isoformat(), jpl_km=reference,
            calculated_km=calculated, difference_km=calculated-reference))
    report = dict(definition='Simultaneous geometric Earth (399) center to Moon (301) center; no light time',
        tolerance_km=TOLERANCE_KM, count=len(rows),
        max_absolute_difference_km=max(abs(r['difference_km']) for r in rows), results=rows)
    (OUTPUT/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    assert report['max_absolute_difference_km'] <= TOLERANCE_KM


if __name__ == '__main__':
    main()
