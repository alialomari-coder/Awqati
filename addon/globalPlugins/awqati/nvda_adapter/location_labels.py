"""Localized place presentation; stable identities remain independent of labels."""
from functools import cmp_to_key, lru_cache
import re
import unicodedata

from .settings_sections import is_rtl_language

ARAB_COUNTRIES = frozenset("SA AE BH KW QA OM YE IQ JO PS LB SY EG SD SO DJ KM LY TN DZ MA MR".split())
_ARABIC_ALPHABET = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"
_ARABIC_ORDER = {letter: index for index, letter in enumerate(_ARABIC_ALPHABET)}


def normalized_name(value):
	"""Ignore vocalization, tatweel, alef variants and spacing for presentation sort."""
	value = unicodedata.normalize("NFKD", value.replace("ـ", "")).casefold()
	value = "".join(c for c in value if unicodedata.category(c) not in ("Mn", "Cf"))
	return " ".join(value.translate(str.maketrans({"ى": "ي", "ة": "ه", "ٱ": "ا"})).split())


def fallback_key(value):
	# Explicit Arabic alphabet, then deterministic non-Arabic characters.
	return tuple((1, _ARABIC_ORDER[c]) if c in _ARABIC_ORDER else (0 if c.isspace() else 2, ord(c))
		for c in normalized_name(value))


@lru_cache(maxsize=8)
def collation_key(language):
	"""Windows linguistic collation without changing NVDA's process-wide locale.

	Normalize equivalent spellings first. A deterministic explicit Arabic alphabet
	is the fallback on other hosts or if Windows rejects the locale.
	"""
	arabic = is_rtl_language(language)
	try:
		import ctypes
		compare = ctypes.WinDLL("kernel32", use_last_error=True).CompareStringEx
		compare.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_int,
			ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
		compare.restype = ctypes.c_int
	except (AttributeError, OSError):
		return fallback_key if arabic else normalized_name
	locale = "ar-SA" if arabic else "en-US"
	def compare_names(left, right):
		result = compare(locale, 0x1000, left, len(left), right, len(right), None, None, 0)
		if result:
			return result - 2
		a, b = (fallback_key(left), fallback_key(right)) if arabic else (left, right)
		return (a > b) - (a < b)
	wrapper = cmp_to_key(compare_names)
	return lambda value: wrapper(normalized_name(value))


def _arabic_name(names):
	return next((name.strip() for name in names if re.search(r"[ؠ-ي]", name)
		and not any("LATIN" in unicodedata.name(c, "") for c in name)), None)


def city_name(match, language):
	if is_rtl_language(language):
		return _arabic_name(match.arabic_names) or match.location.name
	return match.english_names[0] if match.english_names else match.location.name


def _human_name(value):
	return bool(value and any(c.isalpha() for c in value) and not re.fullmatch(r"[A-Z0-9._-]{1,8}", value))


def subdivisions(match, language):
	arabic = is_rtl_language(language)
	result = []
	for names, original in ((match.arabic_admin1_names, match.admin1_name),
			(match.arabic_admin2_names, match.admin2_name)):
		value = (_arabic_name(names) or (None if match.country_code in ARAB_COUNTRIES else original)) if arabic else original
		if _human_name(value) and value not in result:
			result.append(value)
	return tuple(result)


def country_choices(countries, language, translate):
	key = collation_key(language)
	return tuple(sorted(countries, key=lambda country: (key(translate(country.name)), country.code)))


def location_choices(service, country_code, query, language):
	"""All Arab records when blank; all aliases searched before display ranking.

	Run on the existing search worker. Never load data for other countries.
	"""
	count = next(country.city_count for country in service.countries() if country.code == country_code)
	arab = country_code in ARAB_COUNTRIES
	if query:
		matches = service.search(country_code, query, count)
	else:
		matches = service.browse(country_code, count if arab else 40)
	key = collation_key(language)
	ordered = tuple(sorted(matches, key=lambda match: (
		match.match_strength if query else 0, key(city_name(match, language)),
		tuple(key(name) for name in subdivisions(match, language)), int(match.location.location_id))))
	return ordered if arab else ordered[:40]
