import struct

import pytest

from cdtb.unreal.locres import LocresFile, LOCRES_MAGIC

ENTRIES = {
    "": {"1F777F094AD4B14BB621D38CB4D91A86": "Frontman", "AB": "Héllo ★"},
    "Store": {"buy": "Buy", "again": "Frontman"},
}


def fstring(s):
    try:
        raw = s.encode('ascii') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    except UnicodeEncodeError:
        raw = s.encode('utf-16-le') + b'\0\0'
        return struct.pack('<i', -(len(raw) // 2)) + raw


def build_locres(entries, version):
    """Serialize `entries` the way Unreal writes a given locres version"""
    strings = []
    body = b''
    for namespace, table in entries.items():
        if version >= 2:
            body += struct.pack('<I', 0)
        body += fstring(namespace) + struct.pack('<I', len(table))
        for key, value in table.items():
            if version >= 2:
                body += struct.pack('<I', 0)
            body += fstring(key) + struct.pack('<I', 0)
            if version >= 1:
                if value not in strings:
                    strings.append(value)
                body += struct.pack('<i', strings.index(value))
            else:
                body += fstring(value)
    body = struct.pack('<I', len(entries)) + body
    if version == 0:
        return body
    header_size = 16 + 1 + 8 + (4 if version >= 2 else 0)
    header = LOCRES_MAGIC + bytes([version])
    header += struct.pack('<q', header_size + len(body))
    if version >= 2:
        header += struct.pack('<I', sum(len(t) for t in entries.values()))
    array = struct.pack('<I', len(strings))
    for s in strings:
        array += fstring(s) + (struct.pack('<i', 1) if version >= 2 else b'')
    return header + body + array


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_locres_versions(version):
    loc = LocresFile(build_locres(ENTRIES, version))
    assert loc.version == version
    assert loc.entries == ENTRIES
    assert len(loc) == 4
    assert loc.get("1F777F094AD4B14BB621D38CB4D91A86") == "Frontman"
    assert loc.get("buy", namespace="Store") == "Buy"
    assert loc.get("missing", default="?") == "?"


def test_locres_from_path_and_update(tmp_path):
    path = tmp_path / "Game.locres"
    path.write_bytes(build_locres({"": {"a": "A"}}, 3))
    base = LocresFile(str(path))
    base.update(LocresFile(build_locres({"": {"b": "B"}, "X": {"c": "C"}}, 3)))
    assert base.entries == {"": {"a": "A", "b": "B"}, "X": {"c": "C"}}


def test_locres_unsupported_version():
    with pytest.raises(ValueError, match="version"):
        LocresFile(LOCRES_MAGIC + bytes([9]) + b'\0' * 16)
