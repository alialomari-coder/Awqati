"""Reproducible task-2 API probes; no UI, build or user settings."""
from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.application.historical_conversion import (
	ConversionCalendar as C, HijriMethod as M, HistoricalConversionService,
)
from awqati.infrastructure.ummalqura_provider import UmmAlQuraProvider


def main():
	provider = UmmAlQuraProvider()  # Explicit bundled provider for this probe only.
	service = HistoricalConversionService(provider)
	rows = []
	def probe(label, source, target, y, m, d, method, expected=None, error=None):
		result = service.convert(source, target, year=y, month=m, day=d, hijri_method=method)
		if error:
			assert result.error and result.error.code == error, result
		else:
			assert result.successful, result.error
			assert (result.converted.year, result.converted.month, result.converted.day) == expected, result
		rows.append({"label": label, "expected_date": expected, "expected_error": error,
			"passed": True, "result": asdict(result)})
		print(label + ": " + (result.error.code if result.error else
			f"{result.converted.year}-{result.converted.month:02}-{result.converted.day:02}"))
	probe("Umm al-Qura H1448-4-1 to Gregorian", C.HIJRI, C.GREGORIAN, 1448, 4, 1, M.UMM_AL_QURA, (2026, 9, 12))
	probe("IIc H1448-4-1 to Gregorian", C.HIJRI, C.GREGORIAN, 1448, 4, 1, M.IIC, (2026, 9, 14))
	probe("IIc H365-9-12 to Gregorian", C.HIJRI, C.GREGORIAN, 365, 9, 12, M.IIC, (976, 5, 19))
	probe("IIc H365-9-12 to Julian", C.HIJRI, C.JULIAN, 365, 9, 12, M.IIC, (976, 5, 14))
	probe("Umm al-Qura H365 rejected", C.HIJRI, C.GREGORIAN, 365, 9, 12, M.UMM_AL_QURA, error="ummalqura_out_of_range")
	probe("Gregorian to Umm al-Qura", C.GREGORIAN, C.HIJRI, 2026, 9, 12, M.UMM_AL_QURA, (1448, 4, 1))
	probe("Gregorian to IIc", C.GREGORIAN, C.HIJRI, 2026, 9, 14, M.IIC, (1448, 4, 1))
	probe("Julian leap day to Gregorian", C.JULIAN, C.GREGORIAN, 1700, 2, 29, None, (1700, 3, 11))
	probe("Gregorian invalid leap day", C.GREGORIAN, C.JULIAN, 1700, 2, 29, None, error="invalid_day")
	probe("Gregorian reform gap remains valid", C.GREGORIAN, C.JULIAN, 1582, 10, 10, None, (1582, 9, 30))
	probe("IIc upper boundary", C.HIJRI, C.JULIAN, 9666, 4, 2, M.IIC, (9999, 10, 19))
	probe("IIc above upper boundary", C.HIJRI, C.GREGORIAN, 9666, 4, 3, M.IIC, error="out_of_range")
	for label, civil in (("first", provider.first_supported_gregorian_date),
		("last", provider.last_supported_gregorian_date)):
		h = provider.from_gregorian(civil)
		probe("Umm al-Qura " + label, C.GREGORIAN, C.HIJRI, civil.year, civil.month, civil.day,
			M.UMM_AL_QURA, (h.year, h.month, h.day))
	for label, civil in (("before", provider.first_supported_gregorian_date - timedelta(days=1)),
		("after", provider.last_supported_gregorian_date + timedelta(days=1))):
		probe("Umm al-Qura " + label, C.GREGORIAN, C.HIJRI, civil.year, civil.month, civil.day,
			M.UMM_AL_QURA, error="ummalqura_out_of_range")
	output = ROOT / "docs/historical_converter_task2"
	output.mkdir(parents=True, exist_ok=True)
	summary = {"checks": len(rows), "passed": len(rows), "failed": 0,
		"ummalqura_days": (provider.last_supported_gregorian_date - provider.first_supported_gregorian_date).days + 1,
		"provider_metadata": provider.metadata, "samples": rows}
	(output / "reference_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"Completed {len(rows)} API probes successfully.")


if __name__ == "__main__":
	main()
