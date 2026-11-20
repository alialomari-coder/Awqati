"""Verify complete release bytes and protected baselines without rebuilding."""
from pathlib import Path
import gettext
import hashlib
import io
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.build-deps')]
import buildVars
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

OUT = ROOT / 'docs/weather_task3'
sha = lambda data: hashlib.sha256(data).hexdigest()

def main():
    package = ROOT / 'dist/awqati-8.0.0.nvda-addon'
    before = json.loads((OUT / 'source_before.json').read_text('utf-8'))
    allowed = {'addon/doc/ar/readme.md', 'addon/doc/ar/readme.html',
               'addon/doc/en/readme.md', 'addon/doc/en/readme.html'}
    changes = [name for name, digest in before.items()
               if not (ROOT / name).is_file() or sha((ROOT / name).read_bytes()) != digest]
    assert not set(changes) - allowed, changes
    assert sha((ROOT / 'dist/awqati-7.1.0.nvda-addon').read_bytes()) == '9684debf537389370652fe132419a6aa492451ab473ef66cfdc38357bc446e67'
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        inventory = {name: sha(z.read(name)) for name in z.namelist()}
        assert len(inventory) == len(z.namelist())
        source = {p.relative_to(ROOT / 'addon').as_posix(): p for p in (ROOT / 'addon').rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
        assert not set(source) - set(inventory)
        assert not set(inventory) - set(source) - {'manifest.ini', 'locale/ar/manifest.ini', 'COPYING.txt', 'DATA_SOURCES.md'}
        for name, path in source.items():
            if path.suffix == '.mo':
                with path.with_suffix('.po').open('rb') as stream:
                    catalog = read_po(stream, locale='ar')
                compiled = io.BytesIO(); write_mo(compiled, catalog)
                expected = gettext.GNUTranslations(io.BytesIO(compiled.getvalue()))._catalog.copy()
                actual = gettext.GNUTranslations(io.BytesIO(z.read(name)))._catalog.copy()
                expected.pop('', None); actual.pop('', None)
                assert expected == actual, name
            else:
                assert sha(path.read_bytes()) == inventory[name], name
        for name in ('COPYING.txt', 'DATA_SOURCES.md'):
            assert z.read(name) == (ROOT / name).read_bytes()
        assert z.read('manifest.ini').decode('utf-8') == (ROOT / 'manifest.ini.tpl').read_text('utf-8').format_map(buildVars.addon_info)
        translated = gettext.GNUTranslations(io.BytesIO(z.read('locale/ar/LC_MESSAGES/nvda.mo'))).gettext
        expected = (ROOT / 'manifest-translated.ini.tpl').read_text('utf-8').format_map(
            {k: translated(v) for k,v in buildVars.addon_info.items() if isinstance(v, str)})
        assert z.read('locale/ar/manifest.ini').decode('utf-8').replace('\r\n','\n') == expected
        modules = [name for name in inventory if name.endswith('.py')]
        for name in modules: compile(z.read(name), name, 'exec')
        assert not any('__pycache__' in name or 'scratchpad' in name or name.endswith(('.pyc','.pyo')) for name in inventory)
    result = dict(successful=True, version='8.0.0', addonId='awqati', path=str(package),
                  bytes=package.stat().st_size, sha256=sha(package.read_bytes()), zipFiles=len(inventory),
                  pythonModulesCompiled=len(modules), sourceResourcesMatched=True, compiledCatalogsMatched=True,
                  stable710AndBackupsUnchanged=True, baselineFiles=len(before), intentionalChanges=changes,
                  productCodeUnchangedSinceTask2=True, referenceAstronomyTestsRerun=False)
    (OUT / 'artifact.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    (OUT / 'package_inventory.json').write_text(json.dumps(inventory, indent=2), 'utf-8')
    print(json.dumps(result, ensure_ascii=True))

if __name__ == '__main__': main()
