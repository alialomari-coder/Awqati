"""Explicit one-shot adapter for the Windows desktop Location COM API."""

from __future__ import annotations

from collections.abc import Callable
import math
import os
import time
import threading
import logging

from ..application import LocationDetectionError
from ..domain import Coordinates, LocationDetectionFailure


_CLSID_LOCATION = "{E5B8E079-EE6D-4E33-A438-C87F2E959254}"
_IID_ILOCATION = "{AB2ECE69-56D9-4F28-B525-DE1B0EE44237}"
_IID_ILATLONG_REPORT = "{7FED806D-0EF8-4F07-80AC-36A0BEAE3134}"


class WindowsLocationAdapter:
	"""Request permission and acquire one fix only when explicitly invoked."""

	def __init__(
		self,
		*,
		parent_window_handle: int = 0,
		timeout_seconds: float = 10.0,
		poll_interval_seconds: float = 0.2,
		native_reader: Callable[[], tuple[float, float]] | None = None,
	) -> None:
		if timeout_seconds <= 0 or poll_interval_seconds <= 0:
			raise ValueError("timeout and poll interval must be positive")
		self._parent_window_handle = int(parent_window_handle)
		self._timeout_seconds = float(timeout_seconds)
		self._poll_interval_seconds = float(poll_interval_seconds)
		self._native_reader = native_reader
		self.last_diagnostics: dict[str, object] = {}

	def get_coordinates(self) -> Coordinates:
		try:
			if self._native_reader is None:
				latitude, longitude = self._read_native_coordinates()
			else:
				latitude, longitude = self._native_reader()
			return Coordinates(float(latitude), float(longitude))
		except LocationDetectionError:
			raise
		except (TypeError, ValueError, OverflowError) as error:
			raise LocationDetectionError(LocationDetectionFailure.INVALID_COORDINATES, str(error)) from error
		except OSError as error:
			raise LocationDetectionError(LocationDetectionFailure.UNAVAILABLE, str(error)) from error
		except Exception as error:
			raise LocationDetectionError(LocationDetectionFailure.API_ERROR, str(error)) from error

	def _read_native_coordinates(self) -> tuple[float, float]:
		if os.name != "nt":
			raise LocationDetectionError(LocationDetectionFailure.UNAVAILABLE, "Windows Location is unavailable")
		return _read_windows_location(
			self._parent_window_handle,
			self._timeout_seconds,
			self._poll_interval_seconds,
			self.last_diagnostics,
		)


# COM retains callback pointers independently of the Python caller. Keep the
# callback object alive until both the caller and COM release their references.
_LIVE_SINKS = {}
_SINK_LOCK = threading.RLock()


def _status_failure(status):
	if status == 2:
		return LocationDetectionFailure.DENIED
	if status == 0:
		return LocationDetectionFailure.NO_PROVIDER
	if status == 1:
		return LocationDetectionFailure.NO_FIX
	return LocationDetectionFailure.TIMEOUT


