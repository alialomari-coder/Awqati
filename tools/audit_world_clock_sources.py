"""Audit official inputs and produce a REJECTED, non-runtime candidate catalog.

No network or automatic transliteration. Run --help for input paths.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
from io import TextIOWrapper
import json
import math
from pathlib import Path
import tarfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


def iana_coordinates(value):
    """Parse ISO 6709 coordinates used by IANA zone.tab."""
    split = next(i for i in range(1, len(value)) if value[i] in '+-')
    def component(text, degrees):
        digits = text[1:]
        result = int(digits[:degrees]) + int(digits[degrees:degrees+2])/60
        if len(digits) == degrees+4:
            result += int(digits[-2:])/3600
        elif len(digits) != degrees+2:
            raise ValueError('Invalid IANA coordinate')
        return -result if text[0] == '-' else result
    return component(value[:split], 2), component(value[split:], 3)


def distance_km(first, second):
    lat1, lon1, lat2, lon2 = map(math.radians, (*first, *second))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(a)))


def exemplar_conflicts(cities, zone_rows, canonical, wheel):
    """Flag only matching names AND nearby coordinates, never homonyms alone.

    This is a targeted consistency check, not a global timezone boundary map.
    """
    from datetime import datetime, timezone
    from io import BytesIO
    from zoneinfo import ZoneInfo
    instant = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    conflicts = []
    def key(name):
        return ''.join(c for c in normalized(name) if c.isalnum())
    indexed = defaultdict(list)
    for city in cities.values():
        for name in {key(city['en']), key(city['native'])}:
            indexed[(city['country'], name)].append(city)
    for row in zone_rows:
        expected = row[2]
        name = key(expected.split('/')[-1])
        point = iana_coordinates(row[1])
        for city in indexed[(row[0], name)]:
            distance = distance_km(point, (float(city['lat']), float(city['lon'])))
            if distance > 20 or canonical(city['zone']) == canonical(expected):
                continue
            def local(zone):
                return instant.astimezone(ZoneInfo.from_file(BytesIO(wheel.read('tzdata/zoneinfo/'+zone)), key=zone))
            actual, reference = local(city['zone']), local(expected)
            conflicts.append({'geonameId': city['id'], 'city': city['en'], 'country': city['country'],
                              'latitude': city['lat'], 'longitude': city['lon'], 'distanceFromIanaPointKm': round(distance, 3),
                              'geonamesZone': city['zone'], 'ianaExemplarZone': expected, 'ianaCoordinates': row[1],
                              'utcInstant': instant.isoformat(), 'geonamesLocal': actual.isoformat(),
                              'ianaLocal': reference.isoformat(),
                              'differenceMinutes': int((actual.utcoffset()-reference.utcoffset()).total_seconds()/60)})
    return conflicts


def normalized(value):
    value = unicodedata.normalize('NFKD', value).casefold()
    return ''.join(c for c in value if not unicodedata.combining(c)).replace('_', ' ').strip()


def build(source, output, include_exemplars=False):
    source, output = Path(source), Path(output)
    if output.resolve().is_relative_to(Path(__file__).resolve().parents[1]/'addon'):
        raise ValueError('Audit candidates must not be written into the add-on')
    reviews=json.loads((Path(__file__).resolve().parents[1]/'data_sources/world_clock_reviews.v1.json').read_text('utf8')) if include_exemplars else {}
    extras=reviews.get('geographicRepresentatives',{})
    inputs = {
        'cities': ('world-cities500.zip', 'https://download.geonames.org/export/dump/cities500.zip'),
        'names': ('world-alternateNamesV2.zip', 'https://download.geonames.org/export/dump/alternateNamesV2.zip'),
        'countries': ('world-countryInfo.txt', 'https://download.geonames.org/export/dump/countryInfo.txt'),
        'cldr': ('cldr49-core.zip', 'https://unicode.org/Public/cldr/49/core.zip'),
        'iana': ('tzdata2026f.tar.gz', 'https://data.iana.org/time-zones/releases/tzdata2026f.tar.gz'),
        'tzif': ('tzdata-2026.6.whl', 'https://files.pythonhosted.org/packages/0a/66/9a06c2227fedfd4919f0eaaa8b94377d9730882a7e4f95823c9a331ab5e1/tzdata-2026.6-py2.py3-none-any.whl'),
    }
    provenance = {key: {'file': name, 'url': url, 'sha256': hashlib.sha256((source/name).read_bytes()).hexdigest()}
                  for key, (name, url) in inputs.items()}
    if provenance['tzif']['sha256'] != '0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec':
        raise ValueError('tzdata does not match the published PyPI digest')
    with tarfile.open(source/inputs['iana'][0]) as archive:
        version = archive.extractfile('version').read().decode().strip()
        zone_rows = [line.split('\t') for line in archive.extractfile('zone.tab').read().decode().splitlines() if line and not line.startswith('#')]
    with zipfile.ZipFile(source/inputs['tzif'][0]) as archive:
        zi = archive.read('tzdata/zoneinfo/tzdata.zi').decode()
    links = {line.split()[2]: line.split()[1] for line in zi.splitlines() if line.startswith('L ')}
    def canonical(zone):
        seen = set()
        while zone in links:
            if zone in seen:
                raise ValueError('cyclic zone alias')
            seen.add(zone)
            zone = links[zone]
        return zone
    with zipfile.ZipFile(source/inputs['cldr'][0]) as archive:
        roots = {lang: ET.fromstring(archive.read('common/main/'+lang+'.xml')) for lang in ('ar', 'en')}
        countries = {lang: {n.attrib['type']: n.text for n in root.findall('./localeDisplayNames/territories/territory') if 'alt' not in n.attrib}
                     for lang, root in roots.items()}
        exemplars = {lang: {n.attrib['type']: n.findtext('exemplarCity') for n in root.findall('./dates/timeZoneNames/zone') if n.findtext('exemplarCity')}
                     for lang, root in roots.items()}
    all_countries = {}
    for row in csv.reader((source/inputs['countries'][0]).read_text('utf-8-sig').splitlines(), delimiter='\t'):
        if row and not row[0].startswith('#') and len(row) >= 19:
            all_countries[row[0]] = {'en': row[4], 'population': int(row[7] or 0)}
    cities, by_country, by_zone = {}, defaultdict(list), defaultdict(list)
    city_inputs = [(source/inputs['cities'][0], 'cities500.txt')]
    for path in sorted(source.glob('world-country-*.zip')):
        cc = path.stem.removeprefix('world-country-')
        city_inputs.append((path, cc+'.txt'))
        provenance['country-'+cc] = {'file': path.name, 'url': 'https://download.geonames.org/export/dump/'+cc+'.zip',
                                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for city_path, member in city_inputs:
      with zipfile.ZipFile(city_path) as archive:
        with TextIOWrapper(archive.open(member), encoding='utf-8') as stream:
            for row in csv.reader(stream, delimiter='\t'):
                if len(row) != 19 or (row[6] != 'P' and row[0] not in extras) or (not row[17] and row[0] not in extras):
                    continue
                if row[0] in cities or row[7] in ('PPLH', 'PPLQ', 'PPLW', 'PPLCH'):
                    continue
                city = {'id': row[0], 'en': row[2] or row[1], 'native': row[1], 'country': row[8],
                        'zone': canonical(row[17] or extras[row[0]]), 'lat': row[4], 'lon': row[5], 'population': int(row[14] or 0), 'feature': row[7], 'admin': row[10], 'ar': '', 'aliases': []}
                if row[0] in extras:
                    city['geographicRepresentative']=True
                    city['requiredExemplar']=extras[row[0]]
                cities[row[0]] = city
                by_country[row[8]].append(city)
                by_zone[city['zone']].append(city)
    selected = {c['id']: c for c in cities.values() if c['feature'] == 'PPLC' or c['population'] >= 500000}
    selected.update({i:c for i,c in cities.items() if i in extras})
    if include_exemplars:
        for row in zone_rows:
            target = normalized(row[2].split('/')[-1]).replace('-', '').replace("'", '')
            matches = [c for c in by_country[row[0]] if distance_km(iana_coordinates(row[1]),
                (float(c['lat']),float(c['lon']))) < 20 and target in {
                    normalized(c['en']).replace('-', '').replace("'", ''), normalized(c['native']).replace('-', '').replace("'", '')}]
            if matches:
                best = min(matches, key=lambda c: distance_km(iana_coordinates(row[1]), (float(c['lat']),float(c['lon']))))
                best['requiredExemplar'] = row[2]
                selected[best['id']] = best
    for group in (*by_country.values(), *by_zone.values()):
        best = max(group, key=lambda c: (c['feature'] == 'PPLC', c['population'], c['id']))
        selected[best['id']] = best
    # Prefer an exact GeoNames city-name match for CLDR exemplar spelling.
    for city in selected.values():
        zone = city['zone']
        english = exemplars['en'].get(zone, zone.split('/')[-1].replace('_', ' '))
        if normalized(english) in {normalized(city['en']), normalized(city['native'])} and zone in exemplars['ar']:
            city['ar'], city['nameSource'] = exemplars['ar'][zone], 'CLDR 49 exemplarCity'
    candidates = defaultdict(lambda: defaultdict(list))
    with zipfile.ZipFile(source/inputs['names'][0]) as archive:
        with TextIOWrapper(archive.open('alternateNamesV2.txt'), encoding='utf-8') as stream:
            for row in csv.reader(stream, delimiter='\t'):
                if len(row) < 8 or row[1] not in selected or row[2] not in ('ar', 'en'):
                    continue
                # Reject historic, colloquial and explicitly expired names.
                if row[6] == '1' or row[7] == '1' or (len(row) > 9 and row[9].strip()):
                    continue
                name = row[3].strip()
                if not name or len(name) > 160 or any(unicodedata.category(c).startswith('C') for c in name):
                    continue
                if row[2] == 'ar' and not any('\u0620' <= c <= '\u064a' for c in name):
                    continue
                candidates[row[1]][row[2]].append((0 if row[4] == '1' else 1, name))
    for city in selected.values():
        for lang in ('en', 'ar'):
            names = sorted(set(candidates[city['id']][lang]))
            city['aliases'].extend(name for _, name in names)
            if names and (lang == 'en' or not city['ar']):
                city[lang] = names[0][1]
                if lang == 'ar':
                    city['nameSource'] = 'GeoNames current alternate name' + (' (preferred)' if names[0][0] == 0 else '')
        city['countryEn'] = countries['en'].get(city['country'], all_countries.get(city['country'], {}).get('en', city['country']))
        city['countryAr'] = countries['ar'].get(city['country'], '')
        city['aliases'] = sorted(set(city['aliases'] + [city['native']]))
    missing = [dict(id=c['id'], en=c['en'], country=c['country'], zone=c['zone']) for c in selected.values() if not c['ar']]
    absent_countries = [{'code': cc, **info} for cc, info in all_countries.items() if cc not in by_country]
    absent_zones = [{'country': r[0], 'zone': r[2]} for r in zone_rows if canonical(r[2]) not in by_zone]
    records = sorted(selected.values(), key=lambda c: int(c['id']))
    payload = {'schemaVersion': 1, 'version': '2026-11-03.1', 'ianaVersion': version, 'cldrVersion': '49', 'cities': records}
    output.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8')
    (output/'rejected-candidate.json').write_bytes(content)
    with zipfile.ZipFile(source/inputs['tzif'][0]) as archive:
        conflicts = exemplar_conflicts(cities, zone_rows, canonical, archive)
    additional_names = defaultdict(set)
    supplemental_sources = []
    for path in sorted(source.glob('world-wikidata-*.json')):
        document = json.loads(path.read_text('utf-8'))
        supplemental_sources.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in document['results']['bindings']:
            additional_names[row['gn']['value']].add(row['label']['value'])
    report = {'date': '2026-11-03', 'inputCityCount': len(cities), 'cityCount': len(records),
              'countryCount': len({c['country'] for c in records}), 'zoneCount': len({c['zone'] for c in records}),
              'arabicNameCount': len(records)-len(missing), 'arabicPercent': round(100*(len(records)-len(missing))/len(records), 3),
              'missingArabic': missing, 'countriesWithoutCity': absent_countries, 'zonesWithoutCity': absent_zones,
              'candidateBytes': len(content), 'candidateSha256': hashlib.sha256(content).hexdigest(), 'sources': provenance,
              'ianaVersion': version, 'cldrVersion': '49', 'tzdataVersion': '2026.6',
              'selection': 'All PPLC capitals, cities with population >=500000, largest capital/population per country and per GeoNames timezone; no numerical cap.',
              'nameSources': dict((source, sum(c.get('nameSource','') == source for c in records)) for source in sorted({c.get('nameSource','') for c in records})),
              'geographicZoneConflicts': conflicts,
              'supplementalNames': {'source': 'https://query.wikidata.org/sparql', 'license': 'CC0-1.0',
                                    'files': supplemental_sources, 'uniqueIdsWithArabicLabels': len(additional_names),
                                    'missingArabicWithOneCandidate': sum(len(additional_names[c['id']]) == 1 for c in missing),
                                    'status': 'Retrieved by GeoNames ID; candidate labels not accepted or merged without review.'},
              'status': 'REJECTED_TIMEZONE_ASSOCIATIONS' if any(c['differenceMinutes'] for c in conflicts) else 'REQUIRES_FURTHER_REVIEW',
              'runtimeApproved': False}
    (output/'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--include-exemplars', action='store_true')
    args = parser.parse_args()
    report = build(args.source, args.output, args.include_exemplars)
    print(json.dumps({k: v for k, v in report.items() if k not in ('sources', 'missingArabic', 'supplementalNames')}, ensure_ascii=True, indent=2))
    raise SystemExit(2 if report['status'] == 'REJECTED_TIMEZONE_ASSOCIATIONS' else 0)
