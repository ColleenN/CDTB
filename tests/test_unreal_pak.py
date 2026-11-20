import struct
import zlib

import pytest
from Crypto.Cipher import AES

from cdtb.unreal.codecs import parse_aes_key, read_fstring, align
from cdtb.unreal.pak import PakFile, PAK_MAGIC, ENTRY_HEADER_SIZE

KEY = bytes(range(32))


def fstring(s):
    raw = s.encode() + b'\0'
    return struct.pack('<i', len(raw)) + raw


def encrypt(data):
    data = data + b'\0' * (align(len(data)) - len(data))
    return AES.new(KEY, AES.MODE_ECB).encrypt(data)


def build_pak(files, *, encrypted, block_size=2048, version=11):
    """Build a pak in the same layout Unreal writes: data, index, directory index, footer

    `files` maps path to (content, compress).
    """
    data = bytearray()
    encoded = bytearray()
    directories = {}
    for path, (content, compress) in files.items():
        if compress:
            chunks = [zlib.compress(content[i:i + block_size]) for i in range(0, len(content), block_size)]
        else:
            chunks = []
        method = 1 if compress else 0
        struct_size = ENTRY_HEADER_SIZE + 1 + 4 + (4 + 16 * len(chunks) if compress else 0)
        offset = len(data)
        data += b'\0' * struct_size
        if compress:
            for c in chunks:
                data += encrypt(c) if encrypted else c
            size = sum(len(c) for c in chunks)
        else:
            data += encrypt(content) if encrypted else content
            size = len(content)
        value = (1 << 31) | (1 << 30) | (1 << 29)
        value |= (block_size >> 11) & 0x3f
        value |= (len(chunks) & 0xffff) << 6
        value |= int(encrypted) << 22
        value |= method << 23
        location = len(encoded)
        encoded += struct.pack('<I', value) + struct.pack('<II', offset, len(content))
        if method:
            encoded += struct.pack('<I', size)
        if len(chunks) > 1 or (encrypted and chunks):
            for c in chunks:
                encoded += struct.pack('<I', len(c))
        dirname, _, filename = path.rpartition('/')
        directories.setdefault(dirname + '/', []).append((filename, location))

    dir_index = struct.pack('<i', len(directories))
    for dirname, entries in directories.items():
        dir_index += fstring(dirname) + struct.pack('<i', len(entries))
        for filename, location in entries:
            dir_index += fstring(filename) + struct.pack('<i', location)
    dir_index = encrypt(dir_index) if encrypted else dir_index
    dir_offset = len(data)
    data += dir_index

    index = fstring("../../../") + struct.pack('<iQ', len(files), 0)
    index += struct.pack('<I', 0)  # no path hash index
    index += struct.pack('<IQQ', 1, dir_offset, len(dir_index)) + b'\0' * 20
    index += struct.pack('<i', len(encoded)) + bytes(encoded)
    index += struct.pack('<i', 0)
    index = encrypt(index) if encrypted else index
    index_offset = len(data)
    data += index

    footer = b'\0' * 16 + bytes([int(encrypted)])
    footer += struct.pack('<IiQQ', PAK_MAGIC, version, index_offset, len(index)) + b'\0' * 20
    footer += b'Zlib'.ljust(32, b'\0') + b'\0' * 4 * 32
    return bytes(data + footer)


CONTENT = bytes(range(256)) * 20  # 5120 bytes: three 2048-byte blocks


@pytest.mark.parametrize("encrypted", [False, True])
def test_pak_list_and_read(tmp_path, encrypted):
    path = tmp_path / "test.pak"
    path.write_bytes(build_pak({
        "TFT/Content/a.bin": (CONTENT, True),
        "TFT/Content/Sub/b.txt": (b"hello pak", False),
        "TFT/c.bin": (CONTENT[:1000], True),
    }, encrypted=encrypted))
    pak = PakFile(path, aes_key=KEY if encrypted else None)
    assert pak.mount_point == "../../../"
    assert sorted(e.path for e in pak.entries) == ["TFT/Content/Sub/b.txt", "TFT/Content/a.bin", "TFT/c.bin"]
    by_path = {e.path: e for e in pak.entries}
    assert by_path["TFT/Content/a.bin"].method == "Zlib"
    assert len(by_path["TFT/Content/a.bin"].blocks) == 3
    assert pak.read(by_path["TFT/Content/a.bin"]) == CONTENT
    assert pak.read(by_path["TFT/Content/Sub/b.txt"]) == b"hello pak"
    assert pak.read(by_path["TFT/c.bin"]) == CONTENT[:1000]


def test_pak_encrypted_requires_key(tmp_path):
    path = tmp_path / "test.pak"
    path.write_bytes(build_pak({"a/b.txt": (b"x", False)}, encrypted=True))
    with pytest.raises(ValueError, match="AES key"):
        PakFile(path)


def test_pak_extract_with_pattern(tmp_path):
    path = tmp_path / "test.pak"
    path.write_bytes(build_pak({"a/one.txt": (b"1", False), "b/two.txt": (b"2", False)}, encrypted=False))
    pak = PakFile(path)
    pak.extract(tmp_path / "out", pak.find("b/*"))
    assert (tmp_path / "out" / "b" / "two.txt").read_bytes() == b"2"
    assert not (tmp_path / "out" / "a").exists()


def test_parse_aes_key():
    assert parse_aes_key("0x" + KEY.hex().upper()) == KEY
    assert parse_aes_key(KEY.hex()) == KEY
    with pytest.raises(ValueError):
        parse_aes_key("00ff")


def test_read_fstring_utf16():
    raw = "Héllo".encode('utf-16-le') + b'\0\0'
    buf = struct.pack('<i', -(len(raw) // 2)) + raw
    assert read_fstring(buf, 0) == ("Héllo", len(buf))
