"""Windows sleep-inclusive high resolution clock and atomic isolated JSON files."""
import ctypes
import json
import os
from pathlib import Path
import tempfile


class InterruptClock:
    source = "Windows QueryInterruptTimePrecise (100 ns units)"

    def __init__(self):
        # Use the public API-set contract. On Windows 11 this function is not
        # necessarily exported by kernel32.dll despite its documentation label.
        self._query = ctypes.WinDLL("api-ms-win-core-realtime-l1-1-1", use_last_error=True).QueryInterruptTimePrecise
        self._query.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
        self._query.restype = None

    def __call__(self):
        value = ctypes.c_ulonglong()
        self._query(ctypes.byref(value))
        return value.value * 100


class StopwatchRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.read_only = False

    def load(self):
        if not self.path.exists():
            return None
        try:
            if self.path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Stopwatch file too large")
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.read_only = True
            raise

    def save(self, payload):
        if self.read_only:
            raise OSError("Existing stopwatch file needs recovery")
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".stopwatch-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
