"""Extract and validate Awqati's complete user-facing catalog and NVDA resources."""
from pathlib import Path
import ast
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".build-deps"))
sys.path.insert(0, str(ROOT))
from babel.messages.catalog import Catalog
from babel.messages.extract import extract
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo
import buildVars


CONVERTER_MODULES = {
	"advanced_converter_dialog.py", "advanced_converter_model.py",
	"calendar_converter_dialog.py", "calendar_converter_model.py",
	"calendar_converter_text.py", "conversion_result_dialog.py", "converter_dialog_base.py",
}


def extract_catalog(domain="nvda"):
	if domain not in ("nvda", "calendar_converter"):
		raise ValueError(domain)
	catalog = Catalog(project="Awqati", version=buildVars.addon_info["addon_version"], charset="utf-8")
	paths = sorted({path for pattern in buildVars.i18nSources for path in ROOT.glob(pattern)})
	for path in paths:
		converter = path.name in CONVERTER_MODULES
		if converter != (domain == "calendar_converter"):
			continue
		if converter:
			# Babel concatenates conditional-expression branches into nonexistent
			# msgids. These modules use ConverterText.gettext, a separate domain.
			for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
				if not isinstance(node, ast.Call) or not node.args:
					continue
				name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
				if name in ("_", "gettext"):
					for value in ast.walk(node.args[0]):
						if isinstance(value, ast.Constant) and isinstance(value.value, str):
							catalog.add(value.value, locations=[(path.relative_to(ROOT).as_posix(), value.lineno)])
			continue
		with path.open("rb") as source:
			for line, message, comments, context in extract("python", source, keywords={"_": None, "N_": None}):
				catalog.add(message, locations=[(path.relative_to(ROOT).as_posix(), line)], auto_comments=comments)
	if domain == "calendar_converter":
		return catalog
	# These names are data labels, translated only at the UI boundary.
	data = ROOT / "addon/globalPlugins/awqati/data"
	for relative, key in (("locations/metadata.json", "countries"), ("calculation_methods/methods.json", "methods")):
		path = data / relative
		for item in json.loads(path.read_text(encoding="utf-8"))[key]:
			catalog.add(item["name"], locations=[(path.relative_to(ROOT).as_posix(), 1)])
	for key in ("addon_summary", "addon_description"):
		catalog.add(buildVars.addon_info[key], locations=[("buildVars.py", 1)])
	return catalog


def build_translations(staging: Path):
	catalog = extract_catalog()
	output = ROOT / "build/messages.pot"
	output.parent.mkdir(parents=True, exist_ok=True)
	with output.open("wb") as stream:
		write_po(stream, catalog, sort_output=True)
	with (ROOT / "addon/locale/ar/LC_MESSAGES/nvda.po").open("rb") as stream:
		arabic = read_po(stream, locale="ar")
	missing = [message.id for message in catalog if message.id and (message.id not in arabic or not arabic[message.id].string or arabic[message.id].fuzzy)]
	errors = list(arabic.check())
	if missing or errors:
		raise ValueError(f"Incomplete Arabic catalog: {missing!r}; errors: {errors!r}")
	destination = staging / "locale/ar/LC_MESSAGES/nvda.mo"
	destination.parent.mkdir(parents=True, exist_ok=True)
	with destination.open("wb") as stream:
		write_mo(stream, arabic)
	# Compile the independent converter domain from its PO at every build;
	# never trust a possibly stale checked-in binary resource.
	with (ROOT / "addon/locale/ar/LC_MESSAGES/calendar_converter.po").open("rb") as stream:
		converter = read_po(stream, locale="ar")
	invalid = [m.id for m in converter if m.id and (not m.string or m.fuzzy)]
	invalid += [m.id for m in extract_catalog("calendar_converter") if m.id and m.id not in converter]
	converter_errors = list(converter.check())
	if invalid or converter_errors:
		raise ValueError(f"Incomplete converter catalog: {invalid!r}; errors: {converter_errors!r}")
	with destination.with_name("calendar_converter.mo").open("wb") as stream:
		write_mo(stream, converter)
	import gettext
	with destination.open("rb") as stream:
		translate = gettext.GNUTranslations(stream).gettext
	template = (ROOT / "manifest-translated.ini.tpl").read_text(encoding="utf-8")
	(staging / "locale/ar/manifest.ini").write_text(template.format_map({key: translate(value) for key, value in buildVars.addon_info.items() if isinstance(value, str)}), encoding="utf-8")
	print(f"Validated {len(catalog)} gettext messages; compiled Arabic NVDA catalog")


if __name__ == "__main__":
	build_translations(ROOT / "build/awqati")
