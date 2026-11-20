"""Verify the final bundle differs from the owner-approved bundle only in help."""
from pathlib import Path
import hashlib
import json
import zipfile
import gettext
import io

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/release_7_1_0/closure'


def main():
    package = ROOT / 'dist/awqati-7.1.0.nvda-addon'
    approved = json.loads((OUT / 'approved_package_inventory.json').read_text('utf-8'))
    guides = {f'doc/{lang}/readme.{ext}' for lang in ('ar', 'en') for ext in ('md', 'html')}
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        current = {n: hashlib.sha256(archive.read(n)).hexdigest() for n in archive.namelist()}
        assert len(current) == len(archive.namelist())
        assert current.keys() == approved.keys()
        changed = sorted(n for n in current if current[n] != approved[n])
        translations = {f'locale/ar/LC_MESSAGES/{name}.mo' for name in ('nvda', 'calendar_converter')}
        assert set(changed) - guides <= translations, changed
        assert guides <= set(changed)
        for name in translations:
            reference = OUT / ('approved_' + Path(name).name)
            assert hashlib.sha256(reference.read_bytes()).hexdigest() == approved[name]
            old = gettext.GNUTranslations(io.BytesIO(reference.read_bytes()))._catalog.copy()
            new = gettext.GNUTranslations(io.BytesIO(archive.read(name)))._catalog.copy()
            old.pop('', None); new.pop('', None)
            assert old == new, name
        for name in guides:
            assert archive.read(name) == (ROOT / 'addon' / name).read_bytes()
        assert 'version = 7.1.0' in archive.read('manifest.ini').decode('utf-8-sig')
        assert 'name = awqati' in archive.read('manifest.ini').decode('utf-8-sig')
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    result = dict(successful=True, version='7.1.0', package=package.name,
                  sha256=digest, bytes=package.stat().st_size, entries=len(current),
                  changedEntries=changed, unchangedEntries=len(current)-len(changed),
                  productCodeAndDataUnchanged=True, translationMessagesUnchanged=True,
                  generatedTranslationHeadersMayDiffer=True, bilingualGuidesMatchSource=True)
    (OUT / 'artifact.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'awqati-7.1.0.nvda-addon.sha256').write_text(f'{digest}  {package.name}\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
