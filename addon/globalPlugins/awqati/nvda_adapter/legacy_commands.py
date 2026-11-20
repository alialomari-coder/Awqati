"""Hide duplicate commands while retaining saved NVDA gesture bindings."""

from __future__ import annotations


# Keep these script names callable: gestures.ini may still refer to them.
# Values identify the default command and its zero-based press index.
DUPLICATE_COMMANDS = {
	"zawaliTime": ("timeDateInfo", 0),
	"stopwatchToggle": ("stopwatchInfo", 0),
	"stopwatchLap": ("stopwatchLaps", 0),
	"stopwatchStatus": ("stopwatchTotal", 1),
	"stopwatchLastLap": ("stopwatchCurrentLap", 1),
}


def configure_legacy_visibility(plugin_class, gesture_maps) -> None:
	"""Retain descriptions for customized aliases; hide unused duplicates.

	NVDA lists scripts by their description (__doc__). Resolution of saved
	bindings uses the script name independently. Read NVDA's loaded maps only;
	never migrate or rewrite a user's gestures.ini. Collect first so a failed
	map cannot cause partial hiding. A subsequent add-on reload restores any
	newly customized alias, including bindings using the discovery-module name.
	"""
	# Restore first, so inspection failure conservatively retains every entry.
	for name in DUPLICATE_COMMANDS:
		method = getattr(plugin_class, "script_" + name)
		if not hasattr(method, "_awqati_legacy_description"):
			method._awqati_legacy_description = method.__doc__
		method.__doc__ = method._awqati_legacy_description
	assigned = {
		name
		for gesture_map in gesture_maps
		for cls, gesture, name in gesture_map.getScriptsForAllGestures()
		if issubclass(plugin_class, cls) and name in DUPLICATE_COMMANDS
	}
	for name in DUPLICATE_COMMANDS:
		method = getattr(plugin_class, "script_" + name)
		method.__doc__ = method._awqati_legacy_description if name in assigned else None
