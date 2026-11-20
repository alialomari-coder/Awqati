"""Countdown definitions. Runtime state is owned by CountdownService."""
from dataclasses import dataclass
from uuid import uuid4
from .settings import AlertAction

INTERVALS = (5, 10, 15, 30, 60, 120, 300)
MAX_DURATION = 999 * 3600 + 59 * 60 + 59
STATES = ("ready", "running", "paused", "finished", "cancelled")


@dataclass(frozen=True)
class Countdown:
    timer_id: str
    name: str
    duration: int
    saved: bool = False
    action: AlertAction = AlertAction.SOUND_AND_SPEECH
    sound_ref: str | None = None
    repeat: bool = False
    interval: int = 30
    count: int = 3
    obey_quiet_hours: bool = False
    ticking: bool = False  # Additive default keeps existing version-1 files valid.

    @classmethod
    def create(cls, name, duration, **options):
        return cls(uuid4().hex, name, duration, **options)

    def __post_init__(self):
        if not isinstance(self.timer_id, str) or len(self.timer_id) != 32 or any(c not in "0123456789abcdef" for c in self.timer_id):
            raise ValueError("invalid timer identity")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 200:
            raise ValueError("invalid timer name")
        if type(self.duration) is not int or not 1 <= self.duration <= MAX_DURATION:
            raise ValueError("invalid countdown duration")
        if self.action not in (AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH):
            raise ValueError("invalid countdown action")
        if self.interval not in INTERVALS or type(self.interval) is not int or type(self.count) is not int or not 1 <= self.count <= 100:
            raise ValueError("invalid countdown repeats")
        if any(type(x) is not bool for x in (self.saved, self.repeat, self.obey_quiet_hours, self.ticking)):
            raise ValueError("invalid countdown switch")
        if self.sound_ref is not None and (not isinstance(self.sound_ref, str) or not self.sound_ref.startswith("sounds/timers/") or any(p in ("", ".", "..") or ":" in p or "\\" in p for p in self.sound_ref.split("/"))):
            raise ValueError("invalid countdown sound")
