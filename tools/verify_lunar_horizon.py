"""Replay immutable USNO fixtures offline. Network fetch is a separate tool."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addon/globalPlugins'))
from awqati.domain import lunar_horizon_events
from awqati.infrastructure import BundledTimezoneProvider

OUTPUT = ROOT / 'docs/lunar_horizon_task21'
# Chosen before reference acquisition: minute-rounded USNO, <=30s rounding,
# abbreviated lunar theory, TT/UT1 approximation and shallow polar crossings.
NORMAL_TOLERANCE_SECONDS = 90
POLAR_TOLERANCE_SECONDS = 180


def compare():
    zones = BundledTimezoneProvider()
    manifest = json.loads((OUTPUT/'reference_manifest.json').read_text(encoding='utf-8-sig'))
    sources = []
    for item in manifest:
        path = OUTPUT/item['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        body = json.loads(path.read_text(encoding='utf-8-sig'))
        assert not body.get('error')
        assert body['apiversion'] == '4.0.1'
        data = body['properties']['data']
        assert data['tz'] == 0 and not data['isdst']
        assert item['file'].endswith(f"{date(data['year'],data['month'],data['day']):%Y-%m-%d}.json")
        sources.append((item, body))
    results = []
    for case in json.loads((OUTPUT/'cases.json').read_text()):
        day = date.fromisoformat(case['date'])
        zone = zones.get_timezone(case['timezone'])
        calculated = lunar_horizon_events(day, case['latitude'], case['longitude'], zone)
        reference = {'Rise': [], 'Set': []}
        for item, body in sources:
            if not item['file'].startswith(case['site'].replace(' ', '_')+'_'):
                continue
            lon, lat = body['geometry']['coordinates']
            assert (lat, lon) == (case['latitude'], case['longitude'])
            data = body['properties']['data']
            source_day = date(data['year'], data['month'], data['day'])
            for event in data['moondata']:
                if event['phen'] not in reference or not event.get('time'):
                    continue
                # Some USNO records may carry 24:xx; do not assign next-day
                # values to the source date without normalizing them.
                hour, minute = map(int, event['time'].split(':'))
                utc = datetime.combine(source_day, datetime.min.time(), timezone.utc) + timedelta(hours=hour, minutes=minute)
                if utc.astimezone(zone).date() == day:
                    reference[event['phen']].append(utc)
        tolerance = POLAR_TOLERANCE_SECONDS if abs(case['latitude']) >= 65 else NORMAL_TOLERANCE_SECONDS
        row = dict(case, tolerance_seconds=tolerance, passed=True, events={})
        for kind, values in [('Rise', calculated.rises_utc), ('Set', calculated.sets_utc)]:
            expected = sorted(set(reference[kind]))
            errors = [(a-b).total_seconds() for a, b in zip(values, expected)]
            passed = len(values) == len(expected) and all(abs(e) <= tolerance for e in errors)
            row['events'][kind] = dict(calculated_local=[t.astimezone(zone).isoformat() for t in values],
                reference_local=[t.astimezone(zone).isoformat() for t in expected], signed_errors_seconds=errors,
                count_matches=len(values)==len(expected), passed=passed)
            row['passed'] &= passed
        results.append(row)
    errors = [abs(e) for row in results for event in row['events'].values() for e in event['signed_errors_seconds']]
    summary = dict(reference='USNO API 4.0.1, UTC dates; upper limb, sea level, flat horizon, 34 arcmin refraction',
        cases=len(results), compared_events=len(errors), max_absolute_error_seconds=max(errors),
        mean_absolute_error_seconds=sum(errors)/len(errors), passed=all(r['passed'] for r in results), results=results)
    (OUTPUT/'comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__ == '__main__':
    result = compare()
    print(json.dumps({k:v for k,v in result.items() if k != 'results'},indent=2))
    for row in result['results']:
        if not row['passed']:
            print(json.dumps(row,indent=2))
    raise SystemExit(int(not result['passed']))
