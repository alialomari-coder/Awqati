"""Explicit one-shot adapter for the Windows desktop Location COM API."""

from __future__ import annotations

from collections.abc import Callable
import math
import os
import time

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
		)


def _read_windows_location(parent_window_handle: int, timeout_seconds: float, poll_interval_seconds: float) -> tuple[float, float]:
	"""Use LocationAPI.dll directly so the NVDA package needs no added runtime."""
	import ctypes
	from ctypes import wintypes

	class GUID(ctypes.Structure):
		_fields_ = (
			("Data1", wintypes.DWORD),
			("Data2", wintypes.WORD),
			("Data3", wintypes.WORD),
			("Data4", ctypes.c_ubyte * 8),
		)

	def guid(value: str) -> GUID:
		result = GUID()
		hresult = ole32.CLSIDFromString(value, ctypes.byref(result))
		if hresult < 0:
			raise OSError(f"Invalid COM GUID: 0x{hresult & 0xFFFFFFFF:08X}")
		return result

	def com_method(pointer: ctypes.c_void_p, index: int, argument_types: tuple[object, ...]):
		vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
		return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argument_types)(vtable[index])

	def release(pointer: ctypes.c_void_p) -> None:
		if pointer.value:
			com_method(pointer, 2, ())(pointer)
			pointer.value = None

	def failed(hresult: int) -> bool:
		return hresult < 0

	def hex_hresult(hresult: int) -> int:
		return hresult & 0xFFFFFFFF

	E_ACCESSDENIED = 0x80070005
	ERROR_CANCELLED = 0x800704C7
	ERROR_NO_DATA = 0x800700E8
	E_FAIL = 0x80004005
	RPC_E_CHANGED_MODE = 0x80010106
	COINIT_APARTMENTTHREADED = 0x2
	CLSCTX_INPROC_SERVER = 0x1

	ole32 = ctypes.OleDLL("ole32")
	ole32.CLSIDFromString.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(GUID))
	ole32.CLSIDFromString.restype = ctypes.c_long
	ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
	ole32.CoInitializeEx.restype = ctypes.c_long
	ole32.CoUninitialize.argtypes = ()
	ole32.CoCreateInstance.argtypes = (
		ctypes.POINTER(GUID),
		ctypes.c_void_p,
		wintypes.DWORD,
		ctypes.POINTER(GUID),
		ctypes.POINTER(ctypes.c_void_p),
	)
	ole32.CoCreateInstance.restype = ctypes.c_long

	initialized = False
	location = ctypes.c_void_p()
	report = ctypes.c_void_p()
	latlong = ctypes.c_void_p()
	try:
		hresult = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
		if failed(hresult) and hex_hresult(hresult) != RPC_E_CHANGED_MODE:
			raise LocationDetectionError(LocationDetectionFailure.API_ERROR, f"CoInitializeEx failed: 0x{hex_hresult(hresult):08X}")
		initialized = not failed(hresult)
		location_class = guid(_CLSID_LOCATION)
		location_interface = guid(_IID_ILOCATION)
		report_interface = guid(_IID_ILATLONG_REPORT)
		hresult = ole32.CoCreateInstance(
			ctypes.byref(location_class),
			None,
			CLSCTX_INPROC_SERVER,
			ctypes.byref(location_interface),
			ctypes.byref(location),
		)
		if failed(hresult):
			reason = LocationDetectionFailure.UNAVAILABLE if hex_hresult(hresult) in {E_FAIL, ERROR_NO_DATA} else LocationDetectionFailure.API_ERROR
			raise LocationDetectionError(reason, f"Windows Location activation failed: 0x{hex_hresult(hresult):08X}")

		request_permissions = com_method(
			location,
			11,
			(ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.ULONG, wintypes.BOOL),
		)
		hresult = request_permissions(
			location,
			ctypes.c_void_p(parent_window_handle),
			ctypes.byref(report_interface),
			1,
			True,
		)
		if failed(hresult):
			code = hex_hresult(hresult)
			reason = LocationDetectionFailure.DENIED if code in {E_ACCESSDENIED, ERROR_CANCELLED} else LocationDetectionFailure.UNAVAILABLE
			raise LocationDetectionError(reason, f"Windows Location permission failed: 0x{code:08X}")

		get_report = com_method(
			location,
			5,
			(ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)),
		)
		deadline = time.monotonic() + timeout_seconds
		while True:
			hresult = get_report(location, ctypes.byref(report_interface), ctypes.byref(report))
			if not failed(hresult):
				break
			code = hex_hresult(hresult)
			if code == E_ACCESSDENIED:
				raise LocationDetectionError(LocationDetectionFailure.DENIED, "Windows Location access was denied")
			if code not in {ERROR_NO_DATA, E_FAIL}:
				raise LocationDetectionError(LocationDetectionFailure.API_ERROR, f"GetReport failed: 0x{code:08X}")
			if time.monotonic() >= deadline:
				raise LocationDetectionError(LocationDetectionFailure.TIMEOUT, "Windows Location timed out")
			time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

		query_interface = com_method(
			report,
			0,
			(ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)),
		)
		hresult = query_interface(report, ctypes.byref(report_interface), ctypes.byref(latlong))
		if failed(hresult):
			raise LocationDetectionError(LocationDetectionFailure.API_ERROR, f"Latitude report unavailable: 0x{hex_hresult(hresult):08X}")
		latitude = ctypes.c_double()
		longitude = ctypes.c_double()
		hresult = com_method(latlong, 6, (ctypes.POINTER(ctypes.c_double),))(latlong, ctypes.byref(latitude))
		if failed(hresult):
			raise LocationDetectionError(LocationDetectionFailure.API_ERROR, f"GetLatitude failed: 0x{hex_hresult(hresult):08X}")
		hresult = com_method(latlong, 7, (ctypes.POINTER(ctypes.c_double),))(latlong, ctypes.byref(longitude))
		if failed(hresult):
			raise LocationDetectionError(LocationDetectionFailure.API_ERROR, f"GetLongitude failed: 0x{hex_hresult(hresult):08X}")
		if not math.isfinite(latitude.value) or not math.isfinite(longitude.value):
			raise LocationDetectionError(LocationDetectionFailure.INVALID_COORDINATES, "Windows returned non-finite coordinates")
		return latitude.value, longitude.value
	finally:
		release(latlong)
		release(report)
		release(location)
		if initialized:
			ole32.CoUninitialize()
