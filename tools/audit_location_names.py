"""Audit bundled Arabic display-name coverage without exposing coordinates."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def audit(data_root: Path) -> dict:
 metadata = json.loads((data_root/'metadata.json').read_text(encoding='utf-8'))
 countries=[];examples=[];samples=[];sample_ids={'108410','110336','104515','360630','2643743','2988507','5128581','745044','524901','1850147','110250'}
 total=named=admin1=admin2=0
 for entry in metadata['countries']:
  raw=(data_root/entry['file']).read_bytes()
  if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Country checksum mismatch: '+entry['code'])
  records=json.loads(gzip.decompress(raw))['cities'];count=sum(bool(r['a']) for r in records)
  total+=len(records);named+=count
  admin1+=sum(bool(r.get('a1ar')) for r in records);admin2+=sum(bool(r.get('a2ar')) for r in records)
  countries.append({'countryCode':entry['code'],'total':len(records),'withArabicName':count,'withoutArabicName':len(records)-count})
  missing=sorted((r for r in records if not r['a']),key=lambda r:(-r['p'],r['i']))
  if missing and len(examples)<30:examples.append({'countryCode':entry['code'],'locationId':missing[0]['i'],'originalName':missing[0]['n']})
  samples.extend({'locationId':r['i'],'countryCode':entry['code'],'originalName':r['n'],'arabicName':r['a'][0] if r['a'] else None} for r in records if r['i'] in sample_ids)
 if total!=metadata['cityCount']:raise ValueError('Metadata count mismatch')
 return {'schemaVersion':1,'locationDataVersion':metadata['locationDataVersion'],'totalCities':total,'withArabicName':named,'coveragePercent':round(100*named/total,4),'withoutArabicName':total-named,'cityRecordsWithArabicAdmin1':admin1,'cityRecordsWithArabicAdmin2':admin2,'countryCount':len(countries),'countries':countries,'missingExamples':examples,'sampleNames':samples,'policy':metadata['arabicDisplayPolicy'],'scope':'Missing means absent from the validated bundled sources, not proof that no documented Arabic name exists elsewhere.'}


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--data-root',type=Path,default=ROOT/'addon/globalPlugins/awqati/data/locations')
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args();report=audit(args.data_root)
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('countries','missingExamples','sampleNames')},ensure_ascii=False))
