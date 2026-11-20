"""Personal alarm recurrence and cycle state, sharing the central scheduler."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone

from ..domain import AlertEvent, AlertEventType, Instant
from ..domain.alerts import utc
from .alert_scheduler import resolve_civil_time
from .general_policy import in_scope


class PersonalAlarmService:
    def __init__(self, repository, zone_provider, now_provider, diagnostic=lambda error: None):
        self.repository, self.zone_provider, self.now_provider = repository, zone_provider, now_provider
        self.diagnostic = diagnostic
        self.alarms, raw_state = repository.load()
        self.storage_error = bool(getattr(repository, "read_only", False))
        self.state = {}
        # Validate each persisted cycle separately; malformed state cannot replay sound.
        for identity, row in raw_state.items():
            if identity not in self.alarms:
                continue
            try:
                if not isinstance(row, dict):
                    raise ValueError("invalid alarm state row")
                stamp = row.get("handled", "")
                if not isinstance(stamp, str):
                    raise ValueError("invalid handled occurrence")
                if stamp:
                    datetime.strptime(stamp, "%Y-%m-%dT%H:%M")
                pending = row.get("snooze")
                if pending is not None:
                    parsed = datetime.fromisoformat(pending)
                    if parsed.tzinfo is None:
                        raise ValueError("naive snooze")
                count = row.get("count", 0)
                if type(count) is not int or count < 0:
                    raise ValueError("invalid snooze count")
                self.state[identity] = {"handled": stamp, "snooze": pending, "count": count,
                    "outcome": str(row.get("outcome", "restored"))}
            except (ValueError, TypeError) as error:
                self.diagnostic(error)
                # Fail closed for a corrupt cycle, while preserving the definition.
                self.state[identity] = {"handled": "9999-12-31T23:59", "outcome": "invalidState"}
        self.active = None

    def _commit(self, alarms, state):
        try:
            self.repository.save(alarms, state)
        except OSError:
            self.storage_error = True
            raise
        self.storage_error = False
        self.alarms, self.state = alarms, state

    def put(self, alarm):
        alarms, state = dict(self.alarms), deepcopy(self.state)
        previous = alarms.get(alarm.alarm_id)
        alarms[alarm.alarm_id] = alarm
        if previous != alarm:
            row = state.setdefault(alarm.alarm_id, {})
            row.update(snooze=None, count=0, outcome="edited")
        self._commit(alarms, state)

    def delete(self, identity):
        alarms, state = dict(self.alarms), deepcopy(self.state)
        del alarms[identity]
        state.pop(identity, None)
        self._commit(alarms, state)

    def enable_all(self, enabled):
        alarms = {key: replace(value, enabled=enabled) for key, value in self.alarms.items()}
        state = deepcopy(self.state)
        if not enabled:
            for row in state.values():
                row.update(snooze=None, outcome="disabled")
        self._commit(alarms, state)

    def next_occurrence(self, alarm, now, *, include_recent=False):
        if not alarm.enabled:
            return None
        zone = self.zone_provider()
        local = utc(now).astimezone(zone)
        handled = self.state.get(alarm.alarm_id, {}).get("handled", "")
        start = -1 if include_recent else 0
        for offset in range(start, 9):
            day = local.date() + timedelta(days=offset)
            if day.weekday() not in alarm.weekdays:
                continue
            civil = datetime.combine(day, time(alarm.hour, alarm.minute))
            if civil.isoformat(timespec="minutes") <= handled:
                continue
            candidate = resolve_civil_time(civil, zone)
            lower = utc(now) - (timedelta(minutes=10) if include_recent else timedelta())
            if candidate.astimezone(timezone.utc) >= lower:
                return Instant(candidate)
        return None

    def events(self, now, *, include_recent=False):
        if self.storage_error:
            return ()
        result = []
        for alarm in self.alarms.values():
            if not alarm.enabled:
                continue
            row = self.state.get(alarm.alarm_id, {})
            pending = row.get("snooze")
            if pending:
                when = Instant(datetime.fromisoformat(pending))
                if utc(when) >= utc(now) - timedelta(minutes=10):
                    result.append(self._event(alarm, when, snooze=True))
                else:
                    state = deepcopy(self.state)
                    state[alarm.alarm_id].update(snooze=None, outcome="expiredSnooze")
                    try:
                        self._commit(dict(self.alarms), state)
                    except OSError as error:
                        self.diagnostic(error)
                        return ()
            when = self.next_occurrence(alarm, now, include_recent=include_recent)
            if when:
                result.append(self._event(alarm, when))
        return tuple(result)

    def next_run(self, alarm, now):
        regular = self.next_occurrence(alarm, now)
        pending = self.state.get(alarm.alarm_id, {}).get("snooze")
        if pending and alarm.enabled:
            when = Instant(datetime.fromisoformat(pending))
            if utc(when) >= utc(now):
                return min((value for value in (regular, when) if value), key=utc)
        return regular

    def _event(self, alarm, when, *, snooze=False):
        # Civil key deliberately ignores UTC offset: a repeated DST hour runs once.
        civil = utc(when).astimezone(self.zone_provider()).replace(tzinfo=None)
        stamp = civil.isoformat(timespec="minutes")
        key = "personal." + alarm.alarm_id + "." + ("snooze." + when.value.isoformat() if snooze else stamp)
        return AlertEvent(key, AlertEventType.PERSONAL_ALARM, when,
            action=alarm.action, sound_ref=alarm.sound_ref, source="personalAlarm", scope="personal." + alarm.alarm_id,
            metadata={"alarm_id": alarm.alarm_id, "name": alarm.name, "duration": alarm.duration,
                "obey_quiet_hours": alarm.obey_quiet_hours, "civil": stamp, "snooze": snooze,
                "definition": alarm})

    def claimed(self, event):
        if event.event_type is not AlertEventType.PERSONAL_ALARM:
            return
        identity = event.metadata["alarm_id"]
        state = deepcopy(self.state)
        row = state.setdefault(identity, {})
        if not event.metadata["snooze"]:
            row["handled"] = event.metadata["civil"]
            row["count"] = 0
        row.update(snooze=None, outcome="presenting")
        # Reserve before any output: restart never repeats a partly presented cycle.
        self._commit(dict(self.alarms), state)
        self.active = event

    def finish(self, event, outcome):
        if event.event_type is not AlertEventType.PERSONAL_ALARM:
            return
        identity = event.metadata["alarm_id"]
        try:
            if identity in self.alarms:
                state = deepcopy(self.state)
                row = state.setdefault(identity, {})
                if row.get("outcome") != outcome:
                    row.update(outcome=outcome)
                    self._commit(dict(self.alarms), state)
        finally:
            if self.active and self.active.event_id == event.event_id:
                self.active = None

    def discarded(self, event, outcome):
        if event.event_type is not AlertEventType.PERSONAL_ALARM:
            return
        identity = event.metadata["alarm_id"]
        if identity not in self.alarms:
            return
        state = deepcopy(self.state)
        row = state.setdefault(identity, {})
        if not event.metadata["snooze"]:
            row["handled"] = max(row.get("handled", ""), event.metadata["civil"])
        row.update(snooze=None, outcome=outcome)
        try:
            self._commit(dict(self.alarms), state)
        except OSError as error:
            self.diagnostic(error)

    def snooze(self, now):
        event = self.active
        if event is None:
            return False
        identity = event.metadata["alarm_id"]
        alarm = self.alarms.get(identity)
        row = self.state.get(identity, {})
        count = row.get("count", 0)
        if alarm is None or not alarm.snooze_enabled or (alarm.snooze_limit is not None and count >= alarm.snooze_limit):
            return False
        state = deepcopy(self.state)
        state[identity].update(snooze=(utc(now) + timedelta(minutes=alarm.snooze_minutes)).isoformat(),
            count=count + 1, outcome="snoozed")
        self._commit(dict(self.alarms), state)
        return True

    def cancel_snooze(self, identity, expected_when):
        """Stop only the pending cycle created by the last successful snooze."""
        row = self.state.get(identity, {})
        if not expected_when or row.get("snooze") != expected_when:
            return False
        state = deepcopy(self.state)
        state[identity].update(snooze=None, outcome="stopped")
        self._commit(dict(self.alarms), state)
        return True


class CombinedAlarmSource:
    """Compose producers, with no second scheduler or competing presentation queue."""
    def __init__(self, existing, alarms):
        self.existing, self.alarms = existing, alarms

    def settings_changed(self, *args):
        self.existing.settings_changed(*args)

    def next_rebuild_at(self, now):
        local = utc(now).astimezone(self.alarms.zone_provider())
        midnight = Instant(resolve_civil_time(datetime.combine(local.date() + timedelta(days=1), time()), self.alarms.zone_provider()))
        old = self.existing.next_rebuild_at(now)
        return min((value for value in (old, midnight) if value), key=utc)

    def __call__(self, now, reason, scope):
        existing = self.existing(now, reason, scope)
        if scope is None or in_scope(scope, "personal"):
            personal = self.alarms.events(now, include_recent=reason in ("startup", "resume", "systemTimeChanged", "localDayChanged"))
            return (*existing, *(event for event in personal if in_scope(event.scope, scope)))
        return existing
