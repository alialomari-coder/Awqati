"""Compare independently downloaded Drive bytes with originals and G copies.

Input is an ephemeral connector-provided download reference list, never included
in evidence archives. The receipt contains public file URLs and checksums only.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/historical_converter_task6'
STAGING = ROOT / 'delivery-local/release7'
FOLDER = '1xYHh4gJ8kAdRXf875CYU2oa--7vAVCGY'


def verify(item):
	name = item['title']
	with urlopen(item['download_url'], timeout=60) as response:
		raw = response.read()
	original = (STAGING / name).read_bytes()
	destination = Path('G:/ملفاتي/إضافة أوقاتي') / name
	parents = item['metadata']['parent_ids']
	assert FOLDER in parents
	assert raw == original == destination.read_bytes(), name
	report = name == 'HISTORICAL_CONVERTER_TASK6_REPORT.md'
	if report:
		assert raw.decode('utf-8') == (ROOT / name).read_text('utf-8')
		assert '1336' in raw.decode('utf-8') and '2026.1' in raw.decode('utf-8')
	return dict(name=name, source=str(STAGING / name), destination=str(destination),
		size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), cloudId=item['id'], cloudUrl=item['url'],
		cloudParentVerified=True, copyMatched=True, exactCloudBytesMatch=True,
		reportCloudReadbackExact=True if report else None)


def main():
	refs = json.loads((ROOT / 'development_baseline/release7-cloud-downloads.json').read_text('utf-8'))
	with ThreadPoolExecutor(max_workers=4) as pool:
		rows = list(pool.map(verify, refs))
	expected = {p.name for p in STAGING.iterdir() if p.is_file()}
	assert expected == {x['name'] for x in rows}, (expected, {x['name'] for x in rows})
	receipt = dict(completed=True, cloudFolderId=FOLDER, files=rows,
		verifiedBy='G SHA-256 and authenticated independent cloud raw download; original/G/cloud byte-for-byte match',
		reportCloudReadbackExact=True, installedInPersonalNVDA=False, published=False, ownerAcceptancePending=True)
	(OUTPUT / 'delivery.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), 'utf-8')
	print('Verified', len(rows), 'cloud files; report readback exact')


if __name__ == '__main__':
	main()
