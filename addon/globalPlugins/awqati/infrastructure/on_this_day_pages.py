"""Write only newly generated, inert HTML to a private user-data subdirectory."""
import os
from pathlib import Path
import tempfile

from .on_this_day_html import render_html
from ..domain.on_this_day import SECTION_KEYS


class LocalDayPages:
    def __init__(self, root, opener=None):
        self.root = Path(root)
        self.opener = opener if opener is not None else os.startfile

    def open(self, day, key, translate):
        if key not in SECTION_KEYS or day.language not in {"ar", "en"}:
            raise ValueError("invalid page identity")
        content = render_html(day, key, translate)
        self.root.mkdir(parents=True, exist_ok=True)
        # Eight bounded names; no names or paths come from Wikipedia titles.
        target = self.root / f"{day.language}-{key}.html"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.opener(str(target.resolve()))
        return target
