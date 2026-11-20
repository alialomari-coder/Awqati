"""Validated offline world-clock resources and recoverable signed data updates."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import urllib.request
from urllib.parse import urlparse
import zipfile
from ..domain.world_clock import WorldCity
from ..application.world_clock import WorldCatalog
from .timezone_provider import BundledTimezoneProvider, TimezoneDataError
from . import timezone_provider
from .world_zoneinfo._zoneinfo import ZoneInfo as ReferenceZoneInfo


PREFIX='https://api.github.com/repos/alialomari-coder/Awqati/contents/world-clock/'
CHANNEL=PREFIX+'manifest.json?ref=world-clock-data'
APP_VERSION='5.0.0-dev16'


class WorldDataError(ValueError):
    pass


class WorldDataIncompatible(WorldDataError):
    pass


def version_parts(value):
    import re
    if not isinstance(value,str) or not re.fullmatch(r'\d+(?:[.-]\d+)*(?:-dev\d+)?',value):
        raise WorldDataError('Invalid version')
    release,_,development=value.partition('-dev')
    return tuple(int(x) for x in release.replace('-','.').split('.'))+(int(development) if development else 1000000,)


class WorldTimezoneProvider(BundledTimezoneProvider):
    """Keep a damaged world-clock resource from disabling unrelated Awqati tools."""
    def get_timezone(self,key):
        try:
            if timezone_provider._ZoneInfo is not None:return super().get_timezone(key)
            key=self._validate_key(key)
            if key in self._cache:return self._cache[key]
            self._load_metadata()
            expected=self._zones.get(key)
            if expected is None:raise WorldDataError('Unknown world-clock timezone')
            path=self._data_root/'zoneinfo'/Path(*key.split('/'))
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected:raise WorldDataError('Timezone checksum mismatch')
            from io import BytesIO
            zone=ReferenceZoneInfo.from_file(BytesIO(data),key=key)
            self._cache[key]=zone
            return zone
        except TimezoneDataError as error:raise WorldDataError(str(error)) from error

    def timezone_ids(self):
        try:return super().timezone_ids()
        except TimezoneDataError as error:raise WorldDataError(str(error)) from error


def canonical(document):
    return json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


def load_data(root, full=False):
    root=Path(root)
    if (root/'catalog.json').stat().st_size>8*1024*1024:raise WorldDataError('Catalog too large')
    document=json.loads((root/'catalog.json').read_text('utf8'))
    if document.get('schemaVersion')!=1 or not isinstance(document.get('cities'),list) or not document.get('version'):
        raise WorldDataError('Unsupported world-clock catalog')
    zones=WorldTimezoneProvider(root/'timezones')
    ids=set(zones.timezone_ids());cities=[]
    for row in document['cities']:
        if row['zone'] not in ids or not row.get('zoneSource') or not row.get('nameSource'):
            raise WorldDataError('Unverified city or missing timezone')
        if not isinstance(row.get('aliases',[]),list) or not all(isinstance(n,str) for n in row.get('aliases',[])):
            raise WorldDataError('Invalid aliases')
        cities.append(WorldCity(str(row['id']),row['ar'],row['en'],row['countryAr'],row['countryEn'],row['zone'],
            tuple(row.get('aliases',[])),row.get('displayAdminAr',''),row.get('displayAdminEn',''),row.get('timeNoteAr',''),row.get('timeNoteEn','')))
    if not cities:raise WorldDataError('Empty catalog')
    catalog=WorldCatalog(cities,document['version'])
    metadata=json.loads((root/'metadata.json').read_text('utf8'))
    if metadata.get('schemaVersion')!=1 or metadata.get('version')!=document['version']:
        raise WorldDataError('Metadata version mismatch')
    hashes=metadata.get('files')
    if not isinstance(hashes,dict) or 'catalog.json' not in hashes:raise WorldDataError('Missing file manifest')
    # Root metadata is self-excluded; nested timezone metadata remains covered.
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'metadata.json'}
    if actual!=set(hashes):raise WorldDataError('Incomplete world-clock data files')
    for name,digest in hashes.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '\\' in name or ':' in name or any(part in ('..','.') for part in relative.parts):
            raise WorldDataError('Unsafe data path')
        if full or name=='catalog.json':
            if not hmac.compare_digest(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest):
                raise WorldDataError('World-clock resource checksum mismatch')
    if full:
        now=datetime.now(timezone.utc)
        for key in ids:
            zones.get_timezone(key).fromutc(now.replace(tzinfo=zones.get_timezone(key)))
    zones.catalog_ids=set(catalog.cities)
    return catalog,zones,document


def active_root(bundled, user):
    bundled,user=Path(bundled),Path(user)
    for pointer in ('active.json','previous.json'):
        try:
            version=json.loads((user/pointer).read_text('utf8'))['directory']
            if not isinstance(version,str) or '/' in version or '\\' in version or version in ('.','..'):
                raise WorldDataError('Unsafe active version')
            candidate=user/'versions'/version
            load_data(candidate,full=True)
            return candidate
        except (OSError,ValueError,KeyError,TypeError):pass
    return bundled


def atomic_write(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.world-clock-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)


def verify_signature(manifest, key):
    document=dict(manifest)
    try:
        signature=bytes.fromhex(document.pop('signature'))
        modulus=int(key['modulus'],16);exponent=int(key['exponent'])
        length=(modulus.bit_length()+7)//8
        if length<256 or len(signature)!=length or int.from_bytes(signature,'big')>=modulus:return False
        encoded=pow(int.from_bytes(signature,'big'),exponent,modulus).to_bytes(length,'big')
        digest_info=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(canonical(document)).digest()
        expected=b'\x00\x01'+b'\xff'*(length-len(digest_info)-3)+b'\x00'+digest_info
        return hmac.compare_digest(encoded,expected)
    except (KeyError,ValueError,TypeError,OverflowError):return False


def trusted_url(url):
    parsed=urlparse(url)
    return url.startswith(PREFIX) and parsed.scheme=='https' and parsed.hostname=='api.github.com' and not parsed.username and parsed.query in ('','ref=world-clock-data') and not parsed.fragment and '..' not in parsed.path.split('/') and '%' not in parsed.path


def download(url, limit, cancelled=lambda:False):
    if not trusted_url(url):raise WorldDataError('Untrusted update origin')
    if not urlparse(url).query:url+='?ref=world-clock-data'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Awqati-WorldClock/1','Accept':'application/vnd.github.raw+json'}),timeout=20) as response:
        if not trusted_url(response.geturl()):raise WorldDataError('Untrusted redirect')
        parts=[];size=0
        while True:
            if cancelled():raise InterruptedError('Update cancelled')
            part=response.read(min(65536,limit+1-size))
            if not part:break
            parts.append(part);size+=len(part)
            if size>limit:raise WorldDataError('Download exceeds limit')
        return b''.join(parts)


class WorldClockUpdater:
    def __init__(self,bundled,user,fetch=download):
        self.bundled,self.user,self.fetch=Path(bundled),Path(user),fetch
        self.key=json.loads((self.bundled/'update_key.json').read_text('utf8'))

    def check(self,current_version,cancelled=lambda:False):
        manifest=json.loads(self.fetch(CHANNEL,65536,cancelled).decode('utf8'))
        if not verify_signature(manifest,self.key):raise WorldDataError('Invalid update signature')
        if manifest.get('schemaVersion')!=1 or manifest.get('dataSchema')!=1:
            raise WorldDataIncompatible('Incompatible data schema')
        if version_parts(manifest.get('minAwqatiVersion','5.0.0-dev13'))>version_parts(APP_VERSION):
            raise WorldDataIncompatible('A newer Awqati build is required')
        version=manifest.get('version')
        if version_parts(version)<version_parts(current_version):raise WorldDataError('Downgrade rejected')
        if version_parts(version)==version_parts(current_version):return None
        if not trusted_url(manifest.get('url','')):raise WorldDataError('Untrusted archive')
        data=self.fetch(manifest['url'],8*1024*1024,cancelled)
        if len(data)!=manifest.get('bytes') or hashlib.sha256(data).hexdigest()!=manifest.get('sha256'):
            raise WorldDataError('Incomplete or corrupt update')
        try:return self.stage_archive(data,manifest,cancelled)
        except (OSError,zipfile.BadZipFile) as error:
            raise WorldDataError('The update could not be staged safely') from error

    def stage_archive(self,data,manifest,cancelled):
        from io import BytesIO
        version=manifest['version']
        self.user.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.world-stage-',dir=self.user) as temp:
            stage=Path(temp);seen=set();size=0
            with zipfile.ZipFile(BytesIO(data)) as archive:
                for info in archive.infolist():
                    name=info.filename;relative=PurePosixPath(name);size+=info.file_size
                    if (size>32*1024*1024 or name in seen or relative.is_absolute() or '\\' in name or ':' in name
                        or any(part in ('..','.') for part in relative.parts) or info.is_dir()
                        or (info.external_attr>>16)&0o170000==0o120000 or name.lower().endswith(('.py','.exe','.dll','.pyd','.pyc','.ps1','.bat','.cmd','.js','.vbs','.com','.scr','.msi'))):
                        raise WorldDataError('Unsafe update archive')
                    seen.add(name);path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(info))
            catalog,_,_=load_data(stage,full=True)
            if catalog.version!=version:raise WorldDataError('Archive version mismatch')
            if cancelled():raise InterruptedError('Update cancelled')
            directory=version+'-'+manifest['sha256'][:16]
            target=self.user/'versions'/directory;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                existing,_,_=load_data(target,full=True)
                if existing.version!=version or (target/'metadata.json').read_bytes()!=(stage/'metadata.json').read_bytes():
                    raise WorldDataError('Existing staged version does not match the signed update')
            else:os.replace(stage,target)
            return target

    def activate(self,target):
        target=Path(target)
        if target.parent.resolve()!=(self.user/'versions').resolve():raise WorldDataError('Invalid activation target')
        load_data(target,full=True)
        pointer=self.user/'active.json'
        old=pointer.read_bytes() if pointer.exists() else None
        if old is not None:atomic_write(self.user/'previous.json',old)
        atomic_write(pointer,canonical({'directory':target.name}))
        return old

    def rollback(self,old):
        if old is None:
            # Explicitly point at a validated previous bundled version, never delete user cities.
            atomic_write(self.user/'active.json',canonical({'directory':'bundled-fallback'}))
        else:atomic_write(self.user/'active.json',old)
