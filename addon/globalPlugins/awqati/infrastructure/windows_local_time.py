"""Read Windows' configured local rules at the same instant as a world-clock query."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone


class SystemTime(ctypes.Structure):
    _fields_=[(name,wintypes.WORD) for name in ('year','month','weekday','day','hour','minute','second','millisecond')]


class WindowsLocalTimezone:
    def __init__(self):
        self.convert=ctypes.WinDLL('kernel32',use_last_error=True).SystemTimeToTzSpecificLocalTimeEx
        self.convert.argtypes=(ctypes.c_void_p,ctypes.POINTER(SystemTime),ctypes.POINTER(SystemTime))
        self.convert.restype=wintypes.BOOL

    def __call__(self, instant):
        value=instant.astimezone(timezone.utc).replace(microsecond=0)
        utc=SystemTime(value.year,value.month,0,value.day,value.hour,value.minute,value.second,0)
        local=SystemTime()
        # NULL means Windows' current dynamic zone, including system preferences.
        # Do not use the prayer location or a stale C-runtime timezone cache.
        if not self.convert(None,ctypes.byref(utc),ctypes.byref(local)):
            raise ctypes.WinError(ctypes.get_last_error())
        wall=datetime(local.year,local.month,local.day,local.hour,local.minute,local.second)
        return timezone(wall-value.replace(tzinfo=None))
