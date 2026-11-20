"""Verify task 1.3 scope and exact preservation of shared NOAA outputs."""
from pathlib import Path
import ast
import hashlib
import json
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/sun_distance_task13'
sys.path.insert(0, str(ROOT / 'addon/globalPlugins'))
from awqati.domain import astronomy as current


def main():
    baseline = json.loads((OUTPUT / 'before_sha256.json').read_text())
    source_name = 'addon/globalPlugins/awqati/domain/astronomy.py'
    raw = (OUTPUT / 'approved_baseline.py.txt').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == baseline[source_name]
    old = types.ModuleType('task13_approved_baseline')
    sys.modules[old.__name__] = old
    exec(compile(raw, 'approved_baseline.py.txt', 'exec'), old.__dict__)
    comparisons = 0
    for i in range(2401):
        t = -1 + i / 1200
        for name in ('_sun_apparent_longitude', '_equation_of_time', '_sun_declination'):
            assert getattr(old, name)(t) == getattr(current, name)(t), (name, t)
            comparisons += 1
    old_nodes = {n.name: ast.dump(n) for n in ast.parse(raw).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    new_nodes = {n.name: ast.dump(n) for n in ast.parse((ROOT / source_name).read_bytes()).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    allowed = {'_sun_apparent_longitude', '_equation_of_time'}
    changed_nodes = {n for n in old_nodes if old_nodes[n] != new_nodes.get(n)}
    assert changed_nodes == allowed, changed_nodes
    (OUTPUT / 'shared_terms_preservation.json').write_text(json.dumps(dict(
        baseline_sha256=hashlib.sha256(raw).hexdigest(), exact_float_comparisons=comparisons,
        century_range=[-1, 1], existing_definitions_checked=len(old_nodes),
        existing_definitions_changed=sorted(changed_nodes), passed=True), indent=2))
    allowed_files = {source_name, 'addon/globalPlugins/awqati/domain/__init__.py',
        'addon/globalPlugins/awqati/application/astronomy_service.py', 'docs/data_sources.md'}
    changed = [n for n, digest in baseline.items() if not (ROOT/n).is_file()
        or hashlib.sha256((ROOT/n).read_bytes()).hexdigest() != digest]
    unexpected = sorted(set(changed) - allowed_files)
    assert not unexpected, unexpected
    (OUTPUT / 'preservation.json').write_text(json.dumps(dict(files_checked=len(baseline),
        allowed_modified=sorted(allowed_files), actually_modified=changed,
        unexpected_modified=unexpected, passed=True), indent=2))
    print(f'Preserved {len(old_nodes)-len(allowed)} existing astronomy definitions; '
          f'{comparisons} exactly equal float outputs; {len(baseline)} file hashes checked.')


if __name__ == '__main__':
    main()
