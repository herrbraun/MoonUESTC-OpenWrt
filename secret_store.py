"""Current-user Windows DPAPI; no added crypto package or stored encryption key."""
import base64
import ctypes
from ctypes import wintypes
import json
import os

PREFIX = "dpapi:v1:"
FIELDS = ("password", "browser_fingerprint")


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def transform(value, decrypt=False):
    if os.name != "nt":
        raise OSError("This branch requires Windows DPAPI")
    buffer = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise OSError("Windows credential protection failed for the current user")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(outgoing.data)


def protect_account(account):
    result = dict(account)
    for field in FIELDS:
        if result.get(field):
            result[field] = PREFIX + base64.b64encode(transform(result[field].encode("utf-8"))).decode("ascii")
    return result


def read_account(path):
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(result, dict):
        for field in FIELDS:
            value = result.get(field)
            if isinstance(value, str) and value.startswith(PREFIX):
                result[field] = transform(base64.b64decode(value[len(PREFIX):], validate=True), True).decode("utf-8")
    return result
