"""Small NVDA discovery entry point that keeps core imports platform-neutral."""

from __future__ import annotations

from typing import Any

__all__ = ["GlobalPlugin"]


def __getattr__(name: str) -> Any:
	"""Load the NVDA adapter only when NVDA asks for its GlobalPlugin class."""
	if name == "GlobalPlugin":
		from .nvda_adapter.plugin import GlobalPlugin

		return GlobalPlugin
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
