"""Build a review candidate using CLDR, current GeoNames names and independent boundaries.

This command stages data only. An unresolved essential row prevents runtime activation.
"""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import tarfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from world_clock_boundaries import BoundaryIndex
from audit_world_clock_sources import distance_km


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).casefold() if c.isalnum())


def build(source, stage, output):
    source, stage, output = Path(source), Path(stage), Path(output)
    rows=json.loads((stage/'rejected-candidate.json').read_text('utf8'))['cities']
    boundary_path=source/'world-boundaries.zip'
    digest=hashlib.sha256(boundary_path.read_bytes()).hexdigest()
    if digest!='2d160501c844d382233f30b0cd0db2533fe17f93a118a3d38959fe73e3ac20c3':
        raise ValueError('Boundary asset digest differs from the official GitHub release digest')
    with zipfile.ZipFile(source/'tzdata-2026.6.whl') as archive:
        lines=archive.read('tzdata/zoneinfo/tzdata.zi').decode().splitlines()
    links={r.split()[2]:r.split()[1] for r in lines if r.startswith('L ')}
    def canonical(zone):
        while zone in links:zone=links[zone]
        return zone
    country_by_zone={}
    with tarfile.open(source/'tzdata2026f.tar.gz') as archive:
        for line in archive.extractfile('zone.tab').read().decode().splitlines():
            if line and not line.startswith('#'):
                cc,_,zone,*_=line.split('\t'); country_by_zone[zone]=cc
    cldr_names=defaultdict(set)
    with zipfile.ZipFile(source/'cldr49-core.zip') as archive:
        roots={lang:ET.fromstring(archive.read('common/main/'+lang+'.xml')) for lang in ('en','ar')}
    english={n.attrib['type']:n.findtext('exemplarCity') for n in roots['en'].findall('./dates/timeZoneNames/zone')}
    arabic_cldr={n.attrib['type']:n.findtext('exemplarCity') for n in roots['ar'].findall('./dates/timeZoneNames/zone')}
    for node in roots['ar'].findall('./dates/timeZoneNames/zone'):
        zone=node.attrib['type']; arabic=node.findtext('exemplarCity')
        if arabic and zone in country_by_zone:
            name=english.get(zone) or zone.split('/')[-1].replace('_',' ')
            cldr_names[country_by_zone[zone],norm(name)].add(arabic)
    wikidata=defaultdict(set)
    for path in sorted(source.glob('world-wikidata-*.json')):
        for row in json.loads(path.read_text('utf8'))['results']['bindings']:
            wikidata[row['gn']['value']].add((row['label']['value'],row['item']['value']))
    coverage_names=json.loads((source/'world-coverage-names.json').read_text('utf8'))['results']['bindings']
    polygons=BoundaryIndex(boundary_path)
    review_path=Path(__file__).resolve().parents[1]/'data_sources/world_clock_reviews.v1.json'
    reviews=json.loads(review_path.read_text('utf8'))
    corrections=[]; excluded=[]; accepted=[]; unresolved=[]
    for row in rows:
        if row['country']=='AQ' and row['id']!='9072762':
            excluded.append({'id':row['id'],'en':row['en'],'zone':row['zone'],
                'reason':'Antarctic research station rather than an independent civilian town. Preserve the civilian Villa Las Estrellas settlement only.'});continue
        if row['id'] in reviews['exclusions']:
            excluded.append({'id':row['id'],'en':row['en'],**reviews['exclusions'][row['id']]});continue
        if row['feature'] in ('PPLX','PPLH','PPLQ','PPLW','PPLCH') and row['feature']!='PPLC' and not row.get('requiredExemplar'):
            excluded.append({'id':row['id'],'en':row['en'],'reason':'City subdivision or non-current settlement; not a required exemplar.'});continue
        names=set()
        for name in [row['en'],row['native'],*row['aliases']]:
            names.update(cldr_names[row['country'],norm(name)])
        if len(names)==1:
            row['ar']=next(iter(names));row['nameSource']='CLDR 49 exemplarCity'
        elif not row['ar'] and len({name for name,_ in wikidata[row['id']]})==1:
            row['ar']=next(iter(wikidata[row['id']]))[0]
            row['nameSource']='Wikidata P1566 exact ID, Arabic label'
            row['nameReference']=sorted(url for _,url in wikidata[row['id']])
        if not row['ar']:
            for record in coverage_names:
                lon,lat=map(float,record['point']['value'].removeprefix('Point(').removesuffix(')').split())
                if norm(record['en']['value']) in {norm(row['en']),norm(row['native'])} and distance_km((lat,lon),(float(row['lat']),float(row['lon'])))<20:
                    row['ar']=record['label']['value'];row['nameSource']='Wikidata English name and coordinates independently matched'
                    row['nameReference']=[record['item']['value']];break
        if row['id'] in reviews['names']:
            record=reviews['names'][row['id']]
            row['ar']=record['ar'];row['nameSource']='Reviewed geographic name';row['nameReference']=[record['reference']]
            if record.get('en'):row['en']=record['en']
        if row['id'] in reviews['nameFromCldr']:
            zone=reviews['nameFromCldr'][row['id']]
            row['ar']=arabic_cldr[zone];row['nameSource']='CLDR 49 reviewed geographic exemplar'
            row['nameReference']=['https://github.com/unicode-org/cldr/blob/release-49/common/main/ar.xml']
        if not any('\u0620'<=c<='\u064a' for c in row['ar']):
            row['ar']=''
        validation=reviews.get('geographicValidationPoints',{}).get(row['id'])
        lat,lon=(validation['lat'],validation['lon']) if validation else (row['lat'],row['lon'])
        zones={canonical(z) for z in polygons.zones(lat,lon)}
        if validation:row['zoneValidationReference']=validation
        if len(zones)>1 and row['id'] in reviews['overlaps']:
            record=reviews['overlaps'][row['id']]
            if canonical(record['zone']) not in zones:raise ValueError('Reviewed overlap no longer matches independent polygons')
            zones={canonical(record['zone'])}
            row['timeNoteAr'],row['timeNoteEn']=record['noteAr'],record['noteEn']
        if len(zones)==1:
            new=next(iter(zones))
            if new!=canonical(row['zone']):
                corrections.append({'id':row['id'],'en':row['en'],'old':row['zone'],'new':new,
                    'source':'timezone-boundary-builder 2026f, OSM independent of GeoNames; coordinate point-in-polygon',
                    'lat':row['lat'],'lon':row['lon']})
            row['zone']=new;row['zoneSource']='timezone-boundary-builder 2026f'
        else:
            row['unresolvedZoneCandidates']=sorted(zones)
        essential=row['feature']=='PPLC' or bool(row.get('requiredExemplar'))
        if not row['ar'] or len(zones)!=1:
            issue={'id':row['id'],'en':row['en'],'country':row['country'],'zone':row['zone'],
                   'requiredExemplar':row.get('requiredExemplar'),'missingArabic':not row['ar'],
                   'boundaryMatches':sorted(zones),'reason':'Unresolved name or geographic zone'}
            if essential:unresolved.append(issue)
            else:excluded.append(issue)
            continue
        accepted.append(row)
    # Disambiguate same-name cities in the same country using source-attested
    # first-level administrative names in both languages.
    admin_names={r.split('\t')[0]:r.split('\t')[1] for r in (source/'world-admin1.txt').read_text('utf8').splitlines() if '\t' in r}
    with zipfile.ZipFile(source/'cldr49-core.zip') as archive:
        subdivisions={lang:{n.attrib['type']:n.text for n in ET.fromstring(archive.read('common/subdivisions/'+lang+'.xml')).findall('.//subdivision') if 'alt' not in n.attrib} for lang in ('ar','en')}
    duplicate_counts={lang:Counter((norm(c[lang]),c['country']) for c in accepted) for lang in ('ar','en')}
    for row in accepted:
        if any(duplicate_counts[lang][norm(row[lang]),row['country']]>1 for lang in ('ar','en')):
            admin=admin_names[row['country']+'.'+row['admin']]
            codes=[code for code,name in subdivisions['en'].items() if code.startswith(row['country'].lower()) and norm(name)==norm(admin)]
            if len(codes)!=1 or codes[0] not in subdivisions['ar']:raise ValueError('Unresolved bilingual administrative disambiguation')
            row['displayAdminEn']=subdivisions['en'][codes[0]];row['displayAdminAr']=subdivisions['ar'][codes[0]]
    output.mkdir(parents=True,exist_ok=True)
    payload={'schemaVersion':1,'version':'2026-11-03.2','ianaVersion':'2026f','tzdataVersion':'2026.6','cldrVersion':'49',
             'boundaryVersion':'2026f','license':'ODbL-1.0; attribution to GeoNames, Unicode, Wikidata, OSM contributors',
             'cities':sorted(accepted,key=lambda c:int(c['id']))}
    (output/'catalog-candidate.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n','utf8',newline='\n')
    represented={r['zone'] for r in accepted}
    missing=[{'zone':zone,'country':cc,'canonical':canonical(zone)} for zone,cc in country_by_zone.items() if canonical(zone) not in represented]
    gaps=[m for m in missing if m['zone'] not in reviews['uninhabitedZoneExclusions']]
    report={'acceptedCities':len(accepted),'countries':sorted({r['country'] for r in accepted}),
            'zones':sorted({r['zone'] for r in accepted}),'corrections':corrections,'excluded':excluded,'unresolvedEssential':unresolved,
            'boundarySha256':digest,'boundaryPolygons':polygons.polygon_count,'approved':not unresolved and not gaps,
            'unrepresentedIanaZones':missing,'civilCoverageGaps':gaps,
            'reviewSha256':hashlib.sha256(review_path.read_bytes()).hexdigest()}
    (output/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('countries','zones','excluded','corrections')},ensure_ascii=True,indent=2))
    print('countries',len(report['countries']),'zones',len(report['zones']),'corrections',len(corrections),'excluded',len(excluded))
    return 0 if not unresolved else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--stage',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();raise SystemExit(build(a.source,a.stage,a.output))
