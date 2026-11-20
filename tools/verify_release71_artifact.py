"""Final bundle identity, complete source coverage and frozen baseline checks."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile
import gettext
import io

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs/release_7_1_0'
sys.path.insert(0,str(ROOT))
import buildVars


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    package=ROOT/'dist/awqati-7.1.0.nvda-addon'
    before=json.loads((OUTPUT/'source_before.json').read_text('utf-8'))
    allowed={'addon/doc/ar/readme.md','addon/doc/ar/readme.html','addon/doc/en/readme.md','addon/doc/en/readme.html',
        'buildVars.py','tests/test_release_package.py','tests/test_final_help.py','tests/test_architecture.py',
        'tests/test_lunar_horizon.py','tests/test_lunar_transit.py','tests/test_time_tools_embedding.py'}
    removed=[name for name in before if not (ROOT/name).exists()]
    authorized_removals={'dist/awqati-6.0.0.nvda-addon','dist/awqati-7.0.0.nvda-addon'}
    cleanup=json.loads((OUTPUT/'closure/cleanup.json').read_text('utf-8-sig'))
    deleted={item['path']:item['sha256'] for row in cleanup['removedPaths'] for item in row['inventory']}
    for name in set(removed) & authorized_removals:
        assert deleted[name]==before[name], name
    changes=[name for name,expected in before.items() if name not in removed and sha((ROOT/name).read_bytes())!=expected]
    unexpected=sorted((set(changes)-allowed) | (set(removed)-authorized_removals))
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        inventory={name:sha(archive.read(name)) for name in archive.namelist()}
        assert len(inventory)==len(archive.namelist())
        source={p.relative_to(ROOT/'addon').as_posix():p for p in (ROOT/'addon').rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
        missing=sorted(set(source)-set(inventory))
        extras=sorted(set(inventory)-set(source)-{'manifest.ini','COPYING.txt','DATA_SOURCES.md','locale/ar/manifest.ini'})
        generated={'locale/ar/LC_MESSAGES/nvda.mo','locale/ar/LC_MESSAGES/calendar_converter.mo'}
        mismatches=[name for name,path in source.items() if name not in generated and name in inventory and sha(path.read_bytes())!=inventory[name]]
        # The established builder compiles both MO domains from PO, replacing
        # stale source binaries. Compare the complete compiled catalogs, while
        # allowing Babel's generated header dates to vary.
        sys.path.insert(0,str(ROOT/'.build-deps'))
        from babel.messages.pofile import read_po
        from babel.messages.mofile import write_mo
        catalogs={}
        for name in sorted(generated):
            with source[name].with_suffix('.po').open('rb') as stream:
                catalog=read_po(stream,locale='ar')
            compiled_mo=io.BytesIO();write_mo(compiled_mo,catalog)
            expected=gettext.GNUTranslations(io.BytesIO(compiled_mo.getvalue()))._catalog.copy()
            actual=gettext.GNUTranslations(io.BytesIO(archive.read(name)))._catalog.copy()
            expected.pop('',None);actual.pop('',None)
            assert expected==actual,name
            catalogs[name]=len(actual)
        compiled=0
        for name in inventory:
            if name.endswith('.py'):
                compile(archive.read(name),name,'exec');compiled+=1
        manifest=archive.read('manifest.ini').decode('utf-8-sig')
        assert 'version = 7.1.0' in manifest and 'name = awqati' in manifest
        info=buildVars.addon_info
        assert manifest==(ROOT/'manifest.ini.tpl').read_text('utf-8').format_map(info)
        translate=gettext.GNUTranslations(io.BytesIO(archive.read('locale/ar/LC_MESSAGES/nvda.mo'))).gettext
        localized=(ROOT/'manifest-translated.ini.tpl').read_text('utf-8').format_map({key:translate(value) for key,value in info.items() if isinstance(value,str)})
        assert archive.read('locale/ar/manifest.ini').decode('utf-8').replace('\r\n','\n')==localized
        assert 'scratchpad' not in '\n'.join(inventory)
    result=dict(version='7.1.0',addonId=buildVars.addon_info['addon_name'],path=str(package),bytes=package.stat().st_size,
        sha256=sha(package.read_bytes()),zipFiles=len(inventory),pythonModulesCompiled=compiled,
        missingSourceFiles=missing,extraFiles=extras,sourceMismatches=mismatches,
        compiledTranslationMessages=catalogs,localizedManifestVerified=True,
        baselineFiles=len(before),intentionalChanges=changes,intentionalDeletions=removed,unexpectedChanges=unexpected,
        approvedArabicSha256=sha((ROOT/'docs/daily_synopsis_task31/final_editorial/approved_ar.txt').read_bytes()),
        stablePackageSha256='0f474ea7236a5fd34f1887509e62f5b55c2410269822f3c2c8cf2062c0f9710a',
        stablePackageRetained=False,
        successful=not (missing or extras or mismatches or unexpected))
    (OUTPUT/'artifact.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    (OUTPUT/'package_inventory.json').write_text(json.dumps(inventory,indent=2),'utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(not result['successful'])


if __name__=='__main__':raise SystemExit(main())
