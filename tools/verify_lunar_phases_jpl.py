"""Independent apparent-longitude roots in TT, no uncertain UT extrapolation."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.domain.lunar_phases import lunar_phase_events, PrincipalPhase
OUT = ROOT/'docs/lunar_phases_task24'
YEARS = (1901,1950,2000,2026,2050,2099)
TOLERANCE_SECONDS = 90  # acceptance_policy.json: fixed before JPL retrieval


def main():
    requests = []
    results = []
    for year in YEARS:
        events = lunar_phase_events(datetime(year,1,1,tzinfo=timezone.utc),datetime(year+1,1,1,tzinfo=timezone.utc))
        # Two complete cycles at each year end, fixed before successful retrieval.
        events = events[:8] + events[-8:]
        times = [e.jde_tt+s/86400 for e in events for s in (-300,0,300)]
        tables = []
        for body in ('301','10'):
            file = f'jpl_{year}_{body}.json'
            meta = OUT/(file+'.request.json')
            if '--fetch' in sys.argv:
                params = dict(format='json',COMMAND=f"'{body}'",CENTER="'500@399'",
                    EPHEM_TYPE="'OBSERVER'",QUANTITIES="'31'",TIME_TYPE="'TT'",
                    CAL_FORMAT="'JD'",TIME_DIGITS="'FRACSEC'",ANG_FORMAT="'DEG'",
                    APPARENT="'AIRLESS'",CSV_FORMAT="'YES'",EXTRA_PREC="'YES'",
                    TLIST="'"+'\n'.join(f'{t:.9f}' for t in times)+"'",TLIST_TYPE="'JD'")
                url = 'https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
                with urllib.request.urlopen(url,timeout=45) as response:
                    raw = response.read()
                if '$$SOE' not in json.loads(raw).get('result',''):
                    raise RuntimeError(raw.decode())
                (OUT/file).write_bytes(raw)
                meta.write_text(json.dumps(dict(url=url,parameters=params,
                    fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                    sha256=hashlib.sha256(raw).hexdigest()),indent=2),encoding='utf-8')
            raw = (OUT/file).read_bytes()
            metadata = json.loads(meta.read_text(encoding='utf-8'))
            assert hashlib.sha256(raw).hexdigest() == metadata['sha256']
            text = json.loads(raw)['result']
            assert 'Earth (399)' in text and 'Date_________JDTT' in text
            records = list(csv.reader(text.split('$$SOE')[1].split('$$EOE')[0].strip().splitlines()))
            assert len(records) == len(times)
            for t,row in zip(times,records,strict=True):
                assert abs(float(row[0])-t)<1e-8
            tables.append([float(r[3]) for r in records])
            requests.append(dict(file=file,sha256=metadata['sha256']))
        moon,sun = tables
        for i,event in enumerate(events):
            target = tuple(PrincipalPhase).index(event.phase)*90
            values = [((moon[3*i+j]-sun[3*i+j]-target+180)%360)-180 for j in range(3)]
            left,center,right = values
            assert left<0<right and left<center<right
            # Quadratic local interpolation, Newton root in seconds from Meeus.
            a = (left+right-2*center)/(2*300**2)
            b = (right-left)/600
            x = 0.
            for _ in range(5):
                x -= (a*x*x+b*x+center)/(2*a*x+b)
            assert abs(x)<300
            linear_x = -300+600*(-left)/(right-left)
            results.append(dict(phase=event.phase.value,utc=event.at_utc.isoformat(),
                meeus_jde_tt=event.jde_tt,jpl_jde_tt=event.jde_tt+x/86400,
                meeus_minus_jpl_seconds=-x,linear_vs_quadratic_seconds=linear_x-x))
    report = dict(tolerance_seconds=TOLERANCE_SECONDS,count=len(results),
        max_absolute_seconds=max(abs(r['meeus_minus_jpl_seconds']) for r in results),
        max_interpolation_check_seconds=max(abs(r['linear_vs_quadratic_seconds']) for r in results),
        by_phase={p.value:dict(count=len(v:=[r for r in results if r['phase']==p.value]),
            min_signed_seconds=min(r['meeus_minus_jpl_seconds'] for r in v),
            max_signed_seconds=max(r['meeus_minus_jpl_seconds'] for r in v),
            max_absolute_seconds=max(abs(r['meeus_minus_jpl_seconds']) for r in v)) for p in PrincipalPhase},
        requests=requests,results=results)
    (OUT/'jpl_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('requests','results')},indent=2))
    assert report['max_absolute_seconds']<=TOLERANCE_SECONDS
    assert report['max_interpolation_check_seconds']<.2


if __name__ == '__main__':
    main()
