"""Verify final package scope, or only the explicitly requested Drive hashes."""
from concurrent.futures import ThreadPoolExecutor
import ast
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/weather_821'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def artifact():
    baseline = json.loads((ROOT/'development_baseline/weather821-before.json').read_text('utf-8-sig'))
    previous = ROOT/'dist/awqati-8.0.2.nvda-addon'
    package = ROOT/'dist/awqati-8.2.1.nvda-addon'
    assert sha(previous.read_bytes()) == baseline['dist/awqati-8.0.2.nvda-addon']
    with zipfile.ZipFile(previous) as old, zipfile.ZipFile(package) as new:
        assert new.testzip() is None
        assert set(old.namelist()) == set(new.namelist())
        changes = [p for p in new.namelist() if old.read(p) != new.read(p)]
        allowed = {'manifest.ini', 'doc/ar/readme.html', 'doc/en/readme.html',
                   'globalPlugins/awqati/application/weather_formatters.py'}
        generated_catalog = 'locale/ar/LC_MESSAGES/calendar_converter.mo'
        if generated_catalog in changes:
            import gettext
            import io
            catalogs = [gettext.GNUTranslations(io.BytesIO(z.read(generated_catalog)))._catalog for z in (old, new)]
            assert {k: v for k, v in catalogs[0].items() if k} == {k: v for k, v in catalogs[1].items() if k}
            allowed.add(generated_catalog)
        assert set(changes) == allowed, changes
        manifest = new.read('manifest.ini').decode('utf-8')
        assert 'version = 8.2.1' in manifest
        assert not any('__pycache__' in p or p.endswith(('.pyc', '.pyo')) for p in new.namelist())
        name = 'globalPlugins/awqati/application/weather_formatters.py'
        old_ast, new_ast = [ast.parse(z.read(name)) for z in (old, new)]
        def functions(tree):
            return {n.name: ast.dump(n) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        a, b = functions(old_ast), functions(new_ast)
        for method in ('current_parts', 'quantity', 'wind', 'percent', 'convert', 'number', 'time_label'):
            assert a[method] == b[method], method
        # Current parts, units, source data, settings and adapter are byte-for-byte
        # identical to 8.0.2; only report presentation and release titles differ.
        result = dict(path=str(package), bytes=package.stat().st_size, sha256=sha(package.read_bytes()),
            previousPackageUnchanged=True, previousSha256=sha(previous.read_bytes()),
            zipCrcPassed=True, packagedChangedFiles=changes, unchangedValueFormatting=True)
    (OUT/'artifact.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(result, ensure_ascii=False))


def cloud(mode):
    request = ROOT/'development_baseline/weather821-private-readback.json'
    rows = json.loads(request.read_text('utf-8'))
    baseline = json.loads((ROOT/'development_baseline/weather821-before.json').read_text('utf-8-sig'))
    def verify(row):
        parsed = urlparse(row['download_url'])
        assert parsed.scheme == 'https' and (parsed.hostname or '').endswith('.oaiusercontent.com')
        local = (ROOT/row['path']).resolve()
        assert local.is_relative_to(ROOT)
        with urlopen(row['download_url'], timeout=45) as response:
            digest = sha(response.read(max(local.stat().st_size * 2, 1024 * 1024) + 1))
        expected = baseline[row['path']] if mode == 'before' else sha(local.read_bytes())
        return dict(path=row['path'], id=row['id'], sha256=digest, expected=expected, matched=digest == expected)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(verify, rows))
    receipt = OUT/'sync.json'
    data = json.loads(receipt.read_text('utf-8')) if receipt.exists() else {}
    merged = {r['path']: r for r in data.get(mode, [])}
    merged.update({r['path']: r for r in results})
    data[mode] = list(merged.values())
    data['conflicts'] = [r['path'] for r in data.get('before', []) if not r['matched']]
    if mode == 'after':
        data['successful'] = all(r['matched'] for r in data[mode]) and not data['conflicts']
        data['verifiedCount'] = len(data[mode])
    receipt.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    request.unlink()
    print(json.dumps(dict(mode=mode, count=len(results), matched=sum(r['matched'] for r in results), conflicts=data['conflicts'])))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        artifact()
    else:
        cloud(sys.argv[1])
