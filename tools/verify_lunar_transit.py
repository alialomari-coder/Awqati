"""Task 2.2: independent full-civil-day JPL Horizons audit; never used at runtime.

Acquire a full-day minute grid, unrelated to calculated event times. H=0
isolates upper transit; a parabola through reference elevations independently
isolates altitude maxima. Check endpoint limits too, refine the near-zenith
case to two-second samples. Offline replay verifies raw response SHA-256.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import concurrent.futures
import csv
import hashlib
import io
import json
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addon/globalPlugins'))
from awqati.domain.lunar_transit import lunar_transit_day, _civil_intervals
from awqati.domain.astronomy import julian_day
from awqati.infrastructure import BundledTimezoneProvider

OUTPUT = ROOT/'docs/lunar_transit_task22'
# Set before acquiring references: compact Meeus + UT1 approximation, not DE441.
TIME_TOLERANCE_SECONDS = 30
ALTITUDE_TOLERANCE_DEGREES = .03
CASES = (
    ('dammam','2026-11-19',26.4207,50.0888,'Asia/Riyadh'),
    ('riyadh','2026-11-19',24.7136,46.6753,'Asia/Riyadh'),
    ('sydney','2026-06-21',-33.8688,151.2093,'Australia/Sydney'),
    ('london_spring','2026-03-29',51.5074,-.1278,'Europe/London'),
    ('london_autumn','2026-10-25',51.5074,-.1278,'Europe/London'),
    ('sydney_spring','2026-10-04',-33.8688,151.2093,'Australia/Sydney'),
    ('lord_howe','2026-04-05',-31.55,159.08,'Australia/Lord_Howe'),
    ('arctic_below','2026-06-01',78.2232,15.6469,'Arctic/Longyearbyen'),
    ('antarctic','2026-06-01',-78,15.6469,'UTC'),
    ('north_pole','2026-06-01',90,0,'UTC'),
    ('south_pole','2026-06-01',-90,0,'UTC'),
    ('repeated','1969-09-30',8.7167,167.7333,'Pacific/Kwajalein'),
    ('equator','2026-11-19',0,0,'UTC'),
    ('no_transit','2026-11-25',26.4207,50.0888,'Asia/Riyadh'),
)


def acquire(case):
    name, text, lat, lon, tzid = case
    if (OUTPUT/f'{name}_request.json').exists():
        saved=json.loads((OUTPUT/f'{name}_request.json').read_text())
        raw=(OUTPUT/f'{name}_horizons.txt').read_bytes()
        if saved['case']==list(case) and hashlib.sha256(raw).hexdigest()==saved['sha256']:
            return name+' (cached)'
    zone = BundledTimezoneProvider().get_timezone(tzid)
    intervals = _civil_intervals(date.fromisoformat(text), zone)
    assert len(intervals)==1
    start,end=intervals[0]
    params=dict(format='text',COMMAND="'301'",EPHEM_TYPE="'OBSERVER'",
        CENTER="'coord@399'",COORD_TYPE="'GEODETIC'",SITE_COORD=f"'{lon},{lat},0'",
        START_TIME=f"'{start:%Y-%m-%d %H:%M:%S}'",STOP_TIME=f"'{end:%Y-%m-%d %H:%M:%S}'",
        STEP_SIZE="'1 m'",QUANTITIES="'4,5,42,49'",CSV_FORMAT="'YES'",CAL_FORMAT="'JD'",
        TIME_DIGITS="'FRACSEC'",ANG_FORMAT="'DEG'",APPARENT="'AIRLESS'",EXTRA_PREC="'YES'",TIME_TYPE="'UT'")
    url='https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            raw=urllib.request.urlopen(url,timeout=45).read()
            break
        except OSError:
            if attempt==3: raise
            time.sleep(2*(attempt+1))
    if b'$$SOE' not in raw: raise ValueError(raw.decode()[:2000])
    (OUTPUT/f'{name}_horizons.txt').write_bytes(raw)
    record=dict(case=case,url=url,retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(raw).hexdigest())
    (OUTPUT/f'{name}_request.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    return name


def instant(jd):
    return datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(days=jd-2440587.5)


def refine_equatorial_reference(fetch=False):
    """Near-zenith curvature needs finer sampling than a minute parabola.

    Windows are selected from the independent full-day Horizons grid, then
    sampled every two seconds. No Awqati event time selects the request window.
    """
    case=next(c for c in CASES if c[0]=='equator')
    content=(OUTPUT/'equator_horizons.txt').read_text()
    rows=[r for r in csv.reader(io.StringIO(content.split('$$SOE')[1].split('$$EOE')[0])) if r and r[0].strip()]
    values=[tuple(float(r[i]) for i in (0,4,6,7)) for r in rows]
    peaks=[]
    for a,b,c in zip(values,values[1:],values[2:]):
        if b[1]>=a[1] and b[1]>c[1]:
            x=(a[1]-c[1])/(2*(a[1]+c[1]-2*b[1]))
            peaks.append(b[0]+x*(c[0]-b[0]))
    for a,b in zip(values,values[1:]):
        if a[3]<=0<b[3] and b[3]-a[3]<1:
            peaks.append(a[0]-a[3]/(b[3]-a[3])*(b[0]-a[0]))
    # This equatorial case has its transit within the same 40-second window.
    # One uniform grid avoids interleaving nearly coincident window grids.
    assert len(peaks)==2 and abs(peaks[0]-peaks[1])*86400<10
    times=[peaks[0]+s/86400 for s in range(-20,21,2)]
    original=json.loads((OUTPUT/'equator_request.json').read_text())
    params=dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(original['url']).query))
    for key in ('START_TIME','STOP_TIME','STEP_SIZE'): params.pop(key)
    params['TLIST']="'"+','.join(f'{jd:.9f}' for jd in times)+"'"
    url='https://ssd.jpl.nasa.gov/api/horizons.api?'+urllib.parse.urlencode(params)
    path=OUTPUT/'equator_fine_horizons.txt'
    if fetch:
        for attempt in range(4):
            try:
                raw=urllib.request.urlopen(url,timeout=45).read()
                break
            except OSError:
                if attempt==3: raise
                time.sleep(2*(attempt+1))
        assert b'$$SOE' in raw, raw[:1000]
        path.write_bytes(raw)
        (OUTPUT/'equator_fine_request.json').write_text(json.dumps(dict(url=url,
            sha256=hashlib.sha256(raw).hexdigest(),retrieved_at_utc=datetime.now(timezone.utc).isoformat()),indent=2))
    raw=path.read_bytes()
    record=json.loads((OUTPUT/'equator_fine_request.json').read_text())
    assert record['url']==url and hashlib.sha256(raw).hexdigest()==record['sha256']
    data=raw.decode().split('$$SOE')[1].split('$$EOE')[0]
    fine=[tuple(float(r[i]) for i in (0,4,6,7)) for r in csv.reader(io.StringIO(data)) if r and r[0].strip()]
    assert len(fine)==len(times)
    return fine


def compare():
    zones=BundledTimezoneProvider()
    results=[]
    for case in CASES:
        name,text,lat,lon,tzid=case
        request=json.loads((OUTPUT/f'{name}_request.json').read_text())
        assert request['case']==list(case)
        raw=(OUTPUT/f'{name}_horizons.txt').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==request['sha256']
        content=raw.decode()
        assert 'Atmos refraction: NO (AIRLESS)' in content
        rows=[r for r in csv.reader(io.StringIO(content.split('$$SOE')[1].split('$$EOE')[0])) if r and r[0].strip()]
        # JD, solar marker, event marker, AZ, EL, dAZ*cosEL, dEL, LHA, DUT1.
        values=[tuple(float(r[i]) for i in (0,4,6,7)) for r in rows]
        zone=zones.get_timezone(tzid)
        calculated=lunar_transit_day(date.fromisoformat(text),lat,lon,zone)
        start,end=calculated.civil_intervals_utc[0]
        assert abs((instant(values[0][0])-start).total_seconds())<.001
        assert abs((instant(values[-1][0])-end).total_seconds())<.001
        assert all(abs((b[0]-a[0])*86400-60)<.001 for a,b in zip(values,values[1:]))
        if name=='equator':
            # Retain day endpoints; use fine windows for interior event fitting.
            values=[values[0],*refine_equatorial_reference(),values[-1]]
        transits=[]
        maxima=[(start,values[0][1],'civilDayStart'),(end,values[-1][1],'civilDayEndLimit')]
        # Rates printed to .01 arcsec/min are too coarse near a pole. Isolate
        # maxima from full-day elevations (9 decimals), fit the local parabola;
        # never center the reference search on our predicted maximum/transit.
        for a,b,c in zip(values,values[1:],values[2:]):
            if abs((b[0]-a[0])-(c[0]-b[0]))*86400>.001: continue
            if b[1]>=a[1] and b[1]>c[1]:
                curvature=a[1]+c[1]-2*b[1]
                x=(a[1]-c[1])/(2*curvature)
                assert abs(x)<=1
                at=instant(b[0]+x*(c[0]-b[0]))
                el=b[1]+(c[1]-a[1])*x/2+curvature*x*x/2
                if start<at<end: maxima.append((at,el,'interiorMaximum'))
        for a,b in zip(values,values[1:]):
            if not (a[3]<=0<b[3] and b[3]-a[3]<1 and abs(lat)!=90): continue
            f=-a[3]/(b[3]-a[3])
            at=instant(a[0]+f*(b[0]-a[0]))
            # Integrate elevation with a locally linear derivative (arcsec/min).
            minutes=(b[0]-a[0])*1440
            el=a[1]+minutes*(a[2]*f+(b[2]-a[2])*f*f/2)/3600
            if start<=at<end: transits.append((at,el))
        best=max(p[1] for p in maxima)
        expected=[p for p in maxima if best-p[1]<=1e-9]
        row=dict(site=name,date=text,timezone=tzid,day_hours=(end-start).total_seconds()/3600,
                 transit_state=calculated.transit_state.value,transits=[],maxima=[],passed=True)
        for key,actual,reference in [('transits',calculated.transits,transits),('maxima',calculated.maxima,expected)]:
            row['passed'] &= len(actual)==len(reference)
            row[key+'_count_matches']=len(actual)==len(reference)
            for p,q in zip(actual,reference):
                seconds=(p.at_utc-q[0]).total_seconds()
                degrees=p.altitude_degrees-q[1]
                matched=abs(seconds)<=TIME_TOLERANCE_SECONDS and abs(degrees)<=ALTITUDE_TOLERANCE_DEGREES
                if key=='maxima': matched &= p.kind.value==q[2]
                row[key].append(dict(actual_local=p.at_utc.astimezone(zone).isoformat(),
                    reference_local=q[0].astimezone(zone).isoformat(),actual_altitude=p.altitude_degrees,
                    reference_altitude=q[1],signed_seconds=seconds,signed_degrees=degrees,passed=matched,
                    **({'kind':p.kind.value} if key=='maxima' else {})))
                row['passed'] &= matched
        row['center_below_horizon_all_day']=calculated.center_below_horizon_all_day
        results.append(row)
    all_events=[p for r in results for k in ('transits','maxima') for p in r[k]]
    summary=dict(reference='NASA JPL Horizons: lunar center, sea-level topocentric, AIRLESS, UTC modern / UT1 before 1962',
        time_tolerance_seconds=TIME_TOLERANCE_SECONDS,altitude_tolerance_degrees=ALTITUDE_TOLERANCE_DEGREES,
        cases=len(results),transits=sum(len(r['transits']) for r in results),maxima=sum(len(r['maxima']) for r in results),
        max_absolute_seconds=max(abs(p['signed_seconds']) for p in all_events),
        max_absolute_degrees=max(abs(p['signed_degrees']) for p in all_events),
        passed=all(r['passed'] for r in results),results=results)
    (OUTPUT/'comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    OUTPUT.mkdir(exist_ok=True)
    if '--fetch' in sys.argv:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            for name in executor.map(acquire,CASES): print('Saved',name,flush=True)
        refine_equatorial_reference(fetch=True)
    result=compare()
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
    for row in result['results']:
        if not row['passed']: print(json.dumps(row,indent=2))
    raise SystemExit(not result['passed'])
