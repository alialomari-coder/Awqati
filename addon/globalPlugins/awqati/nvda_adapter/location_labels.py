"""Choose versioned place display data without changing location identities."""
from .settings_sections import is_rtl_language


def city_name(match, language):
	names = match.arabic_names if is_rtl_language(language) else match.english_names
	return names[0] if names else match.location.name


def subdivisions(match, language):
	if not is_rtl_language(language):
		return match.subdivisions
	return tuple(names[0] if names else original for names, original in (
		(match.arabic_admin1_names, match.admin1_name),
		(match.arabic_admin2_names, match.admin2_name),
	) if names or original)
