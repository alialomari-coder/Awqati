"""Independent RSA signing and local network fixtures exercise safe update failures."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.build-deps'),str(ROOT/'addon/globalPlugins')]
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from awqati.infrastructure.world_clock import (WorldClockUpdater,WorldDataError,canonical,verify_signature,
    active_root,atomic_write,load_data,CHANNEL,PREFIX,trusted_url,download)

DATA=ROOT/'addon/globalPlugins/awqati/data/world_clock'


class WorldUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=cls.private.public_key().public_numbers()
        cls.public={'modulus':format(public.n,'x'),'exponent':public.e}
        cls.base={p.relative_to(DATA).as_posix():p.read_bytes() for p in DATA.rglob('*') if p.is_file()}
        cls.base['update_key.json']=canonical(cls.public)
        meta=json.loads(cls.base['metadata.json']);meta['files']['update_key.json']=hashlib.sha256(cls.base['update_key.json']).hexdigest()
        cls.base['metadata.json']=canonical(meta)
        cls.current=json.loads(cls.base['catalog.json'])['version']

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bundle=self.root/'bundle';self.user=self.root/'user'
        for name,data in self.base.items():
            path=self.bundle/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.requests=[]
        self.archive,self.manifest=self.release()
        self.updater=WorldClockUpdater(self.bundle,self.user,self.fetch)

    def sign(self,document):
        document=deepcopy(document);document.pop('signature',None)
        document['signature']=self.private.sign(canonical(document),padding.PKCS1v15(),hashes.SHA256()).hex()
        return document

    def release(self,version='2026-11-03.3',change=None):
        files=dict(self.base)
        catalog=json.loads(files['catalog.json']);catalog['version']=version;files['catalog.json']=canonical(catalog)
        metadata=json.loads(files['metadata.json']);metadata['version']=version
        metadata['files']['catalog.json']=hashlib.sha256(files['catalog.json']).hexdigest()
        files['metadata.json']=canonical(metadata)
        if change:change(files)
        stream=BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in files.items():archive.writestr(name,data)
        payload=stream.getvalue()
        manifest=self.sign({'schemaVersion':1,'dataSchema':1,'version':version,'url':PREFIX+'fixture.zip',
            'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
        return payload,manifest

    def fetch(self,url,limit,cancelled):
        self.requests.append(url)
        if cancelled():raise InterruptedError()
        data=canonical(self.manifest) if url==CHANNEL else self.archive
        self.assertLessEqual(len(data),limit)
        return data

    def test_constructor_never_connects_and_same_version_downloads_no_archive(self):
        self.assertFalse(self.requests)
        self.archive,self.manifest=self.release(self.current)
        self.assertIsNone(self.updater.check(self.current))
        self.assertEqual([CHANNEL],self.requests)

    def test_new_release_download_verification_activation_and_rollback(self):
        olddir=self.user/'versions/old';shutil.copytree(self.bundle,olddir)
        atomic_write(self.user/'active.json',canonical({'directory':'old'}))
        oldbytes=(self.user/'active.json').read_bytes()
        target=self.updater.check(self.current)
        self.assertEqual(olddir,active_root(self.bundle,self.user))
        old=self.updater.activate(target)
        self.assertEqual(target,active_root(self.bundle,self.user))
        self.assertEqual('2026-11-03.3',load_data(target)[0].version)
        self.updater.rollback(old)
        self.assertEqual(oldbytes,(self.user/'active.json').read_bytes())
        self.assertEqual(olddir,active_root(self.bundle,self.user))

    def test_signature_is_checked_by_independent_crypto_and_tampering_fails(self):
        self.assertTrue(verify_signature(self.manifest,self.public))
        document=dict(self.manifest);signature=bytes.fromhex(document.pop('signature'))
        self.private.public_key().verify(signature,canonical(document),padding.PKCS1v15(),hashes.SHA256())
        for key,value in (('version','2099-01-01.1'),('sha256','0'*64),('url','https://example.org/file')):
            changed=dict(self.manifest);changed[key]=value
            self.assertFalse(verify_signature(changed,self.public))
        self.manifest['signature']='0'*512
        with self.assertRaises(WorldDataError):self.updater.check(self.current)
        self.assertEqual([CHANNEL],self.requests)

    def test_truncated_and_corrupt_payloads_never_activate(self):
        for data in (self.archive[:-20],b'corrupt'):
            self.archive=data
            with self.assertRaises(WorldDataError):self.updater.check(self.current)
            self.assertFalse((self.user/'active.json').exists())
            self.assertEqual(self.bundle,active_root(self.bundle,self.user))

    def test_older_and_incompatible_releases_rejected(self):
        self.archive,self.manifest=self.release('2026-11-02.1')
        with self.assertRaises(WorldDataError):self.updater.check(self.current)
        self.archive,self.manifest=self.release()
        self.manifest=self.sign({**self.manifest,'dataSchema':99})
        with self.assertRaises(WorldDataError):self.updater.check(self.current)
        self.assertFalse((self.user/'active.json').exists())

    def test_invalid_signed_archive_and_wrong_catalog_version_rejected(self):
        for change in (lambda files:files.update({'catalog.json':b'{}'}),
                lambda files:files.pop('timezones/zoneinfo/Europe/London'),
                lambda files:files.update({'catalog.json':b'{broken'})):
            self.archive,self.manifest=self.release(change=change)
            with self.assertRaises((ValueError,OSError,KeyError)):self.updater.check(self.current)
            self.assertFalse((self.user/'active.json').exists())

    def test_path_traversal_and_downloaded_executable_rejected(self):
        for name in ('../escape.json','C:/escape.json','/escape.json','\\escape.json','evil.py','evil.exe'):
            self.archive,self.manifest=self.release(change=lambda files:files.update({name:b'bad'}))
            with self.assertRaises(WorldDataError):self.updater.check(self.current)
        self.assertFalse((self.root/'escape.json').exists())

    def test_network_failure_and_cancellation_preserve_existing_data(self):
        self.updater.fetch=lambda *a:(_ for _ in ()).throw(OSError('offline'))
        with self.assertRaises(OSError):self.updater.check(self.current)
        self.updater.fetch=self.fetch
        with self.assertRaises(InterruptedError):self.updater.check(self.current,lambda:True)
        self.assertFalse((self.user/'active.json').exists())

    def test_write_failure_keeps_previous_pointer_and_user_city_file(self):
        olddir=self.user/'versions/old';shutil.copytree(self.bundle,olddir)
        atomic_write(self.user/'active.json',canonical({'directory':'old'}))
        city_file=self.root/'world_clock_cities.json';city_file.write_bytes(b'{"selected":["2643743"]}')
        original=(self.user/'active.json').read_bytes();selected=city_file.read_bytes()
        target=self.updater.check(self.current)
        with patch('awqati.infrastructure.world_clock.atomic_write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.updater.activate(target)
        self.assertEqual(original,(self.user/'active.json').read_bytes());self.assertEqual(selected,city_file.read_bytes())

    def test_invalid_active_data_falls_back_to_previous_then_bundle(self):
        olddir=self.user/'versions/old';shutil.copytree(self.bundle,olddir)
        atomic_write(self.user/'previous.json',canonical({'directory':'old'}))
        atomic_write(self.user/'active.json',canonical({'directory':'missing'}))
        self.assertEqual(olddir,active_root(self.bundle,self.user))
        (self.user/'previous.json').write_bytes(b'bad')
        self.assertEqual(self.bundle,active_root(self.bundle,self.user))

    def test_source_identity_and_malformed_manifest(self):
        for url in ('http://raw.githubusercontent.com/x','https://example.org/file',PREFIX+'../escape.zip',PREFIX+'file.zip?x=1'):
            self.assertFalse(trusted_url(url))
        self.assertTrue(trusted_url(CHANNEL))
        for manifest in ({}, {'signature':'bad'}, {'signature':None}):self.assertFalse(verify_signature(manifest,self.public))


if __name__=='__main__':unittest.main()
