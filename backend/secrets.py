"""DPAPI, scoped to the current Windows user. Atomic writes, no key logging."""

import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
from tempfile import NamedTemporaryFile


class Blob(c.Structure):
    _fields_ = [("count", w.DWORD), ("ptr", c.POINTER(c.c_ubyte))]


class Vault:
    def __init__(self, root):
        self.root = Path(root)

    def file(self, service):
        if service not in ("faceit", "ai"):
            raise ValueError("Неизвестный сервис")
        return self.root / (service + ".dpapi")

    @staticmethod
    def crypt(data, decrypt):
        buffer = c.create_string_buffer(data)
        source = Blob(len(data), c.cast(buffer, c.POINTER(c.c_ubyte)))
        out = Blob()
        fn = (
            c.windll.crypt32.CryptUnprotectData
            if decrypt
            else c.windll.crypt32.CryptProtectData
        )
        if not fn(c.byref(source), None, None, None, None, 1, c.byref(out)):
            raise OSError("Windows DPAPI не смог обработать ключ")
        try:
            return c.string_at(out.ptr, out.count)
        finally:
            c.windll.kernel32.LocalFree(c.cast(out.ptr, c.c_void_p))

    def save(self, service, key):
        path = self.file(service)
        if not key:
            path.unlink(missing_ok=True)
            return
        encrypted = self.crypt(key.encode(), False)
        with NamedTemporaryFile(dir=self.root, delete=False) as tmp:
            tmp.write(encrypted)
        Path(tmp.name).replace(path)

    def read(self, service):
        path = self.file(service)
        return self.crypt(path.read_bytes(), True).decode() if path.exists() else ""