def _read_windows_location(parent_window_handle, timeout_seconds, poll_interval_seconds, diagnostics=None):
	"""Wait for one ILocationEvents report on the caller's background MTA thread."""
	import ctypes
	from ctypes import wintypes
	import uuid

	diagnostics = diagnostics if diagnostics is not None else {}
	diagnostics.clear()
	started = time.monotonic()
	diagnostics.update(report_received=False, api="ILocationEvents")
	class GUID(ctypes.Structure):
		_fields_ = (("bytes", ctypes.c_ubyte * 16),)
	def guid(value):
		return GUID.from_buffer_copy(uuid.UUID(value.strip("{}")).bytes_le)
	def method(pointer, index, *types):
		table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
		return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[index])
	def release(pointer):
		if pointer.value:
			method(pointer, 2)(pointer)
			pointer.value = None
	def checked(hr, operation):
		code = hr & 0xFFFFFFFF
		diagnostics[operation] = f"0x{code:08X}"
		if hr < 0:
			failure = LocationDetectionFailure.DENIED if code in (0x80070005, 0x800704C7) else LocationDetectionFailure.API_ERROR
			raise LocationDetectionError(failure, f"{operation}: 0x{code:08X}")
	def read_report(pointer):
		latlong = ctypes.c_void_p()
		try:
			checked(method(pointer, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
				pointer, ctypes.byref(report_iid), ctypes.byref(latlong)), "QueryInterface")
			latitude, longitude = ctypes.c_double(), ctypes.c_double()
			checked(method(latlong, 6, ctypes.POINTER(ctypes.c_double))(latlong, ctypes.byref(latitude)), "GetLatitude")
			checked(method(latlong, 7, ctypes.POINTER(ctypes.c_double))(latlong, ctypes.byref(longitude)), "GetLongitude")
			# Validate here, without including coordinates in any diagnostic text.
			if not math.isfinite(latitude.value) or not math.isfinite(longitude.value) or not -90 <= latitude.value <= 90 or not -180 <= longitude.value <= 180:
				raise LocationDetectionError(LocationDetectionFailure.INVALID_COORDINATES, "Invalid report coordinates")
			return latitude.value, longitude.value
		finally:
			release(latlong)

	ole32 = ctypes.WinDLL("ole32")
	ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
	ole32.CoInitializeEx.restype = ctypes.c_long
	ole32.CoCreateInstance.argtypes = (ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
	ole32.CoCreateInstance.restype = ctypes.c_long
	ole32.CoUninitialize.argtypes = ()
	ole32.CoUninitialize.restype = None
	location = ctypes.c_void_p()
	report_iid = guid(_IID_ILATLONG_REPORT)
	event_iid = bytes(guid("{CAE02BBF-798B-4508-A207-35A7906DC73D}"))
	unknown_iid = bytes(guid("{00000000-0000-0000-C000-000000000046}"))
	done = threading.Event()
	lock = threading.RLock()
	result = []
	errors = []
	initialized = registered = False
	sink = None
	refs = 1
	QI = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
	REF = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
	REPORT = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.c_void_p)
	STATUS = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.c_int)
	@REF
	def add_ref(this):
		nonlocal refs
		with _SINK_LOCK:
			refs += 1
			return refs
	@REF
	def release_ref(this):
		nonlocal refs
		with _SINK_LOCK:
			refs -= 1
			if refs == 0:
				_LIVE_SINKS.pop(this, None)
			return refs
	@QI
	def query_interface(this, iid, out):
		if not out:
			return -2147467261  # E_POINTER
		out[0] = None
		if iid and bytes(iid.contents) in (event_iid, unknown_iid):
			out[0] = this
			add_ref(this)
			return 0
		return -2147467262  # E_NOINTERFACE
	@REPORT
	def on_report(this, iid, report):
		with lock:
			if done.is_set() or not iid or bytes(iid.contents) != bytes(report_iid):
				return 0
			try:
				if not report:
					raise LocationDetectionError(LocationDetectionFailure.API_ERROR, "Null report")
				result.append(read_report(ctypes.c_void_p(report)))
				diagnostics["report_received"] = True
			except Exception as error:
				errors.append(error)
			done.set()
		return 0
	@STATUS
	def on_status(this, iid, status):
		with lock:
			if iid and bytes(iid.contents) == bytes(report_iid):
				diagnostics["report_status"] = status
				if status == 2:
					done.set()
		return 0
	callbacks = (query_interface, add_ref, release_ref, on_report, on_status)
	table = (ctypes.c_void_p * 5)(*(ctypes.cast(callback, ctypes.c_void_p).value for callback in callbacks))
	class Sink(ctypes.Structure):
		_fields_ = (("vtable", ctypes.POINTER(ctypes.c_void_p)),)
	sink = Sink(table)
	sink_address = ctypes.addressof(sink)
	with _SINK_LOCK:
		_LIVE_SINKS[sink_address] = (sink, table, callbacks)
	try:
		# MTA dispatches callbacks on COM threads; Event.wait releases the GIL.
		checked(ole32.CoInitializeEx(None, 0), "CoInitializeEx")
		initialized = True
		checked(ole32.CoCreateInstance(ctypes.byref(guid(_CLSID_LOCATION)), None, 1,
			ctypes.byref(guid(_IID_ILOCATION)), ctypes.byref(location)), "CoCreateInstance")
		request_permissions = method(location, 11, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.ULONG, wintypes.BOOL)
		checked(request_permissions(location, parent_window_handle, ctypes.byref(report_iid), 1, False), "RequestPermissions")
		register_for_report = method(location, 3, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD)
		checked(register_for_report(location, sink_address, ctypes.byref(report_iid), 0), "RegisterForReport")
		registered = True
		done.wait(max(0.0, timeout_seconds - (time.monotonic() - started)))
		with lock:
			if errors:
				raise errors[0]
			if result:
				return result[0]
		status = ctypes.c_int()
		get_report_status = method(location, 6, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_int))
		checked(get_report_status(location, ctypes.byref(report_iid), ctypes.byref(status)), "GetReportStatus")
		diagnostics["report_status"] = status.value
		raise LocationDetectionError(_status_failure(status.value), f"No location report; status={status.value}")
	except LocationDetectionError as error:
		diagnostics["failure"] = error.failure.value
		raise
	finally:
		done.set()
		try:
			if registered:
				hr = method(location, 4, ctypes.POINTER(GUID))(location, ctypes.byref(report_iid))
				diagnostics["UnregisterForReport"] = f"0x{hr & 0xFFFFFFFF:08X}"
		finally:
			try:
				release(location)
			finally:
				release_ref(sink_address)
				if initialized:
					ole32.CoUninitialize()
			diagnostics["elapsed_seconds"] = round(time.monotonic() - started, 3)
			logging.getLogger(__name__).debug("Windows Location diagnostics: %s", diagnostics)
