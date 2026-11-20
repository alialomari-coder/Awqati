"""Read native MSAA name and role of a test-owned HWND, without NVDA injection."""
import ctypes as C
from ctypes import wintypes as W
import uuid


class Guid(C.Structure):
    _fields_ = [('data1', C.c_uint32), ('data2', C.c_uint16), ('data3', C.c_uint16), ('data4', C.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


NAME_PROPERTY = Guid.parse('608d3df8-8128-4aa7-a428-f55e49267291')


class NativePropertyServices:
    """Independent test instance of the documented Windows annotation service."""
    def __init__(self):
        ole = C.OleDLL('ole32')
        ole.CoInitialize(None)
        cls = Guid.parse('b5f8350b-0548-48b1-a6ee-88bd00b4a5e7')
        iid = Guid.parse('6e26e776-04f0-495d-80e4-3330352e3169')
        self.pointer = C.c_void_p()
        ole.CoCreateInstance.argtypes = [C.POINTER(Guid), C.c_void_p, W.DWORD, C.POINTER(Guid), C.POINTER(C.c_void_p)]
        result = ole.CoCreateInstance(C.byref(cls), None, 1, C.byref(iid), C.byref(self.pointer))
        if result < 0:
            raise OSError('CoCreateInstance failed', result)
        self.vtable = C.cast(self.pointer, C.POINTER(C.POINTER(C.c_void_p))).contents

    def SetHwndPropStr(self, hwnd, object_id, child_id, prop, text):
        call = C.WINFUNCTYPE(C.c_long, C.c_void_p, W.HWND, W.DWORD, W.DWORD, Guid, W.LPCWSTR)(self.vtable[7])
        if call(self.pointer, hwnd, object_id, child_id, prop, text) < 0:
            raise OSError('SetHwndPropStr failed')

    def ClearHwndProps(self, hwnd, object_id, child_id, props, count):
        call = C.WINFUNCTYPE(C.c_long, C.c_void_p, W.HWND, W.DWORD, W.DWORD, C.POINTER(Guid), C.c_int)(self.vtable[9])
        if call(self.pointer, hwnd, object_id, child_id, props, count) < 0:
            raise OSError('ClearHwndProps failed')

    def close(self):
        if self.pointer:
            C.WINFUNCTYPE(C.c_ulong, C.c_void_p)(self.vtable[2])(self.pointer)
            self.pointer = None
            uninitialize = C.OleDLL('ole32').CoUninitialize
            uninitialize.restype = None
            uninitialize()


class VariantData(C.Union):
    _fields_ = [('integer', C.c_long), ('pointers', C.c_void_p * 2)]


class Variant(C.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('vt', C.c_ushort), ('reserved', C.c_ushort * 3), ('data', VariantData)]


def native_list_properties(hwnd, child_id=0):
    oleacc, oleaut = C.OleDLL('oleacc'), C.OleDLL('oleaut32')
    iid = (C.c_ubyte * 16).from_buffer_copy(uuid.UUID('618736e0-3c3d-11cf-810c-00aa00389b71').bytes_le)
    pointer = C.c_void_p()
    get = oleacc.AccessibleObjectFromWindow
    get.argtypes = [W.HWND, W.DWORD, C.c_void_p, C.POINTER(C.c_void_p)]
    get.restype = C.c_long
    result = get(hwnd, 0xfffffffc, C.byref(iid), C.byref(pointer))
    if result < 0 or not pointer:
        raise OSError('AccessibleObjectFromWindow failed', result)
    vtable = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    child = Variant(); child.vt = 3; child.integer = child_id
    bstr = C.c_void_p()
    role = Variant()
    try:
        name_get = C.WINFUNCTYPE(C.c_long, C.c_void_p, Variant, C.POINTER(C.c_void_p))(vtable[10])
        role_get = C.WINFUNCTYPE(C.c_long, C.c_void_p, Variant, C.POINTER(Variant))(vtable[13])
        if name_get(pointer, child, C.byref(bstr)) < 0:
            raise OSError('get_accName failed')
        if role_get(pointer, child, C.byref(role)) < 0 or role.vt != 3:
            raise OSError('get_accRole failed')
        return {'name': C.wstring_at(bstr) if bstr else '', 'role': role.integer}
    finally:
        if bstr:
            oleaut.SysFreeString.argtypes = [C.c_void_p]
            oleaut.SysFreeString.restype = None
            oleaut.SysFreeString(bstr)
        C.WINFUNCTYPE(C.c_ulong, C.c_void_p)(vtable[2])(pointer)
