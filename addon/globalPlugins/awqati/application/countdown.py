"""Independent sleep-inclusive countdowns with transactional state transitions.

The injected clock returns nanoseconds; UTC is only used across NVDA sessions.
Alert attempts are reserved on disk before output. A crash may therefore lose
an in-progress attempt, but cannot replay it. No periodic disk checkpointing.
"""
from copy import deepcopy
from dataclasses import asdict
import math
from uuid import uuid4
from ..domain.countdown import Countdown, STATES, MAX_DURATION
from ..domain import AlertAction, AlertEvent, AlertEventType

NS = 10**9
GRACE = 600


class CountdownService:
    def __init__(self, clock, wall, repository):
        self.clock, self.wall, self.repository = clock, wall, repository
        self.storage_error = False
        self.definitions, self.rows = {}, {}
        raw = repository.load()
        if raw is None:
            return
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("timers"), list) or len(raw["timers"]) > 10000:
            raise ValueError("invalid countdown file")
        tick, now = clock(), wall()
        for entry in raw["timers"]:
            definition = dict(entry["definition"])
            definition["action"] = AlertAction(definition["action"])
            timer = Countdown(**definition)
            if timer.timer_id in self.definitions:
                raise ValueError("duplicate countdown identity")
            row = dict(entry["runtime"])
            if row["state"] not in STATES or type(row["ack"]) is not bool or type(row["attempt"]) is not int or not 0 <= row["attempt"] <= 100:
                raise ValueError("invalid countdown state")
            for key in ("remaining", "deadline", "finished", "next"):
                if row[key] is not None and (type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0):
                    raise ValueError("invalid countdown reference")
            if not 0 <= row["remaining"] <= MAX_DURATION * NS or not isinstance(row["cycle"], str) or len(row["cycle"]) != 32:
                raise ValueError("invalid countdown cycle")
            if row["state"] == "running":
                if row["deadline"] is None:
                    raise ValueError("missing countdown deadline")
                row["deadline"] = tick + round((row["deadline"] - now) * NS)
            elif row["state"] == "finished":
                if row["finished"] is None:
                    raise ValueError("missing countdown completion")
                row["finished"] = tick + round((row["finished"] - now) * NS)
                if row["next"] is not None:
                    row["next"] = tick + round((row["next"] - now) * NS)
                # Previously claimed alerts and their repetitions never replay.
                if row["attempt"]:
                    row["ack"], row["next"] = True, None
            self.definitions[timer.timer_id], self.rows[timer.timer_id] = timer, row

    def _commit(self, definitions, rows):
        tick, now = self.clock(), self.wall()
        records = []
        for identity, timer in definitions.items():
            definition = asdict(timer)
            definition["action"] = timer.action.value
            row = dict(rows[identity])
            for key in ("deadline", "finished", "next"):
                if row[key] is not None:
                    row[key] = now + (row[key] - tick) / NS
            records.append({"definition": definition, "runtime": row})
        try:
            self.repository.save({"version": 1, "timers": records})
        except OSError:
            self.storage_error = True
            raise
        self.storage_error = False
        self.definitions, self.rows = definitions, rows

    def put(self, timer):
        definitions, rows = dict(self.definitions), deepcopy(self.rows)
        if timer.timer_id not in definitions and len(definitions) >= 10000:
            raise ValueError("countdown storage limit reached")
        previous = definitions.get(timer.timer_id)
        if previous and rows[timer.timer_id]["state"] in ("running", "paused"):
            raise ValueError("cancel the countdown before editing")
        definitions[timer.timer_id] = timer
        rows[timer.timer_id] = dict(state="ready", remaining=timer.duration * NS,
            deadline=None, finished=None, next=None, cycle=uuid4().hex, attempt=0, ack=False)
        self._commit(definitions, rows)

    def remaining(self, identity):
        row = self.rows[identity]
        return max(0, row["deadline"] - self.clock()) if row["state"] == "running" else row["remaining"]

    def ordered(self):
        return sorted(self.definitions, key=lambda i: (self.rows[i]["state"] != "running",
            self.remaining(i) if self.rows[i]["state"] == "running" else 0, i))

    def transition(self, identity, action, *, confirmed=False):
        rows = deepcopy(self.rows)
        row, timer = rows[identity], self.definitions[identity]
        tick = self.clock()
        state = row["state"]
        if action == "restart":
            if state in ("running", "paused") and not confirmed:
                raise ValueError("restart confirmation required")
            row.update(state="running", remaining=timer.duration * NS, deadline=tick + timer.duration * NS,
                finished=None, next=None, cycle=uuid4().hex, attempt=0, ack=False)
        elif action in ("start", "resume") and state in ("ready", "paused"):
            row.update(state="running", deadline=tick + row["remaining"])
        elif action == "pause" and state == "running":
            remaining = max(0, row["deadline"] - tick)
            if not remaining:
                return False  # Expiry must be handled, never converted into a pause.
            row.update(state="paused", remaining=remaining, deadline=None)
        elif action == "cancel" and state != "cancelled":
            row.update(state="cancelled", remaining=timer.duration * NS, deadline=None, next=None, ack=True)
        elif action == "ack" and state == "finished" and not row["ack"]:
            row.update(ack=True, next=None)
        else:
            return False
        self._commit(dict(self.definitions), rows)
        return True

    def delete(self, identity):
        definitions, rows = dict(self.definitions), deepcopy(self.rows)
        del definitions[identity]
        del rows[identity]
        self._commit(definitions, rows)

    def poll(self, instant):
        """Return at most one pending event per timer, without accumulating repeats."""
        rows, changed, events = deepcopy(self.rows), False, []
        tick = self.clock()
        for identity, timer in self.definitions.items():
            row = rows[identity]
            if row["state"] == "running" and tick >= row["deadline"]:
                row.update(state="finished", remaining=0, finished=row["deadline"], next=row["deadline"], deadline=None)
                changed = True
            if row["state"] != "finished" or row["ack"] or row["next"] is None:
                continue
            if tick - row["next"] > GRACE * NS:
                row.update(ack=True, next=None)
                changed = True
                continue
            if tick >= row["next"]:
                key = "timer." + identity + "." + row["cycle"] + "." + str(row["attempt"])
                events.append(AlertEvent(key, AlertEventType.COUNTDOWN, instant, action=timer.action,
                    sound_ref=timer.sound_ref, scope="timers." + identity, source="countdown",
                    metadata={"timer_id": identity, "name": timer.name, "cycle": row["cycle"],
                        "attempt": row["attempt"], "obey_quiet_hours": timer.obey_quiet_hours}))
        if changed:
            self._commit(dict(self.definitions), rows)
        return events

    def handled(self, event, outcome=None):
        if event.event_type is not AlertEventType.COUNTDOWN:
            return
        identity = event.metadata["timer_id"]
        row = self.rows.get(identity)
        if not row or row["cycle"] != event.metadata["cycle"] or row["attempt"] != event.metadata["attempt"] or row["ack"]:
            return
        rows = deepcopy(self.rows)
        row, timer = rows[identity], self.definitions[identity]
        row["attempt"] += 1
        done = row["attempt"] >= (timer.count if timer.repeat else 1) or outcome is not None
        row.update(ack=done, next=None if done else self.clock() + timer.interval * NS)
        self._commit(dict(self.definitions), rows)

    def checkpoint(self):
        self._commit(dict(self.definitions), deepcopy(self.rows))
