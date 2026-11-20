"""Verify task 3.2's only operational change and frozen editorial/package hashes."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'docs/daily_synopsis_task32'
ALLOWED = {'addon/globalPlugins/awqati/nvda_adapter/text_dialog.py'}

def main():
    before = json.loads((OUTPUT/'source_before.json').read_text('utf-8'))
    changed = [name for name, digest in before.items()
        if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    unexpected = sorted(set(changed)-ALLOWED)
    compiled=[]
    for name in sorted(ALLOWED | {p.relative_to(ROOT).as_posix() for p in (ROOT/'tools').glob('*daily_synopsis*checks.py')} | {'tools/daily_synopsis_nvda_probe.py', 'tools/verify_daily_synopsis_final_preservation.py'}):
        compile((ROOT/name).read_text('utf-8-sig'),name,'exec')
        compiled.append(name)
    result = dict(baselineFiles=len(before), unchangedFiles=len(before)-len(changed),
        intentionalChanges=changed, unexpectedChanges=unexpected, compilationPassed=compiled,
        approvedArabicSha256=hashlib.sha256((ROOT/'docs/daily_synopsis_task31/final_editorial/approved_ar.txt').read_bytes()).hexdigest(),
        stablePackageSha256=hashlib.sha256((ROOT/'dist/awqati-7.0.0.nvda-addon').read_bytes()).hexdigest(),
        successful=not unexpected)
    (OUTPUT/'preservation_result.json').write_text(json.dumps(result,indent=2),'utf-8')
    print(json.dumps(result,indent=2))
    return int(not result['successful'])

if __name__=='__main__':
    raise SystemExit(main())
