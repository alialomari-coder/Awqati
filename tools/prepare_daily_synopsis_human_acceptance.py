"""Prepare immutable source fixtures for the owner's task 3.2 acceptance.

No installer, release build, personal configuration, or NVDA process changes.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'development_baseline/daily-synopsis-human32'
EVIDENCE=ROOT/'docs/daily_synopsis_task32/human_acceptance'
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if TARGET.exists():raise RuntimeError('Prepared environment already exists; refusing to overwrite it')
    accepted=json.loads((ROOT/'docs/daily_synopsis_task32/source_before.json').read_text('utf-8'))
    accepted['addon/globalPlugins/awqati/nvda_adapter/text_dialog.py']=next(
        e['sha256'] for e in json.loads((ROOT/'docs/daily_synopsis_task32/delivery_manifest.json').read_text('utf-8-sig'))['files']
        if e['path']=='addon/globalPlugins/awqati/nvda_adapter/text_dialog.py')
    actual={p.relative_to(ROOT).as_posix() for p in (ROOT/'addon').rglob('*')
        if p.is_file() and '__pycache__' not in p.parts}
    if actual!={name for name in accepted if name.startswith('addon/')}:
        raise RuntimeError('Addon inventory differs from the accepted source')
    for name,expected in accepted.items():
        if name.startswith('addon/') and digest(ROOT/name)!=expected:
            raise RuntimeError('Source differs from task 3.2 accepted baseline: '+name)
    if digest(ROOT/'dist/awqati-7.0.0.nvda-addon')!='0f474ea7236a5fd34f1887509e62f5b55c2410269822f3c2c8cf2062c0f9710a':
        raise RuntimeError('Stable package fingerprint mismatch')
    TARGET.mkdir(parents=True)
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    template=TARGET/'addon'
    shutil.copytree(ROOT/'addon',template,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    with zipfile.ZipFile(ROOT/'dist/awqati-7.0.0.nvda-addon') as z:
        (template/'manifest.ini').write_bytes(z.read('manifest.ini'))
    shutil.copyfile(ROOT/'tools/daily_synopsis_human_host.py',TARGET/'human_host.py')
    # Only the existing runtime is reused. No portable installer is run.
    runtime=ROOT/'development_baseline/nvda-2026.1-portable'
    files={p.relative_to(TARGET).as_posix():digest(p) for p in TARGET.rglob('*') if p.is_file()}
    runtime_files={p.relative_to(runtime).as_posix():digest(p) for p in runtime.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    manifest=dict(task='3.2 human acceptance preparation',nvda='2026.1',
        runtime=str(runtime),runtimeFiles=runtime_files,files=files,sourceMatchesAccepted=True,
        stablePackageSha256=digest(ROOT/'dist/awqati-7.0.0.nvda-addon'),humanAcceptance=None)
    (TARGET/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    (EVIDENCE/'prepared_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(prepared=str(TARGET),sourceFiles=len(files),runtimeFiles=len(runtime_files),startedNVDA=False),indent=2))

if __name__=='__main__':main()
