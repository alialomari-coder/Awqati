"""Prepare approved offline resources and a signed update artifact; never publish.

Private signing material must stay outside addon/ and version control.
"""
import argparse
from argparse import Namespace
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from build_timezones import build as build_timezones

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.infrastructure.world_clock import canonical, load_data, PREFIX


def prepare(source, reviewed, output, channel, private_key, generate=False):
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    source,reviewed,output,channel,key_path=map(Path,(source,reviewed,output,channel,private_key))
    if key_path.resolve().is_relative_to(ROOT/'addon'):
        raise ValueError('Never put the signing key in the add-on')
    report=json.loads((reviewed/'review.json').read_text('utf8'))
    if not report['approved'] or report['unresolvedEssential'] or report['civilCoverageGaps']:
        raise ValueError('World-clock data have not passed the review gates')
    if generate and not key_path.exists():
        key_path.parent.mkdir(parents=True,exist_ok=True)
        key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    else:key=serialization.load_pem_private_key(key_path.read_bytes(),password=None)
    output.mkdir(parents=True,exist_ok=True)
    shutil.copy2(reviewed/'catalog-candidate.json',output/'catalog.json')
    url='https://files.pythonhosted.org/packages/0a/66/9a06c2227fedfd4919f0eaaa8b94377d9730882a7e4f95823c9a331ab5e1/tzdata-2026.6-py2.py3-none-any.whl'
    build_timezones(Namespace(wheel=source/'tzdata-2026.6.whl',output=output/'timezones',source_url=url,generated_at='2026-11-03'))
    with zipfile.ZipFile(source/'cldr49-core.zip') as archive:
        root=ET.fromstring(archive.read('common/supplemental/windowsZones.xml'))
        unicode_license=archive.read('LICENSE')
    mapping={n.attrib['other']:n.attrib['type'].split()[0] for n in root.findall('.//mapZone') if n.attrib['territory']=='001'}
    (output/'timezones/windows_zones.json').write_bytes(canonical(mapping)+b'\n')
    public=key.public_key().public_numbers()
    (output/'update_key.json').write_bytes(canonical({'algorithm':'RSA-PKCS1-v1_5-SHA256','modulus':format(public.n,'x'),'exponent':public.e})+b'\n')
    licenses=output/'licenses';licenses.mkdir(exist_ok=True)
    shutil.copy2(source/'world-boundaries-LICENSE.txt',licenses/'ODbL-1.0.txt')
    shutil.copy2(ROOT/'addon/globalPlugins/awqati/data/locations/LICENSE-CC-BY-4.0.txt',licenses/'CC-BY-4.0.txt')
    (licenses/'Unicode.txt').write_bytes(unicode_license)
    notice='''Awqati World Clock data, build 2026-11-03.2.
City catalog is an adapted database distributed under ODbL 1.0.
Geographical records and current alternate names: GeoNames, CC BY 4.0,
https://www.geonames.org/ ; downloaded 2026-11-03, filtered and corrected.
Arabic/English geographical exemplars, countries and Windows zone mapping:
Unicode CLDR 49, Unicode License V3, https://cldr.unicode.org/ .
Additional Arabic labels: Wikidata, CC0, https://www.wikidata.org/ .
Kanton proper-name component attested in FAO AGROVOC concept c_1265:
https://agrovoc.fao.org/browse/agrovoc/en/page/c_1265 . Attribution: FAO.
Name component selected from a longer geographical term, not machine-transliterated.
FAO's current maintenance page declares CC BY 4.0 for its Arabic content:
https://www.fao.org/agrovoc/index.php/maintenance ; CC-BY-4.0 text is included.
Independent coordinate/timezone validation: timezone-boundary-builder 2026f,
ODbL 1.0, https://github.com/evansiroky/timezone-boundary-builder ;
copyright OpenStreetMap contributors, https://www.openstreetmap.org/copyright .
Changes include city selection, bilingual labels, geographical representatives,
verified timezone corrections, normalized search aliases and combined fields.
The full adapted catalog is provided as machine-readable catalog.json.
Timezone rules are a separate, unmodified data aggregate: Python tzdata 2026.6
(Apache-2.0) / IANA 2026f (public domain); license under timezones/LICENSE.txt.
No raw geographic boundary polygons, external executable code or private
signing key are distributed. Detailed provenance and correction ledger:
https://github.com/alialomari-coder/Awqati (tools/build_world_clock*.py,
data_sources/world_clock_reviews.v1.json, docs/world_clock_data_review.json).
'''
    (output/'NOTICE.txt').write_text(notice,'utf8',newline='\n')
    catalog=json.loads((output/'catalog.json').read_text('utf8'))
    metadata={'schemaVersion':1,'version':catalog['version'],'sourceVersions':{
        'IANA':'2026f','tzdata':'2026.6','CLDR':'49','GeoNames':'daily retrieved 2026-11-03','boundaries':'2026f'},
        'cityCount':len(catalog['cities']),'countryCount':len(report['countries']),'zoneCount':len(report['zones']),
        'files':{p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*')) if p.is_file() and p!=output/'metadata.json'}}
    (output/'metadata.json').write_bytes(canonical(metadata)+b'\n')
    load_data(output,full=True)
    channel.mkdir(parents=True,exist_ok=True)
    name='world-clock-'+catalog['version']+'.zip'
    archive_path=channel/name
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(output).as_posix(),date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,path.read_bytes())
    content=archive_path.read_bytes()
    manifest={'schemaVersion':1,'dataSchema':1,'version':catalog['version'],'url':PREFIX+name,
        'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'sources':metadata['sourceVersions']}
    manifest['signature']=key.sign(canonical(manifest),padding.PKCS1v15(),hashes.SHA256()).hex()
    (channel/'manifest.json').write_bytes(canonical(manifest)+b'\n')
    print(json.dumps({'cities':metadata['cityCount'],'countries':metadata['countryCount'],'zones':metadata['zoneCount'],
        'archive':str(archive_path),'archiveSha256':manifest['sha256'],'published':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','reviewed','output','channel','private-key'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--generate-key',action='store_true')
    a=parser.parse_args();prepare(a.source,a.reviewed,a.output,a.channel,a.private_key,a.generate_key)
