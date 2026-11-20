"""Atomic, independently versioned alarm storage; never rewrites settings.json."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
from ..domain.personal_alarms import PersonalAlarm
from ..domain.settings import AlertAction


class AlarmRepository:
    def __init__(self, path, diagnostic=lambda error: None):
        self.path = Path(path)
        self.diagnostic = diagnostic
        self.read_only = False

    def load(self):
        if not self.path.exists():
            return {}, {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if type(raw.get("version")) is not int or raw.get("version") != 1 or not isinstance(raw.get("alarms"), list) or not isinstance(raw.get("state"), dict):
                raise ValueError("unsupported alarm file")
        except (OSError, ValueError, TypeError, AttributeError) as error:
            self.read_only = True
            self.diagnostic(error)
            return {}, {}
        alarms = {}
        for item in raw["alarms"]:
            try:
                values = dict(item)
                values["action"] = AlertAction(values["action"])
                values["weekdays"] = tuple(values["weekdays"])
                alarm = PersonalAlarm(**values)
                if alarm.alarm_id in alarms:
                    raise ValueError("duplicate alarm identity")
                alarms[alarm.alarm_id] = alarm
            except (ValueError, TypeError, KeyError) as error:
                self.read_only = True  # Recover valid rows, preserve damaged original.
                self.diagnostic(error)
        return alarms, raw["state"]

    def save(self, alarms, state):
        if self.read_only:
            raise OSError("Alarm data requires recovery; the original file has been preserved")
        rows = []
        for alarm in alarms.values():
            row = asdict(alarm)
            row["action"] = alarm.action.value
            rows.append(row)
        payload = json.dumps({"version": 1, "alarms": rows, "state": state}, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".alarms-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
