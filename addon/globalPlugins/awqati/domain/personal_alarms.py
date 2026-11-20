"""Immutable personal alarm definitions, independent of NVDA and storage."""
from dataclasses import dataclass
from uuid import uuid4
from .settings import AlertAction

DURATIONS = (30, 60, 120, 300)
SNOOZE_MINUTES = (1, 2, 5, 10, 15, 30)


@dataclass(frozen=True, slots=True)
class PersonalAlarm:
    alarm_id: str
    name: str
    hour: int
    minute: int
    weekdays: tuple[int, ...]  # Monday=0; presentation starts Sunday.
    enabled: bool = True
    action: AlertAction = AlertAction.SOUND_AND_SPEECH
    sound_ref: str | None = None
    duration: int = 60
    snooze_enabled: bool = True
    snooze_minutes: int = 5
    snooze_limit: int | None = 3
    obey_quiet_hours: bool = False

    @classmethod
    def create(cls, name, hour, minute, weekdays, **options):
        return cls(uuid4().hex, name, hour, minute, tuple(sorted(set(weekdays))), **options)

    def __post_init__(self):
        if not isinstance(self.alarm_id, str) or not self.alarm_id or "." in self.alarm_id:
            raise ValueError("invalid alarm identity")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("alarm name is required")
        for value, maximum in ((self.hour, 23), (self.minute, 59)):
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError("invalid alarm time")
        if not isinstance(self.weekdays, tuple) or not self.weekdays or any(type(d) is not int or d not in range(7) for d in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("at least one distinct weekday is required")
        if self.action not in (AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH):
            raise ValueError("invalid alarm action")
        if type(self.duration) is not int or self.duration not in DURATIONS or type(self.snooze_minutes) is not int or self.snooze_minutes not in SNOOZE_MINUTES:
            raise ValueError("invalid alarm duration")
        if self.snooze_limit is not None and (type(self.snooze_limit) is not int or not 1 <= self.snooze_limit <= 1000000):
            raise ValueError("invalid snooze limit")
        if any(type(v) is not bool for v in (self.enabled, self.snooze_enabled, self.obey_quiet_hours)):
            raise ValueError("invalid alarm switch")
        if self.sound_ref is not None and (not isinstance(self.sound_ref, str) or not self.sound_ref.startswith("sounds/alarms/") or any(part in ("", ".", "..") or ":" in part or "\\" in part for part in self.sound_ref.split("/"))):
            raise ValueError("invalid alarm sound reference")


def validate_alarm_fields(hour, minute, weekdays):
    """Return one validation result; the adapter translates and focuses it."""
    try:
        valid = str(hour).strip() != "" and str(minute).strip() != "" and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    except (TypeError, ValueError):
        valid = False
    if not valid and not weekdays:
        return "timeAndDays"
    if not valid:
        return "time"
    if not weekdays:
        return "days"
    return None
