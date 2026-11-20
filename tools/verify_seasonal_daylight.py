"""Task 1.2 independent JPL horizon crossings; explicit --fetch, offline replay.

Same conventional -0.833 degree center horizon, airless topocentric DE441.
Three-point quadratic crossing interpolation in a +/- 300 second bracket.
Reference code never imports NOAA positions; seeds only bracket the events.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import csv
import io
import json
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addon/globalPlugins'))
from awqati.domain.astronomy import annual_daylight, solar_day_for_local_date, julian_day, seasonal_daylight
from awqati.infrastructure import BundledTimezoneProvider

OUTPUT = ROOT / 'docs/seasonal_daylight_task12'
SITES = (
    ('riyadh', 24.7136, 46.6753, 'Asia/Riyadh', ()),
    ('london', 51.5074, -0.1278, 'Europe/London', ('2026-03-28', '2026-03-29', '2026-10-24', '2026-10-25')),
    ('sydney', -33.8688, 151.2093, 'Australia/Sydney', ('2026-04-04', '2026-04-05', '2026-10-03', '2026-10-04')),
    ('kiritimati', 1.8721, -157.4278, 'Pacific/Kiritimati', ()),
    ('equator', 0.0, 0.0, 'Etc/UTC', ()),
)

def crossing(rows, seed):
    y0, ym, y1 = (float(row[4]) + 0.833 for row in rows)
    assert y0 * y1 < 0, ('unbracketed crossing', rows)
    a, b, c = (y1 + y0) / 2 - ym, (y1 - y0) / 2, ym
    left, right = -1., 1.
    for _ in range(50):
        middle = (left + right) / 2
        y = a * middle**2 + b * middle + c
        if (y >= 0) == (y0 >= 0):
            left = middle
        else:
            right = middle
    return seed + timedelta(seconds=300 * (left + right) / 2)

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    zones = BundledTimezoneProvider()
    results, extrema, seasonal = [], [], []
    for name, lat, lon, tz, extras in SITES:
        zone = zones.get_timezone(tz)
        annual = annual_daylight(2026, lat, lon, zone)
        days = {date.fromisoformat(s) for s in ('2026-01-01', '2026-12-31', '2026-03-15', '2026-09-15') + extras}
        changes = [seasonal_daylight(datetime.combine(d, datetime.min.time(), tzinfo=zone), lat, lon, zone, annual=annual) for d in sorted(days)]
        days.update(f.reference_local_date for f in changes)
        # Include both solstices, reference dates and all nearby candidate days.
        for center in (date(2026, 6, 21), date(2026, 12, 21), annual.longest.days[0].local_date, annual.shortest.days[0].local_date):
            days.update(center + timedelta(days=i) for i in range(-3, 4))
        cases, seeds = [], []
        for day in sorted(days):
            solar = solar_day_for_local_date(day, lat, lon, zone)
            cases.append((day, solar))
            seeds.extend((solar.sunrise_utc, solar.sunset_utc, solar.next_sunrise_utc))
        # Sorted deduplicated TLIST avoids JPL's chronological-order ambiguity.
        times = sorted({s + timedelta(seconds=i) for s in seeds for i in (-300, 0, 300)})
        lookup = {}
        for batch, start in enumerate(range(0, len(times), 60)):
            subset = times[start:start + 60]
            params = dict(format='text', COMMAND="'10'", EPHEM_TYPE="'OBSERVER'", CENTER="'coord@399'",
                COORD_TYPE="'GEODETIC'", SITE_COORD=f"'{lon},{lat},0'",
                TLIST="'" + ','.join(f'{julian_day(t):.9f}' for t in subset) + "'",
                QUANTITIES="'4'", CSV_FORMAT="'YES'", CAL_FORMAT="'JD'", TIME_DIGITS="'FRACSEC'",
                ANG_FORMAT="'DEG'", APPARENT="'AIRLESS'", EXTRA_PREC="'YES'")
            url = 'https://ssd.jpl.nasa.gov/api/horizons.api?' + urllib.parse.urlencode(params)
            path = OUTPUT / f'{name}_{batch}_horizons.txt'
            if '--fetch' in sys.argv:
                path.write_bytes(urllib.request.urlopen(url, timeout=45).read())
                path.with_suffix('.json').write_text(json.dumps(dict(url=url, retrieved_at_utc=datetime.now(timezone.utc).isoformat()), indent=2))
            raw = path.read_text()
            rows = [r for r in csv.reader(io.StringIO(raw.split('$$SOE')[1].split('$$EOE')[0])) if r and r[0].strip()]
            assert len(rows) == len(subset)
            lookup.update(zip(subset, rows))
        references = {}
        for seed in set(seeds):
            references[seed] = crossing([lookup[seed + timedelta(seconds=i)] for i in (-300, 0, 300)], seed)
        for day, s in cases:
            light = (references[s.sunset_utc] - references[s.sunrise_utc]).total_seconds()
            night = (references[s.next_sunrise_utc] - references[s.sunset_utc]).total_seconds()
            results.append(dict(site=name, date=day.isoformat(), latitude=lat, longitude=lon, timezone=tz,
                actual_daylight_seconds=s.daylight.total_seconds(), reference_daylight_seconds=light,
                actual_night_seconds=s.night.total_seconds(), reference_night_seconds=night,
                difference_daylight_seconds=s.daylight.total_seconds()-light,
                difference_night_seconds=s.night.total_seconds()-night,
                passed=max(abs(s.daylight.total_seconds()-light), abs(s.night.total_seconds()-night)) <= 120))
        site_rows = [r for r in results if r['site'] == name]
        by_date = {r['date']: r for r in site_rows}
        for facts in changes:
            actual = facts.change.total_seconds()
            reference = by_date[facts.local_date.isoformat()]['reference_daylight_seconds'] - by_date[facts.reference_local_date.isoformat()]['reference_daylight_seconds']
            seasonal.append(dict(site=name, date=facts.local_date.isoformat(), reference_date=facts.reference_local_date.isoformat(),
                actual_change_seconds=actual, reference_change_seconds=reference, difference_seconds=actual-reference,
                passed=abs(actual-reference) <= 240))
        for label, extreme, op in (('longest', annual.longest, max), ('shortest', annual.shortest, min)):
            center = extreme.days[0].local_date
            window = [r for r in site_rows if abs((date.fromisoformat(r['date']) - center).days) <= 3]
            ref = op(window, key=lambda r: r['reference_daylight_seconds'])
            model_day = extreme.days[0].local_date.isoformat()
            model_row = next(r for r in window if r['date'] == model_day)
            extrema.append(dict(site=name, kind=label, model_date=model_day, reference_window_date=ref['date'],
                same_date=model_day == ref['date'], reference_gap_at_model_date_seconds=abs(ref['reference_daylight_seconds']-model_row['reference_daylight_seconds']),
                model_daylight_seconds=extreme.days[0].daylight.total_seconds(), model_night_seconds=extreme.days[0].night.total_seconds(),
                exact_dates=[s.local_date.isoformat() for s in extreme.days], rounded_dates=[d.isoformat() for d in extreme.rounded_minute_dates]))
        print(name, len(cases), 'compared', flush=True)
    polar = []
    for name, lat in (('arctic', 78.2232), ('antarctic', -78.2232)):
        times = [datetime(2026, month, 22, hour, tzinfo=timezone.utc) for month in (6, 12) for hour in range(24)]
        params = dict(format='text', COMMAND="'10'", EPHEM_TYPE="'OBSERVER'", CENTER="'coord@399'",
            COORD_TYPE="'GEODETIC'", SITE_COORD=f"'15.6469,{lat},0'",
            TLIST="'" + ','.join(f'{julian_day(t):.9f}' for t in times) + "'",
            QUANTITIES="'4'", CSV_FORMAT="'YES'", CAL_FORMAT="'JD'", TIME_DIGITS="'FRACSEC'",
            ANG_FORMAT="'DEG'", APPARENT="'AIRLESS'", EXTRA_PREC="'YES'")
        url = 'https://ssd.jpl.nasa.gov/api/horizons.api?' + urllib.parse.urlencode(params)
        path = OUTPUT / f'{name}_horizons.txt'
        if '--fetch' in sys.argv:
            path.write_bytes(urllib.request.urlopen(url, timeout=45).read())
            path.with_suffix('.json').write_text(json.dumps(dict(url=url, retrieved_at_utc=datetime.now(timezone.utc).isoformat()), indent=2))
        raw = path.read_text()
        rows = [r for r in csv.reader(io.StringIO(raw.split('$$SOE')[1].split('$$EOE')[0])) if r and r[0].strip()]
        assert len(rows) == 48
        for i, month in enumerate((6, 12)):
            elevations = [float(r[4]) for r in rows[i*24:(i+1)*24]]
            day = date(2026, month, 22)
            actual = solar_day_for_local_date(day, lat, 15.6469, timezone.utc)
            expected = 'polarDay' if min(elevations) > -0.833 else 'polarNight' if max(elevations) < -0.833 else 'normal'
            polar.append(dict(site=name, latitude=lat, longitude=15.6469, date=day.isoformat(),
                hourly_min_elevation=min(elevations), hourly_max_elevation=max(elevations),
                actual_state=actual.state.value, reference_state=expected, passed=actual.state.value == expected))
    (OUTPUT / 'polar_comparisons.json').write_text(json.dumps(polar, indent=2))
    (OUTPUT / 'comparisons.json').write_text(json.dumps(results, indent=2))
    (OUTPUT / 'extrema_comparisons.json').write_text(json.dumps(extrema, indent=2))
    (OUTPUT / 'seasonal_comparisons.json').write_text(json.dumps(seasonal, indent=2))
    summary = dict(cases=len(results), passed=sum(r['passed'] for r in results),
        max_daylight_difference_seconds=max(abs(r['difference_daylight_seconds']) for r in results),
        max_night_difference_seconds=max(abs(r['difference_night_seconds']) for r in results),
        tolerance_seconds=120, matching_extreme_dates=sum(r['same_date'] for r in extrema), extrema=len(extrema),
        max_extreme_reference_gap_seconds=max(r['reference_gap_at_model_date_seconds'] for r in extrema),
        seasonal_cases=len(seasonal), seasonal_passed=sum(r['passed'] for r in seasonal),
        seasonal_tolerance_seconds=240,
        max_seasonal_difference_seconds=max(abs(r['difference_seconds']) for r in seasonal),
        polar_cases=len(polar), polar_passed=sum(r['passed'] for r in polar))
    (OUTPUT / 'reference_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    extrema_accepted = all(r['same_date'] or (r['site'] == 'equator' and r['reference_gap_at_model_date_seconds'] <= 1) for r in extrema)
    return int(not extrema_accepted or summary['passed'] != summary['cases'] or summary['seasonal_passed'] != summary['seasonal_cases'] or summary['polar_passed'] != summary['polar_cases'])

if __name__ == '__main__':
    raise SystemExit(main())
