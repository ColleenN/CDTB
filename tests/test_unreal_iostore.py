import struct
import zlib

import pytest
from Crypto.Cipher import AES

from cdtb.unreal.codecs import align
from cdtb.unreal.iostore import IoStoreReader, TOC_MAGIC, INVALID

KEY = bytes(range(32))
BLOCK_SIZE = 64


def fstring(s):
    raw = s.encode() + b'\0'
    return struct.pack('<i', len(raw)) + raw


def encrypt(data):
    data = data + b'\0' * (align(len(data)) - len(data))
    return AES.new(KEY, AES.MODE_ECB).encrypt(data)


def build_directory_index(paths, mount_point="../../../"):
    """Build the directory tree; `paths` maps file path to TOC index"""
    tree = {}
    for path, toc_index in paths.items():
        *parts, filename = path.split('/')
        node = tree
        for p in parts:
            node = node.setdefault(p, {})
        node.setdefault(None, []).append((filename, toc_index))

    strings, dirs, files = [], [], []

    def string(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    def add_dir(name, node):
        index = len(dirs)
        dirs.append([INVALID if name is None else string(name), INVALID, INVALID, INVALID])
        prev = None
        for filename, toc_index in node.get(None, []):
            files.append([string(filename), INVALID, toc_index])
            if prev is None:
                dirs[index][3] = len(files) - 1
            else:
                files[prev][1] = len(files) - 1
            prev = len(files) - 1
        prev = None
        for child_name, child in node.items():
            if child_name is None:
                continue
            child_index = add_dir(child_name, child)
            if prev is None:
                dirs[index][1] = child_index
            else:
                dirs[prev][2] = child_index
            prev = child_index
        return index

    add_dir(None, tree)
    out = fstring(mount_point)
    out += struct.pack('<i', len(dirs)) + b''.join(struct.pack('<4I', *d) for d in dirs)
    out += struct.pack('<i', len(files)) + b''.join(struct.pack('<3I', *f) for f in files)
    out += struct.pack('<i', len(strings)) + b''.join(fstring(s) for s in strings)
    return out


def build_container(tmp_path, files, *, encrypted, compress=True, mount_point="../../../"):
    """Write test.utoc and test.ucas; `files` maps path to content"""
    chunk_ids, offsets, blocks = b'', b'', b''
    cas = bytearray()
    position = 0  # in uncompressed container data
    paths = {}
    for toc_index, (path, content) in enumerate(files.items()):
        paths[path] = toc_index
        chunk_ids += struct.pack('<QHBB', 1000 + toc_index, 0, 0, 2)
        offsets += position.to_bytes(5, 'big') + len(content).to_bytes(5, 'big')
        for i in range(0, len(content), BLOCK_SIZE):
            piece = content[i:i + BLOCK_SIZE]
            data = zlib.compress(piece) if compress else piece
            stored = encrypt(data) if encrypted else data
            blocks += len(cas).to_bytes(5, 'little') + len(data).to_bytes(3, 'little')
            blocks += len(piece).to_bytes(3, 'little') + bytes([1 if compress else 0])
            cas += stored
        # chunks start on a block boundary
        position += align(len(content), BLOCK_SIZE)
        while len(blocks) // 12 < position // BLOCK_SIZE:
            blocks += len(cas).to_bytes(5, 'little') + b'\0' * 7

    dir_index = build_directory_index(paths, mount_point)
    if encrypted:
        dir_index = encrypt(dir_index)
    flags = 1 | 8 | (2 if encrypted else 0)
    header = TOC_MAGIC + bytes([8, 0, 0, 0])
    header += struct.pack('<9I', 144, len(files), len(blocks) // 12, 12, 1, 32, BLOCK_SIZE, len(dir_index), 1)
    header += struct.pack('<Q', 42) + b'\0' * 16 + bytes([flags, 0, 0, 0])
    header += struct.pack('<IQI', 0, 2**64 - 1, 0)
    header = header.ljust(144, b'\0')
    toc = header + chunk_ids + offsets + blocks + b'Zlib'.ljust(32, b'\0') + dir_index
    (tmp_path / "test.utoc").write_bytes(toc)
    (tmp_path / "test.ucas").write_bytes(bytes(cas))
    return tmp_path / "test.utoc"


FILES = {
    "TFT/Content/a.uasset": bytes(range(200)),
    "TFT/Content/Sub/b.ubulk": b"bulk data" * 30,
    "TFT/Plugins/c.uasset": b"small",
    "Engine/d.bin": bytes(range(256)) * 3,
}


@pytest.mark.parametrize("encrypted", [False, True])
@pytest.mark.parametrize("compress", [False, True])
def test_iostore_list_and_read(tmp_path, encrypted, compress):
    reader = IoStoreReader(build_container(tmp_path, FILES, encrypted=encrypted, compress=compress),
                           aes_key=KEY if encrypted else None)
    assert reader.mount_point == "../../../"
    assert reader.encrypted == encrypted
    assert sorted(e.path for e in reader.entries) == sorted(FILES)
    for entry in reader.entries:
        assert reader.read(entry) == FILES[entry.path]


def test_iostore_paths_include_mount_point(tmp_path):
    # plugin containers mount below the game root
    utoc = build_container(tmp_path, {"UI_19/Content/a.uasset": b"x"}, encrypted=False,
                           mount_point="../../../TFT/Plugins/GameFeatures/")
    reader = IoStoreReader(utoc)
    assert [e.path for e in reader.entries] == ["TFT/Plugins/GameFeatures/UI_19/Content/a.uasset"]


def test_iostore_chunk_ids(tmp_path):
    reader = IoStoreReader(build_container(tmp_path, FILES, encrypted=False))
    assert reader.chunk_id(2) == (1002, 0, 2)


def test_iostore_encrypted_requires_key(tmp_path):
    with pytest.raises(ValueError, match="AES key"):
        IoStoreReader(build_container(tmp_path, FILES, encrypted=True))


def test_iostore_extract_with_pattern(tmp_path):
    reader = IoStoreReader(build_container(tmp_path, FILES, encrypted=False))
    reader.extract(tmp_path / "out", reader.find("TFT/Content/*"))
    assert (tmp_path / "out" / "TFT" / "Content" / "Sub" / "b.ubulk").read_bytes() == FILES["TFT/Content/Sub/b.ubulk"]
    assert not (tmp_path / "out" / "Engine").exists()
