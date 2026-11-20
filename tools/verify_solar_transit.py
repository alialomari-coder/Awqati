"""Explicit developer-only JPL audit. Never imported by the offline add-on."""
from datetime import date, timedelta, timezone, datetime
from pathlib import Path
import csv
import io
import json
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addon/globalPlugins'))
from awqati.domain.astronomy import solar_day, julian_day
from awqati.infrastructure import BundledTimezoneProvider

OUTPUT = ROOT / 'docs/solar_transit_task11'
SITES = (
    ('dammam', 26.4207, 50.0888, 'Asia/Riyadh', ()),
    ('riyadh', 24.7136, 46.6753, 'Asia/Riyadh', ()),
    ('cairo', 30.0444, 31.2357, 'Africa/Cairo', ('2026-04-23', '2026-04-24', '2026-10-29', '2026-10-30')),
    ('london', 51.5074, -0.1278, 'Europe/London', ('2026-03-28', '2026-03-29', '2026-10-24', '2026-10-25')),
    ('sydney', -33.8688, 151.2093, 'Australia/Sydney', ('2026-04-04', '2026-04-05', '2026-10-03', '2026-10-04')),
    ('longyearbyen', 78.2232, 15.6469, 'Arctic/Longyearbyen', ()),
)
DATES = ('2026-03-20', '2026-06-21', '2026-09-23', '2026-12-21')
# Compact NOAA solar series: target 15 seconds in transit, 0.02 degrees in
# elevation. These exceed rounding/UT1 (<1 s), solar parallax (<0.0025 deg),
# and truncated solar longitude/nutation series errors by a modest allowance.
TIME_TOLERANCE_SECONDS = 15.0
ALTITUDE_TOLERANCE_DEGREES = 0.02


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    provider = BundledTimezoneProvider()
    results = []
    for name, lat, lon, tzid, extra in SITES:
        zone = provider.get_timezone(tzid)
        cases = []
        times = []
        for day_text in sorted(DATES + extra):
            day = date.fromisoformat(day_text)
            value = solar_day(day, lat, lon, transit_zone=zone)
            cases.append((day_text, value))
            times.extend(value.transit_utc + timedelta(seconds=s) for s in (-120, 0, 120))
        params = dict(format='text', COMMAND="'10'", EPHEM_TYPE="'OBSERVER'",
            CENTER="'coord@399'", COORD_TYPE="'GEODETIC'", SITE_COORD=f"'{lon},{lat},0'",
            TLIST="'" + ','.join(f'{julian_day(t):.9f}' for t in times) + "'",
            QUANTITIES="'4,42'", CSV_FORMAT="'YES'", CAL_FORMAT="'JD'",
            TIME_DIGITS="'FRACSEC'", ANG_FORMAT="'DEG'", APPARENT="'AIRLESS'",
            EXTRA_PREC="'YES'")
        url = 'https://ssd.jpl.nasa.gov/api/horizons.api?' + urllib.parse.urlencode(params)
        raw_path = OUTPUT / f'{name}_horizons.txt'
        if '--fetch' in sys.argv:
            raw = urllib.request.urlopen(url, timeout=45).read()
            raw_path.write_bytes(raw)
            (OUTPUT / f'{name}_request.json').write_text(json.dumps(dict(url=url,
                retrieved_at_utc=datetime.now(timezone.utc).isoformat()), indent=2), encoding='utf-8')
        raw = raw_path.read_text(encoding='utf-8')
        data = raw.split('$$SOE')[1].split('$$EOE')[0]
        rows = [row for row in csv.reader(io.StringIO(data)) if row and row[0].strip()]
        assert len(rows) == len(times), (name, rows)
        for index, (day_text, actual) in enumerate(cases):
            samples = rows[index * 3:index * 3 + 3]
            # CSV: JD, solar marker, event marker, azimuth, elevation, hour angle.
            left, right = samples[0], samples[2]
            h0, h1 = float(left[5]), float(right[5])
            assert h0 < 0 < h1, samples
            fraction = -h0 / (h1 - h0)
            jd = float(left[0]) + fraction * (float(right[0]) - float(left[0]))
            reference = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=jd - 2440587.5)
            # Quadratic interpolation at the independent H=0 root removes the
            # elevation curvature across the four-minute sample bracket.
            x = 2 * fraction - 1
            e0, em, e1 = (float(row[4]) for row in samples)
            elevation = em + (e1 - e0) * x / 2 + (e1 + e0 - 2 * em) * x * x / 2
            seconds = abs((actual.transit_utc - reference).total_seconds())
            degrees = abs(actual.transit_altitude_degrees - elevation)
            request = json.loads((OUTPUT / f'{name}_request.json').read_text())
            results.append(dict(site=name, date=day_text, latitude=lat, longitude=lon,
                timezone=tzid, actual_local=actual.transit_utc.astimezone(zone).isoformat(),
                actual_altitude=actual.transit_altitude_degrees,
                reference_local=reference.astimezone(zone).isoformat(), reference_altitude=elevation,
                difference_seconds=seconds, difference_degrees=degrees,
                passed=seconds <= TIME_TOLERANCE_SECONDS and degrees <= ALTITUDE_TOLERANCE_DEGREES,
                source='NASA JPL Horizons, Sun center, airless, sea-level topocentric',
                url=request['url'], retrieved_at_utc=request['retrieved_at_utc']))
        print(name, 'parsed', len(cases), flush=True)
    (OUTPUT / 'comparisons.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('cases', len(results), 'max seconds', max(r['difference_seconds'] for r in results),
        'max degrees', max(r['difference_degrees'] for r in results), flush=True)
    return int(not all(r['passed'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
