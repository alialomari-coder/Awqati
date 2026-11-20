"""Prepare and optionally publish data-only commits to the independent GitHub branch.

Never uploads the private key or add-on package. No release, tag or main-branch push.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.build-deps'),str(ROOT/'addon/globalPlugins')]
from awqati.infrastructure.world_clock import canonical,load_data,verify_signature,PREFIX,version_parts


def prepare(source,output,private_key,version,tz_wheel=None,tz_source_url=None):
    from cryptography.hazmat.primitives import serialization,hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    source,output,private_key=map(Path,(source,output,private_key))
    version_parts(version)
    if private_key.resolve().is_relative_to(ROOT/'addon'):raise ValueError('Private key cannot be in addon')
    key=serialization.load_pem_private_key(private_key.read_bytes(),password=None)
    public=key.public_key().public_numbers();trusted=json.loads((source/'update_key.json').read_text('utf8'))
    if public.n!=int(trusted['modulus'],16) or public.e!=trusted['exponent']:raise ValueError('Signing key does not match the preinstalled trust anchor')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='world-publish-',dir=output) as temp:
        stage=Path(temp)/'data';shutil.copytree(source,stage)
        if tz_wheel:
            if not tz_source_url:raise ValueError('Document the official wheel source URL')
            from build_timezones import build
            from argparse import Namespace
            rules=build(Namespace(wheel=Path(tz_wheel),output=stage/'timezones',source_url=tz_source_url,generated_at=datetime.now(timezone.utc).date().isoformat()))
        catalog=json.loads((stage/'catalog.json').read_text('utf8'));catalog['version']=version
        (stage/'catalog.json').write_bytes(canonical(catalog)+b'\n')
        metadata=json.loads((stage/'metadata.json').read_text('utf8'));metadata['version']=version
        if tz_wheel:
            notice_path=stage/'NOTICE.txt';notice=notice_path.read_text('utf8')
            notice=notice.replace('Python tzdata '+metadata['sourceVersions']['tzdata'],'Python tzdata '+rules['tzDataVersion'])
            notice=notice.replace('IANA '+metadata['sourceVersions']['IANA'],'IANA '+rules['ianaVersion'])
            notice_path.write_text(notice,encoding='utf8',newline='\n')
            metadata['sourceVersions']['IANA']=rules['ianaVersion'];metadata['sourceVersions']['tzdata']=rules['tzDataVersion']
        metadata['files']={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file() and p!=stage/'metadata.json'}
        (stage/'metadata.json').write_bytes(canonical(metadata)+b'\n');load_data(stage,full=True)
        archive_name='world-clock-'+version+'.zip'
        with zipfile.ZipFile(output/archive_name,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    info=zipfile.ZipInfo(path.relative_to(stage).as_posix(),date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                    archive.writestr(info,path.read_bytes())
    payload=(output/archive_name).read_bytes()
    manifest={'schemaVersion':1,'dataSchema':1,'version':version,'catalogVersion':version,
        'ianaVersion':metadata['sourceVersions']['IANA'],'cldrVersion':metadata['sourceVersions']['CLDR'],
        'createdAt':datetime.now(timezone.utc).isoformat(),'minAwqatiVersion':'5.0.0-dev15',
        'url':PREFIX+archive_name+'?ref=world-clock-data','fileName':archive_name,'bytes':len(payload),
        'sha256':hashlib.sha256(payload).hexdigest(),'sources':metadata['sourceVersions'],
        'signatureAlgorithm':'RSA-PKCS1-v1_5-SHA256','keySha256':hashlib.sha256(canonical(trusted)).hexdigest()}
    manifest['signature']=key.sign(canonical(manifest),padding.PKCS1v15(),hashes.SHA256()).hex()
    assert verify_signature(manifest,trusted)
    (output/'manifest.json').write_bytes(canonical(manifest)+b'\n')
    (output/'README.md').write_text('# Awqati World Clock data channel\n\nData-only branch, independent of NVDA add-on releases.\nSigned manifest and immutable archives; never delete older archives.\nTrust anchor is installed with Awqati; private signing material is never published.\nIANA '+manifest['ianaVersion']+', CLDR '+manifest['cldrVersion']+'.\nSee licenses and NOTICE inside the archive.\nMaintenance: tools/publish_world_clock_channel.py in the Awqati source tree.\n',encoding='utf8',newline='\n')
    return manifest


def publish(output,manifest):
    """Git trees API creates one commit changing only three data-channel paths."""
    output=Path(output);repo='repos/alialomari-coder/Awqati';branch='world-clock-data'
    def api(path,body=None):
        args=['gh','api',repo+'/'+path]
        if body is None:return json.loads(subprocess.check_output(args))
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json',encoding='utf8',dir=output,delete=False) as stream:
            json.dump(body,stream);name=Path(stream.name)
        try:return json.loads(subprocess.check_output(args+['--method','POST','--input',str(name)]))
        finally:name.unlink(missing_ok=True)
    ref=subprocess.run(['gh','api',repo+'/git/ref/heads/'+branch],capture_output=True,text=True)
    if ref.returncode:
        if '404' not in ref.stderr:raise RuntimeError('Could not inspect channel ref: '+ref.stderr)
        current=api('git/ref/heads/master')['object']['sha'];exists=False
    else:
        current=json.loads(ref.stdout)['object']['sha'];exists=True
        previous=api('contents/world-clock/manifest.json?ref='+branch)
        old_manifest=json.loads(base64.b64decode(previous['content']))
        trusted=json.loads((ROOT/'addon/globalPlugins/awqati/data/world_clock/update_key.json').read_text('utf8'))
        if not verify_signature(old_manifest,trusted):raise ValueError('Existing channel signature cannot be verified')
        if version_parts(manifest['version'])<=version_parts(old_manifest['version']):
            raise ValueError('Publishing requires a strictly newer data version; old archives are immutable')
        archived=subprocess.run(['gh','api',repo+'/contents/world-clock/'+manifest['fileName']+'?ref='+branch],capture_output=True,text=True)
        if archived.returncode==0 or '404' not in archived.stderr:raise ValueError('Will not overwrite an existing or uninspectable archive')
    commit=api('git/commits/'+current);entries=[]
    for name in ('manifest.json',manifest['fileName'],'README.md'):
        data=(output/name).read_bytes()
        blob=api('git/blobs',{'content':base64.b64encode(data).decode('ascii'),'encoding':'base64'})
        entries.append({'path':'world-clock/'+name,'mode':'100644','type':'blob','sha':blob['sha']})
    tree=api('git/trees',{'base_tree':commit['tree']['sha'],'tree':entries})
    created=api('git/commits',{'message':'data: publish signed world-clock '+manifest['version'],'tree':tree['sha'],'parents':[current]})
    if exists:
        # Non-force update rejects a concurrent writer rather than losing a release.
        body={'sha':created['sha'],'force':False}
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json',encoding='utf8',dir=output,delete=False) as stream:json.dump(body,stream);name=Path(stream.name)
        try:subprocess.run(['gh','api',repo+'/git/refs/heads/'+branch,'--method','PATCH','--input',str(name)],check=True,stdout=subprocess.DEVNULL)
        finally:name.unlink(missing_ok=True)
    else:api('git/refs',{'ref':'refs/heads/'+branch,'sha':created['sha']})
    print(json.dumps({'dataCommit':created['sha'],'branch':branch,'publishedPaths':[e['path'] for e in entries],'officialAddonRelease':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default=str(ROOT/'addon/globalPlugins/awqati/data/world_clock'))
    parser.add_argument('--output',required=True);parser.add_argument('--private-key',required=True);parser.add_argument('--version',required=True)
    parser.add_argument('--tz-wheel');parser.add_argument('--tz-source-url')
    parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    manifest=prepare(args.source,args.output,args.private_key,args.version,getattr(args,'tz_wheel',None),getattr(args,'tz_source_url',None))
    print(json.dumps({'version':manifest['version'],'bytes':manifest['bytes'],'sha256':manifest['sha256'],'signatureVerified':True}))
    if args.publish:publish(args.output,manifest)
