"""Opt-in public HTTPS probe; uses temporary user data and real production updater.

This deliberately is not part of the offline unit-test suite.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.infrastructure.world_clock import load_data,WorldClockUpdater,CHANNEL,download,canonical,verify_signature,active_root
from awqati.application.world_clock import WorldClockService
from awqati.infrastructure.stopwatch import StopwatchRepository


def historical_fixture(target,source=None):
    """IANA 2026c already shipped by Awqati; never changes real installed data."""
    source=Path(source or ROOT/'addon/globalPlugins/awqati/data/world_clock');target=Path(target)
    shutil.copytree(source,target)
    old=ROOT/'addon/globalPlugins/awqati/data/timezones'
    for path in old.rglob('*'):
        if path.is_file():
            destination=target/'timezones'/path.relative_to(old);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination)
    meta=json.loads((target/'metadata.json').read_text('utf8'))
    meta['sourceVersions']['IANA']='2026c';meta['sourceVersions']['tzdata']='2026.3'
    meta['files']={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and p!=target/'metadata.json'}
    (target/'metadata.json').write_bytes(canonical(meta)+b'\n');load_data(target,full=True)
    return target


def probe():
    requests=[]
    def fetch(url,limit,cancelled):
        payload=download(url,limit,cancelled);requests.append({'url':url,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()});return payload
    with tempfile.TemporaryDirectory(prefix='awqati-world-live-') as temporary:
        root=Path(temporary);bundle=historical_fixture(root/'historical');user=root/'user'
        catalog,old_zones,_=load_data(bundle)
        repo=StopwatchRepository(root/'world_clock_cities.json');service=WorldClockService(catalog,repo)
        for name in ('Havana','Tokyo','Casablanca'):service.add(catalog.search(name)[0])
        city=service.rows[0];service.edit_names(city.city_id,'ar','هافانا الخاصة','كوبا الخاصة');service.edit_names(city.city_id,'en','My Havana','My Cuba')
        snapshot=repo.path.read_bytes();ids=[c.city_id for c in service.rows]
        stamp=datetime(2026,11,1,6,tzinfo=timezone.utc)
        before={key:int(stamp.astimezone(old_zones.get_timezone(key)).utcoffset().total_seconds()/60) for key in ('America/Havana','Asia/Tokyo','Africa/Casablanca')}
        updater=WorldClockUpdater(bundle,user,fetch)
        target=updater.check(catalog.version);assert target is not None
        new_catalog,new_zones,_=load_data(target,full=True)
        metadata=json.loads((target/'metadata.json').read_text('utf8'))
        pointer=updater.activate(target);assert active_root(bundle,user)==target
        restored=WorldClockService(new_catalog,repo)
        after={key:int(stamp.astimezone(new_zones.get_timezone(key)).utcoffset().total_seconds()/60) for key in before}
        assert before['America/Havana']==-300 and after['America/Havana']==-240
        assert after['Africa/Casablanca']==0
        assert before['Asia/Tokyo']==after['Asia/Tokyo']==540
        assert old_zones.get_timezone('America/Havana') is not new_zones.get_timezone('America/Havana')
        assert ids==[c.city_id for c in restored.rows] and snapshot==repo.path.read_bytes()
        assert restored.names(restored.rows[0],'ar')==('هافانا الخاصة','كوبا الخاصة')
        assert restored.names(restored.rows[0],'en')==('My Havana','My Cuba')
        before_no_change=len(requests);assert updater.check(new_catalog.version) is None
        assert len(requests)==before_no_change+1
        updater.rollback(pointer);assert active_root(bundle,user)==bundle
        # Offline use reads validated local resources, not the network.
        offline_catalog,offline_zones,_=load_data(active_root(bundle,user));assert offline_catalog.version==catalog.version
        assert offline_zones.get_timezone('Asia/Tokyo')
        manifest=json.loads(download(CHANNEL,65536))
        assert verify_signature(manifest,json.loads((bundle/'update_key.json').read_text('utf8')))
        return {'status':'passed','channel':CHANNEL,'publicHttpsWithoutAuthentication':True,'signatureVerifiedWithPreinstalledKey':True,
            'downloadAndActivation':True,'noUpdateOnlyFetchesManifest':True,'rollback':True,'offlineUse':True,
            'userSelectionOrderAndBothLanguagesPreserved':True,'historicalIana':'2026c','newIana':metadata['sourceVersions']['IANA'],
            'instant':stamp.isoformat(),'beforeOffsetsMinutes':before,'afterOffsetsMinutes':after,
            'newProviderAndZoneObjects':True,'requests':requests,'privateNvdaTouched':False,'liveNvdaButtonSpeechBrailleTested':False}


if __name__=='__main__':
    report=probe();output=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'docs/world_clock_update_live.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({key:value for key,value in report.items() if key!='requests'},ensure_ascii=True))
