"""On-demand asynchronous Wikipedia service with daily caching.

Pass GlobalPlugin._language as language and wx.CallAfter as dispatch.
Call request() on demand and close() at termination.
Callbacks receive Day or OnThisDayError, only while their date/language is valid.
Future.result() is intended for tests, never for the NVDA main thread.
"""
from collections import deque
from concurrent.futures import Future
from datetime import date
import threading
import time

from .operation import CancellationToken, OperationCancelled
from ..domain.on_this_day import Day, Failure, OnThisDayError, SECTION_KEYS

UNAVAILABLE_MESSAGES = {
    "ar": "تعذر توفر معلومات باللغة المحددة",
    "en": "Information is unavailable in the selected language.",
}

# Only a requested extraction failure can trigger a refresh, once per interval.
# The source API returns all sections together; successful sections never expire.
EXTRACTION_RETRY_SECONDS = 15 * 60


def extraction_failed(value):
    return isinstance(value, Day) and any(s.failure == Failure.EXTRACTION for s in value.sections)


class OnThisDayService:
    def __init__(self, provider, cache, *, language, dispatch, today=date.today, monotonic=time.monotonic,
                 now=time.time):
        self.provider, self.cache = provider, cache
        self.language, self.dispatch, self.today, self.monotonic = language, dispatch, today, monotonic
        self.now = now
        self._extraction_retry = {}
        self._lock = threading.RLock()
        self._key = None
        self._generation = 0
        self._closed = False
        self._worker = None
        self._queue = deque()
        self._flights = {}
        self._requested_sections = {}
        self._memory = None
        self._cooldown = {}
        # A corrupt cache or failed write does not discard successfully fetched history.
        self.storage_error = None

    def _current_key(self):
        # language must be Awqati's existing normalized language provider.
        return (self.today(), self.language())

    def request(self, callback=None, *, section=None):
        if section is not None and section not in SECTION_KEYS:
            raise ValueError("unknown OnThisDay section")
        future = Future()
        with self._lock:
            if self._closed:
                future.set_exception(OnThisDayError(Failure.CANCELLED, "service closed"))
                return future
            key = self._current_key()
            if key != self._key:
                self._generation += 1
                self._key, self._memory = key, None
                for token, _ in self._flights.values():
                    token.cancel()
            identity = (key, self._generation)
            self._requested_sections.setdefault(identity, set()).add(section)
            if identity in self._flights:
                self._flights[identity][1].append((future, callback))
            else:
                token = CancellationToken()
                self._flights[identity] = (token, [(future, callback)])
                self._queue.append(identity)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="Awqati OnThisDay", daemon=True)
                self._worker.start()
        return future

    def _valid(self, identity):
        return (not self._closed and identity == (self._key, self._generation)
                and identity[0] == self._current_key())

    def _obtain(self, identity, token):
        key, _ = identity
        token.raise_if_cancelled()
        with self._lock:
            value = self._memory[1] if self._memory is not None and self._memory[0] == key else None
        if value is None:
            self.storage_error = None
            try:
                value = self.cache.load(*key)
                if extraction_failed(value) and key not in self._extraction_retry:
                    # Old schema-2 partial caches lack a deadline: retry once now.
                    remaining = max(0, (self.cache.retry_at or 0) - self.now())
                    self._extraction_retry[key] = self.monotonic() + remaining
            except OnThisDayError as error:
                self.storage_error = error
        partial = value if extraction_failed(value) else None
        if value is not None and partial is None:
            return value
        if partial is not None and self.monotonic() < self._extraction_retry.get(key, 0):
            return partial
        if partial is not None:
            with self._lock:
                requested = self._requested_sections[identity]
                if None not in requested and not any(
                        partial.section(section).failure == Failure.EXTRACTION for section in requested):
                    return partial
        blocked = self._cooldown.get(key[1])
        if blocked and self.monotonic() < blocked[0]:
            return partial if partial is not None else blocked[1]
        if partial is not None:
            # Reserve before fetching, so a restart does not bypass the interval.
            token.raise_if_cancelled()
            with self._lock:
                if not self._valid(identity):
                    raise OnThisDayError(Failure.STALE, "date or language changed")
            self._save_partial(key, partial)
        try:
            value = self.provider.fetch(*key, token)
        except OnThisDayError as error:
            if partial is not None:
                token.raise_if_cancelled()
                with self._lock:
                    if not self._valid(identity):
                        raise OnThisDayError(Failure.STALE, "date or language changed")
                if error.kind in {Failure.CANCELLED, Failure.STALE}:
                    raise
                delay = max(EXTRACTION_RETRY_SECONDS, error.retry_after)
                self._cooldown[key[1]] = (self.monotonic() + delay, error)
                self._save_partial(key, partial, delay)
                return partial
            if error.kind != Failure.UNAVAILABLE:
                self._cooldown[key[1]] = (self.monotonic() + max(60, error.retry_after), error)
                return error
            value = error
        token.raise_if_cancelled()
        with self._lock:
            if not self._valid(identity):
                raise OnThisDayError(Failure.STALE, "date or language changed")
        if partial is not None and isinstance(value, Day):
            # Keep one coherent revision; never replace a readable section with
            # a new failure or splice sections from different source revisions.
            if any(not old.failure and new.failure for old, new in zip(partial.sections, value.sections)):
                value = partial
        if extraction_failed(value):
            self._save_partial(key, value)
            return value
        try:
            self.cache.save(*key, value)
        except OnThisDayError as error:
            self.storage_error = error
        return value

    def _save_partial(self, key, value, delay=EXTRACTION_RETRY_SECONDS):
        self._extraction_retry[key] = self.monotonic() + delay
        try:
            self.cache.save(*key, value, retry_at=self.now() + delay)
        except OnThisDayError as error:
            self.storage_error = error

    def _run(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                identity = self._queue.popleft()
                token, _ = self._flights[identity]
            try:
                value = self._obtain(identity, token)
            except OperationCancelled:
                value = OnThisDayError(Failure.CANCELLED, "operation cancelled")
            except OnThisDayError as error:
                value = error
            except Exception as error:
                value = OnThisDayError(Failure.RESPONSE, f"unexpected provider failure: {error}")
            with self._lock:
                valid = self._valid(identity)
                if not valid:
                    value = OnThisDayError(Failure.CANCELLED if self._closed else Failure.STALE,
                                           "request no longer current")
                if valid and (isinstance(value, Day) or value.kind == Failure.UNAVAILABLE):
                    self._memory = (identity[0], value)
                _, subscribers = self._flights.pop(identity)
                self._requested_sections.pop(identity, None)
            for future, callback in subscribers:
                if future.set_running_or_notify_cancel():
                    if isinstance(value, OnThisDayError):
                        future.set_exception(value)
                    else:
                        future.set_result(value)
                if callback is not None and valid and not future.cancelled():
                    def deliver(callback=callback, value=value, identity=identity, future=future):
                        with self._lock:
                            if not self._valid(identity) or future.cancelled():
                                return
                        callback(value)
                    try:
                        self.dispatch(deliver)
                    except Exception:
                        # Shutdown may reject queued GUI work; futures are already resolved.
                        pass

    def close(self):
        with self._lock:
            self._closed = True
            self._generation += 1
            self._memory = None
            for token, _ in self._flights.values():
                token.cancel()
