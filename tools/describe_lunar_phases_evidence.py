"""Recreate legacy/time-model diagnostics and local boundary evidence offline."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.domain.lunar_phases import _event, PrincipalPhase
from awqati.infrastructure import BundledTimezoneProvider
OUT=ROOT/'docs/lunar_phases_task24'


def main():
    old=json.loads((OUT/'legacy_before.json').read_text(encoding='utf-8'))
    rows=[]
    for key,stamp in old.items():
        k=float(key)
        phase=PrincipalPhase.FULL_MOON if k%1==.5 else PrincipalPhase.NEW_MOON
        event=_event(k,phase)
        rows.append(dict(k=k,phase=phase.value,legacy_utc=stamp,
            new_utc=event.at_utc.isoformat(),time_basis=event.time_basis,
            difference_seconds=(event.at_utc-datetime.fromisoformat(stamp)).total_seconds()))
    report=dict(count=len(rows),unchanged=sum(r['difference_seconds']==0 for r in rows),
        max_absolute_seconds=max(abs(r['difference_seconds']) for r in rows),
        largest=max(rows,key=lambda r:abs(r['difference_seconds'])),results=rows)
    (OUT/'legacy_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    usno=json.loads((OUT/'comparison.json').read_text(encoding='utf-8'))
    jpl=json.loads((OUT/'jpl_comparison.json').read_text(encoding='utf-8'))
    zones=BundledTimezoneProvider()
    near=[]
    inferred=[]
    for x in jpl['results']:
        for zid in ('Asia/Riyadh','America/New_York','Pacific/Kiritimati'):
            local=datetime.fromisoformat(x['utc']).astimezone(zones.get_timezone(zid))
            if local.hour in (0,23):
                near.append(dict(phase=x['phase'],zone=zid,local=local.isoformat(),utc=x['utc'],
                                 meeus_minus_jpl_seconds=x['meeus_minus_jpl_seconds']))
        if x['utc'].startswith('2099'):
            y=next(v for v in usno['results'] if abs(v['jde_tt']-x['meeus_jde_tt'])<1e-8)
            tt=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(days=x['jpl_jde_tt']-2440587.5)
            calc_tt=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(days=x['meeus_jde_tt']-2440587.5)
            inferred.append(dict(phase=x['phase'],usno_ut=y['reference_ut'],
                implied_tt_minus_usno_seconds=(tt-datetime.fromisoformat(y['reference_ut'])).total_seconds(),
                project_delta_t_seconds=(calc_tt-datetime.fromisoformat(y['calculated_ut'])).total_seconds(),
                usno_model_difference_seconds=y['difference_seconds'],
                meeus_minus_jpl_seconds=x['meeus_minus_jpl_seconds']))
    (OUT/'boundary_reference_cases.json').write_text(json.dumps(near,indent=2),encoding='utf-8')
    (OUT/'usno_time_model_diagnostic.json').write_text(json.dumps(dict(
        note='Inferred offset includes USNO minute rounding; not a claim about undocumented USNO internals.',
        results=inferred),indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
