"""Task 1.3 geometric center-to-center JPL ranges; offline unless --fetch."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import io
import json
import math
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/sun_distance_task13'
sys.path.insert(0, str(ROOT / 'addon/globalPlugins'))
from awqati.domain.astronomy import julian_day, sun_distance

# Preselected acceptance bound: below the 50,000 km half-step of speech.
TOLERANCE_KM = 25_000
DATES = sorted({f'{year}-{day}T12:00:00+00:00'
    for year in (1901, 1950, 2000, 2026, 2050, 2099)
    for day in ('01-03', '03-20', '06-21', '07-06', '09-23', '12-21')}
    | {f'2026-{day}T12:00:00+00:00' for day in
       ('01-01', '01-08', '07-01', '07-11', '02-15', '04-15', '05-15', '08-15', '10-15', '11-15')}
    | {'2026-03-20T00:00:00+00:00', '2026-03-20T23:59:59+00:00',
       '1901-01-01T00:00:00+00:00', '2099-12-31T23:59:59+00:00'})


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    times = [datetime.fromisoformat(s) for s in DATES]
    params = dict(format='text', COMMAND="'10'", EPHEM_TYPE="'VECTORS'",
        CENTER="'500@399'", TIME_TYPE="'UT'", TLIST_TYPE="'JD'",
        TLIST="'" + ','.join(f'{julian_day(t):.9f}' for t in times) + "'",
        VEC_CORR="'NONE'", VEC_TABLE="'3'", OUT_UNITS="'KM-S'",
        CSV_FORMAT="'YES'", CAL_TYPE="'GREGORIAN'")
    url = 'https://ssd.jpl.nasa.gov/api/horizons.api?' + urllib.parse.urlencode(params)
    path = OUTPUT / 'horizons_vectors.txt'
    if '--fetch' in sys.argv:
        raw_bytes = urllib.request.urlopen(url, timeout=45).read()
        if b'$$SOE' not in raw_bytes:
            raise RuntimeError(raw_bytes.decode())
        path.write_bytes(raw_bytes)
        (OUTPUT / 'horizons_request.json').write_text(json.dumps(dict(url=url,
            parameters=params, retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(raw_bytes).hexdigest()), indent=2), encoding='utf-8')
    raw = path.read_text(encoding='utf-8')
    request = json.loads((OUTPUT / 'horizons_request.json').read_text())
    assert request['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert request['parameters'] == params
    assert 'Sun (10)' in raw and 'Earth (399)' in raw and 'GEOMETRIC' in raw
    assert '{source: DE441}' in raw and 'KM-S' in raw
    rows = [r for r in csv.reader(io.StringIO(raw.split('$$SOE')[1].split('$$EOE')[0]))
        if r and r[0].strip()]
    assert len(rows) == len(times)
    results = []
    for moment, row in zip(times, rows):
        assert abs(float(row[0]) - julian_day(moment)) < 1e-8
        reference = float(row[9])  # JDTDB/calendar, X Y Z VX VY VZ LT RG RR (UT here).
        assert abs(reference - math.sqrt(sum(float(row[i])**2 for i in (2, 3, 4)))) < 0.001
        calculated = sun_distance(moment).distance_km
        error = calculated - reference
        results.append(dict(utc=moment.isoformat(), calculated_km=calculated,
            jpl_km=reference, signed_error_km=error, absolute_error_km=abs(error),
            passed=abs(error) <= TOLERANCE_KM))
    summary = dict(definition='Simultaneous geometric Earth (399) center to Sun (10) center; no light-time',
        tolerance_km=TOLERANCE_KM, count=len(results),
        max_absolute_error_km=max(r['absolute_error_km'] for r in results),
        mean_absolute_error_km=sum(r['absolute_error_km'] for r in results)/len(results),
        passed=all(r['passed'] for r in results), results=results)
    (OUTPUT / 'comparison.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k != 'results'}, indent=2))
    return int(not summary['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
