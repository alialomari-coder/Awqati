"""Fetch USNO only on explicit --fetch; ordinary checks replay hashed evidence."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addon/globalPlugins'))
from awqati.domain.lunar_phases import lunar_phase_events, PrincipalPhase
from awqati.domain.astronomy import _tt_jd_to_utc, _lunar_phase_event_utc, julian_day
OUT = ROOT/'docs/lunar_phases_task24'
YEARS = (1901, 1950, 2000, 2026, 2050, 2099)
# Fixed before retrieval/comparison: 90 s Meeus truncation/time-model allowance
# plus 30 s reference minute rounding. Acceptance is not a global guarantee.
TOLERANCE_SECONDS = 120
NAMES = dict(zip(('New Moon','First Quarter','Full Moon','Last Quarter'), PrincipalPhase))


def main():
    if '--fetch' in sys.argv:
        entries = []
        for year in YEARS:
            url = f'https://aa.usno.navy.mil/api/moon/phases/year?year={year}'
            with urllib.request.urlopen(url, timeout=45) as response:
                raw = response.read()
            data = json.loads(raw)
            if 'phasedata' not in data:
                raise RuntimeError(data)
            filename = f'usno_{year}.json'
            (OUT/filename).write_bytes(raw)
            entries.append(dict(file=filename,url=url,sha256=hashlib.sha256(raw).hexdigest()))
        (OUT/'reference_requests.json').write_text(json.dumps(dict(
            fetched_at_utc=datetime.now(timezone.utc).isoformat(),
            tolerance_seconds=TOLERANCE_SECONDS, requests=entries),indent=2),encoding='utf-8')
    metadata = json.loads((OUT/'reference_requests.json').read_text(encoding='utf-8'))
    rows = []
    for year, request in zip(YEARS, metadata['requests'], strict=True):
        raw = (OUT/request['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == request['sha256']
        events = lunar_phase_events(datetime(year,1,1,tzinfo=timezone.utc),datetime(year+1,1,1,tzinfo=timezone.utc))
        records = json.loads(raw)['phasedata']
        assert len(records) == len(events)
        for ref, event in zip(records, events, strict=True):
            assert event.phase is NAMES[ref['phase']]
            reference = datetime.fromisoformat(f"{ref['year']:04}-{ref['month']:02}-{ref['day']:02}T{ref['time']}+00:00")
            # USNO publishes Universal Time, not TT. Compare the common
            # modeled UT timeline to isolate series error from leap-second policy.
            model_ut = _tt_jd_to_utc(event.jde_tt)
            difference = (model_ut-reference).total_seconds()
            legacy_difference = None
            if event.phase in (PrincipalPhase.NEW_MOON, PrincipalPhase.FULL_MOON):
                n = round((event.jde_tt-2451550.09765)/29.530588853*2)/2
                legacy_difference = (event.at_utc-_lunar_phase_event_utc(n)).total_seconds()
            rows.append(dict(phase=event.phase.value,reference_ut=reference.isoformat(),
                calculated_ut=model_ut.isoformat(),calculated_utc=event.at_utc.isoformat(),
                jde_tt=event.jde_tt,time_basis=event.time_basis,
                difference_seconds=difference, new_minus_legacy_seconds=legacy_difference))
    summary = {p.value:dict(count=len(v:=[r for r in rows if r['phase']==p.value]),
        min_signed_seconds=min(r['difference_seconds'] for r in v),
        max_signed_seconds=max(r['difference_seconds'] for r in v),
        max_absolute_seconds=max(abs(r['difference_seconds']) for r in v)) for p in PrincipalPhase}
    report = dict(tolerance_seconds=TOLERANCE_SECONDS,count=len(rows),by_phase=summary,
        time_comparison='Meeus TT converted using project Delta T to modeled UT; USNO Universal Time minute precision. UTC leap conversion reported separately.',
        max_absolute_seconds=max(abs(r['difference_seconds']) for r in rows),
        max_new_legacy_seconds=max(abs(r['new_minus_legacy_seconds']) for r in rows if r['new_minus_legacy_seconds'] is not None),results=rows)
    (OUT/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    report_passed = report['max_absolute_seconds'] <= TOLERANCE_SECONDS
    if '--diagnostic' not in sys.argv:
        assert report_passed
    else:
        print('USNO diagnostic accepted: ' + str(report_passed) + '; JPL TT is the primary scientific gate')


if __name__ == '__main__':
    main()
