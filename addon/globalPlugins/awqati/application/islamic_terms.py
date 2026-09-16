"""Central bilingual glossary for Islamic terms shown or spoken by Awqati.

Internal identities stay in Domain. This module owns presentation spelling and
the distinction between devotional formulae, feature names, reminders and
astronomical descriptions.
"""

from __future__ import annotations

from enum import Enum


def N_(message: str) -> str:
	"""Mark an English source message for gettext without translating it here."""
	return message


class TermKind(Enum):
	DEVOTIONAL = "devotional"
	FEATURE = "feature"
	REMINDER = "reminder"
	PRAYER = "prayer"
	ASTRONOMICAL = "astronomical"


# English is the source/fallback language. Arabic values are reviewed display
# resources. Devotional English uses transliteration, not a free translation.
_TERMS = {
	"fajr": (TermKind.PRAYER, N_("Fajr"), "الفجر"),
	"dhuhr": (TermKind.PRAYER, N_("Dhuhr"), "الظهر"),
	"asr": (TermKind.PRAYER, N_("Asr"), "العصر"),
	"maghrib": (TermKind.PRAYER, N_("Maghrib"), "المغرب"),
	"isha": (TermKind.PRAYER, N_("Isha"), "العشاء"),
	"sunrise": (TermKind.ASTRONOMICAL, N_("Sunrise"), "الشروق"),
	"midnight": (TermKind.ASTRONOMICAL, N_("Midnight"), "منتصف الليل"),
	"last_third_start": (TermKind.ASTRONOMICAL, N_("Start of the last third"), "بداية الثلث الأخير"),
	"subhanAllah": (TermKind.DEVOTIONAL, N_("Subhan Allah."), "سبحان الله."),
	"alhamduLillah": (TermKind.DEVOTIONAL, N_("Alhamdulillah."), "الحمد لله."),
	"laIlahaIllaAllah": (TermKind.DEVOTIONAL, N_("La ilaha illa Allah."), "لا إله إلا الله."),
	"allahuAkbar": (TermKind.DEVOTIONAL, N_("Allahu Akbar."), "الله أكبر."),
	"laHawlaWaLaQuwwata": (TermKind.DEVOTIONAL,
		N_("La hawla wa la quwwata illa billah."), "لا حول ولا قوة إلا بالله."),
	"astaghfiruAllah": (TermKind.DEVOTIONAL, N_("Astaghfirullah."), "أستغفر الله."),
	"salatAlaAlNabi": (TermKind.FEATURE,
		N_("Blessings upon the Prophet."), "الصلاة على النبي."),
	"udhkurAllah": (TermKind.REMINDER,
		N_("Remember Allah, and He will remember you."), "اذكر الله يذكرك."),
	"laTansaDhikrAllah": (TermKind.REMINDER,
		N_("Do not forget to remember Allah."), "لا تنس ذكر الله."),
}

# Existing Domain enums use camelCase for this astronomical event.  Keep the
# presentation glossary descriptive key stable while accepting that neutral
# Domain identity at the application boundary.
_ALIASES = {"lastThird": "last_third_start"}


def _canonical_identity(identity: str) -> str:
	return _ALIASES.get(identity, identity)


def normalize_language(language: str) -> str:
	"""Return the supported language or the official English fallback."""
	base = language.split("_", 1)[0].split("-", 1)[0].casefold()
	return "ar" if base == "ar" else "en"


def term_text(identity: str, language: str = "en") -> str:
	"""Render one neutral identity with the reviewed spelling for the language."""
	identity = _canonical_identity(identity)
	try:
		_kind, english, arabic = _TERMS[identity]
	except KeyError as error:
		raise ValueError(f"unknown Islamic glossary identity: {identity}") from error
	return arabic if normalize_language(language) == "ar" else english


def term_kind(identity: str) -> TermKind:
	identity = _canonical_identity(identity)
	try:
		return _TERMS[identity][0]
	except KeyError as error:
		raise ValueError(f"unknown Islamic glossary identity: {identity}") from error


def source_message(identity: str) -> str:
	"""Return the stable gettext msgid for adapters that use NVDA translation."""
	identity = _canonical_identity(identity)
	try:
		return _TERMS[identity][1]
	except KeyError as error:
		raise ValueError(f"unknown Islamic glossary identity: {identity}") from error


GLOSSARY_IDENTITIES = tuple(_TERMS)
