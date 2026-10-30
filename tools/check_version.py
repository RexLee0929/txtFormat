"""用 PE 版本资源 API 读 exe 的真实版本号（字符串搜索不可靠）。"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

ver = ctypes.WinDLL("version")


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD), ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD), ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD), ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD), ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD), ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD), ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def q(path: str):
    size = ver.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(path, 0, size, buf):
        return None
    ptr = ctypes.c_void_p()
    length = wintypes.UINT()
    if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
        return None
    if not ptr:
        return None
    info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    f = (info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
         info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF)
    p = (info.dwProductVersionMS >> 16, info.dwProductVersionMS & 0xFFFF,
         info.dwProductVersionLS >> 16, info.dwProductVersionLS & 0xFFFF)
    return ".".join(map(str, f)), ".".join(map(str, p))


for path in sys.argv[1:]:
    r = q(path)
    print(f"{path}  file={r[0] if r else '?'}  product={r[1] if r else '?'}")