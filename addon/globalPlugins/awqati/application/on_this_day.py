"""Dormant asynchronous service. Construct explicitly in a future NVDA adapter.

Pass GlobalPlugin._language as language and wx.CallAfter as dispatch. No service
is instantiated by task 1. Call request() on demand and close() at termination.
Callbacks receive Day or OnThisDayError, only while their date/language is valid.
Future.result() is intended for tests, never for the NVDA main thread.
"""
from collections import deque
from concurrent.futures import Future
from datetime import date
import threading
import time

from .operation import CancellationToken, OperationCancelled
from ..domain.on_this_day import Day, Failure, OnThisDayError

UNAVAILABLE_MESSAGES = {
    "ar": "تعذر توفر معلومات باللغة المحددة",
    "en": "Information is unavailable in the selected language.",
}


class OnThisDayService:
    def __init__(self, provider, cache, *, language, dispatch, today=date.today, monotonic=time.monotonic):
        self.provider, self.cache = provider, cache
        self.language, self.dispatch, self.today, self.monotonic = language, dispatch, today, monotonic
        self._lock = threading.RLock()
        self._key = None
        self._generation = 0
        self._closed = False
        self._worker = None
        self._queue = deque()
        self._flights = {}
        self._memory = None
        self._cooldown = {}
        # A corrupt cache or failed write does not discard successfully fetched history.
        self.storage_error = None

    def _current_key(self):
        # language must be Awqati's existing normalized language provider.
        return (self.today(), self.language())

    def request(self, callback=None):
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
            if self._memory is not None and self._memory[0] == key:
                return self._memory[1]
        self.storage_error = None
        try:
            value = self.cache.load(*key)
        except OnThisDayError as error:
            self.storage_error = error
            value = None
        if value is not None:
            return value
        blocked = self._cooldown.get(key[1])
        if blocked and self.monotonic() < blocked[0]:
            return blocked[1]
        try:
            value = self.provider.fetch(*key, token)
        except OnThisDayError as error:
            if error.kind != Failure.UNAVAILABLE:
                self._cooldown[key[1]] = (self.monotonic() + max(60, error.retry_after), error)
                return error
            value = error
        token.raise_if_cancelled()
        with self._lock:
            if not self._valid(identity):
                raise OnThisDayError(Failure.STALE, "date or language changed")
        try:
            self.cache.save(*key, value)
        except OnThisDayError as error:
            self.storage_error = error
        return value

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
