"""Native MSAA names for wx controls whose Windows label overrides wx.Name."""
from ctypes import WinDLL, c_void_p, c_uint, c_size_t, c_ssize_t, byref
import IAccessibleHandler
import oleacc
import wx


def set_spin_name(control, name):
    """Annotate the spin and its native edit buddy; preserve role and value."""
    control.SetName(name)
    services = IAccessibleHandler.accPropServices
    if services is None:
        # Keep the unit audible if MSAA annotation is unavailable on a host.
        control.awqati_label.SetLabel(name + ":")
        return
    if not hasattr(control, "_awqati_name_handles"):
        hwnd = control.GetHandle()
        send = WinDLL("user32").SendMessageW
        send.argtypes = (c_void_p, c_uint, c_size_t, c_ssize_t)
        send.restype = c_ssize_t
        buddy = send(hwnd, 0x046A, 0, 0)  # UDM_GETBUDDY; native edit of wx.SpinCtrl.
        handles = tuple(dict.fromkeys(h for h in (hwnd, buddy) if h))
        control._awqati_name_handles = handles
        def clear(event):
            if event.GetEventObject() is control:
                for handle in handles:
                    services.ClearHwndProps(handle, 0xFFFFFFFC, 0, byref(oleacc.PROPID_ACC_NAME), 1)
            event.Skip()
        control.Bind(wx.EVT_WINDOW_DESTROY, clear)
    for hwnd in control._awqati_name_handles:
        services.SetHwndPropStr(hwnd, 0xFFFFFFFC, 0, oleacc.PROPID_ACC_NAME, name)
