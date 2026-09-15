"""Audit all eligible Arab locations and every Saudi record from built data."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.infrastructure import BundledLocationRepository
from awqati.nvda_adapter.location_labels import ARAB_COUNTRIES, city_name, normalized_name, subdivisions, _arabic_name


def audit(data_root, output):
    metadata = json.loads((data_root / "metadata.json").read_text(encoding="utf-8"))
    repo = BundledLocationRepository(data_root)
    countries = []
    sa_records = []
    supplement = json.loads((ROOT / "data_sources/sa_locations_supplement.v1.json").read_text(encoding="utf-8"))
    reviewed = {row["geonameId"]: row for section in ("aliases", "additions") for row in supplement[section]}
    for country in repo.countries():
        if country.code not in ARAB_COUNTRIES:
            continue
        records = repo.browse(country.code, country.city_count)
        named = [m for m in records if _arabic_name(m.arabic_names)]
        missing = sorted((m for m in records if not _arabic_name(m.arabic_names)), key=lambda m:(-m.population,m.location.location_id))
        countries.append({"countryCode":country.code,"total":len(records),"withArabicName":len(named),
                          "coveragePercent":round(100*len(named)/len(records),4),"withoutArabicName":len(missing),
                          "missingExamples":[{"locationId":m.location.location_id,"name":m.location.name} for m in missing[:10]],
                          "arabicAdmin1Count":sum(bool(_arabic_name(m.arabic_admin1_names)) for m in records),
                          "arabicAdmin2Count":sum(bool(_arabic_name(m.arabic_admin2_names)) for m in records)})
        if country.code == "SA":
            for m in sorted(records,key=lambda m:int(m.location.location_id)):
                ref = reviewed.get(m.location.location_id)
                sa_records.append({"locationId":m.location.location_id,"originalName":m.location.name,
                                   "arabicName":_arabic_name(m.arabic_names),"admin1":m.admin1_name,"admin2":m.admin2_name,
                                   "displayAdmins":subdivisions(m,"ar"),"featureCode":m.feature_code,
                                   "nameStatus":"reviewed-current-source" if ref else ("current-source-name-not-independent-official-certification" if _arabic_name(m.arabic_names) else "unresolved-original-fallback"),
                                   "sourceRefs":ref["sourceRefs"] if ref else ["GeoNames alternateNamesV2 current snapshot; Wikidata if present"],
                                   "aliases":list(m.arabic_names)})
    ncar = json.loads((ROOT / "data_sources/sa_ncar_governorates.v1.json").read_text(encoding="utf-8"))
    names = {}
    for row in sa_records:
        for name in row["aliases"]:
            names.setdefault(normalized_name(name),[]).append(row["locationId"])
    comparison=[]
    for g in ncar["governorates"]:
        name = re.sub(r"^(مدينة|محافظة)\s+", "", g["name"]).strip()
        ids = names.get(normalized_name(name), [])
        comparison.append({**g,"matchedLocationIds":ids,"status":"name-match-review-region" if ids else "unresolved-name-or-seat-mapping-not-proof-of-absence"})
    report={"schemaVersion":1,"locationDataVersion":metadata["locationDataVersion"],
            "eligibility":"All populated-place records in the approved cities500 base plus reviewed Saudi governorate seats. Includes named populated localities and existing districts; not all administrative polygons or every village.",
            "countries":countries,"saudiRecords":sa_records,"saudiGovernorateComparison":comparison,
            "saudiReviewLimit":"Current non-historic source labels are audited individually for presence and script; they are not asserted to have independent official name certification. Unresolved source/admin anomalies remain documented, not guessed.",
            "knownSaudiSourceAnomalies":[{"locationId":"9031043","issue":"No reliable Arabic name located; original fallback retained."}],
            "sources":metadata.get("arabicSupplements",{})}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for c in countries:
        print(c["countryCode"],c["withArabicName"],"/",c["total"],str(c["coveragePercent"])+"%")
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",type=Path,default=ROOT / "addon/globalPlugins/awqati/data/locations")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    audit(args.data_root,args.output)
