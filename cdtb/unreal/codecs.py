import ctypes
import os
import struct
import zlib
import gzip

import pyzstd
from Crypto.Cipher import AES

AES_BLOCK_SIZE = 16


def parse_aes_key(key):
    """Parse an AES-256 key given as hex, with or without a 0x prefix"""
    if isinstance(key, bytes):
        raw = key
    else:
        key = key.strip()
        if key[:2].lower() == "0x":
            key = key[2:]
        raw = bytes.fromhex(key)
    if len(raw) != 32:
        raise ValueError(f"AES key must be 32 bytes, got {len(raw)}")
    return raw


def aes_decrypt(data, key):
    """Decrypt data with AES-256-ECB, as Unreal does for pak and IoStore files"""
    if len(data) % AES_BLOCK_SIZE:
        raise ValueError("encrypted data must be a multiple of 16 bytes")
    return AES.new(key, AES.MODE_ECB).decrypt(data)


def align(n, alignment=AES_BLOCK_SIZE):
    return (n + alignment - 1) // alignment * alignment


def read_fstring(buf, pos):
    """Read an Unreal FString; return (value, new_pos)

    A negative length means UTF-16 characters, a positive one 8-bit characters.
    """
    n, = struct.unpack_from('<i', buf, pos)
    pos += 4
    if n == 0:
        return "", pos
    if n < 0:
        raw = buf[pos:pos - 2 * n]
        return raw.decode('utf-16-le').rstrip('\0'), pos - 2 * n
    raw = buf[pos:pos + n]
    return raw.decode('utf-8', 'replace').rstrip('\0'), pos + n


class OodleNotAvailable(RuntimeError):
    pass


class Oodle:
    """Oodle decompression through a shared library

    Unreal compresses with Oodle, which has no Python implementation. Point
    `CDTB_OODLE_LIB` (or `path`) at either Epic's oo2core library or an
    open-source build of ooz (https://github.com/zao/ooz); both export a
    decompression function with the same signature.
    """

    # ooz writes up to this many bytes past the end of its output
    SAFE_SPACE = 64

    _instance = None

    def __init__(self, path=None):
        path = path or os.environ.get("CDTB_OODLE_LIB")
        if not path:
            raise OodleNotAvailable("Oodle library not configured; set CDTB_OODLE_LIB")
        lib = ctypes.CDLL(path)
        for name in ("OodleLZ_Decompress", "Ooz_Decompress"):
            fn = getattr(lib, name, None)
            if fn is not None:
                break
        else:
            raise OodleNotAvailable(f"no Oodle decompression function in {path}")
        fn.argtypes = [ctypes.c_char_p, ctypes.c_int64, ctypes.c_char_p, ctypes.c_size_t,
                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        fn.restype = ctypes.c_int64
        self._fn = fn

    @classmethod
    def default(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def decompress(self, data, size):
        out = ctypes.create_string_buffer(size + self.SAFE_SPACE)
        n = self._fn(data, len(data), out, size, 0, 0, 0, None, 0, None, None, None, 0, 0)
        if n != size:
            raise ValueError(f"Oodle decompressed {n} bytes, expected {size}")
        return out.raw[:size]


def decompress(method, data, size):
    """Decompress one block with an Unreal compression method name"""
    method = method.lower()
    if method == "none":
        return data[:size]
    if method == "oodle":
        return Oodle.default().decompress(data, size)
    if method == "zlib":
        return zlib.decompress(data)
    if method == "gzip":
        return gzip.decompress(data)
    if method == "zstd":
        return pyzstd.decompress(data)
    raise ValueError(f"unsupported compression method: {method}")
