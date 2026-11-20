"""Readable task-1 smoke checks, with a JSON record of actual results."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.domain.historical_calendars import (  # noqa: E402
	HistoricalCalendar as C, HistoricalCalendarError, MAX_RD,
	convert, from_rd,
)


def main() -> None:
	sys.stdout.reconfigure(encoding="utf-8")
	records = []
	for source, target, ymd, expected in (
		(C.HIJRI_IIC, C.GREGORIAN, (1, 1, 1), (622, 7, 19)),
		(C.HIJRI_IIC, C.GREGORIAN, (365, 9, 12), (976, 5, 19)),
		(C.HIJRI_IIC, C.JULIAN, (365, 9, 12), (976, 5, 14)),
		(C.JULIAN, C.HIJRI_IIC, (1258, 2, 10), (656, 2, 4)),
		(C.HIJRI_IIC, C.GREGORIAN, (656, 2, 4), (1258, 2, 17)),
		(C.JULIAN, C.GREGORIAN, (1700, 2, 29), (1700, 3, 11)),
		(C.GREGORIAN, C.JULIAN, (1582, 10, 10), (1582, 9, 30)),
		(C.GREGORIAN, C.HIJRI_IIC, (9999, 12, 31), (9666, 4, 2)),
	):
		year, month, day = ymd
		result = convert(source, target, year=year, month=month, day=day)
		actual = result.target.year, result.target.month, result.target.day
		assert actual == expected, (actual, expected)
		records.append({"input": asdict(result.source), "output": asdict(result.target), "rd": result.rd, "passed": True})
		print(f"نجح: {source.value} {year}-{month}-{day} إلى {target.value}: {actual[0]}-{actual[1]}-{actual[2]}")
	for source, ymd, expected_code in (
		(C.HIJRI_IIC, (9666, 4, 3), "out_of_range"),
		(C.GREGORIAN, (1700, 2, 29), "invalid_day"),
		(C.HIJRI_IIC, (15, 12, 30), "invalid_day"),
	):
		try:
			convert(source, C.GREGORIAN, year=ymd[0], month=ymd[1], day=ymd[2])
		except HistoricalCalendarError as error:
			assert error.code.value == expected_code
			records.append({"calendar": source.value, "input": ymd, "error_code": error.code, "field": error.field, "passed": True})
			print(f"نجح الرفض: {source.value} {ymd}: {error.code.value}")
		else:
			raise AssertionError("Invalid date was accepted")
	output = ROOT / "docs/historical_converter_task1/reference_summary.json"
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(json.dumps({
		"manual_api_checks": records,
		"upper_julian": asdict(from_rd(MAX_RD, C.JULIAN)),
		"evidence": {
			"wustenfeld_pdf_sha256": "d92b6f30627bb9c413b9e028a0a8eabf8a715ca5bc470f939a46fec764697080",
			"directly_read_this_task": [
				"printed p16/PDF25: year 365 row; continued on p17/PDF26, Ramadan begins 3 May 976 Julian; day 12 adds 11",
				"printed p28/PDF37: Safar 656 begins 7 February 1258 Julian; day 4 adds 3",
			],
			"other_fixed_test_anchors": "Transcribed from study section 4.1; not all original table pages reread this task.",
			"qualification": "Arithmetic correspondences, not independent proof of event dates.",
		},
	}, ensure_ascii=False, indent=2), encoding="utf-8")
	print("اكتملت 11 تجربة فعلية بنجاح: 8 تحويلات و3 حالات رفض.")


if __name__ == "__main__":
	main()
