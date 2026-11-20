"""Compile only the new isolated converter gettext domain; never build an add-on."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".build-deps"))
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo


def main():
	path = ROOT / "addon/locale/ar/LC_MESSAGES/calendar_converter.po"
	with path.open("rb") as stream:
		catalog = read_po(stream, locale="ar")
	errors = list(catalog.check())
	if errors:
		raise ValueError(errors)
	with path.with_suffix(".mo").open("wb") as stream:
		write_mo(stream, catalog)
	print("Compiled isolated calendar_converter.mo; existing catalogs untouched.")


if __name__ == "__main__":
	main()
