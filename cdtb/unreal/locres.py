import struct

from .codecs import read_fstring

LOCRES_MAGIC = bytes.fromhex("0e14747567 4a03fc 4a15909d c3377f1b".replace(" ", ""))

# ELocResVersion
VERSION_LEGACY = 0
VERSION_COMPACT = 1  # strings stored once in an array, referenced by index
VERSION_OPTIMIZED_CRC32 = 2  # adds key hashes, string ref counts and an entry count
VERSION_OPTIMIZED_CITYHASH64_UTF16 = 3


class LocresFile:
    """An Unreal localization string table (.locres)

    The Unreal client's equivalent of an RST file. Strings are looked up by
    namespace and key; most gameplay text uses the empty namespace.

    `entries` maps namespace to a dict of key to localized string.
    """

    def __init__(self, path_or_data=None):
        self.version = None
        self.entries = {}
        if path_or_data is None:
            return
        if isinstance(path_or_data, (bytes, bytearray)):
            data = bytes(path_or_data)
        else:
            with open(path_or_data, 'rb') as f:
                data = f.read()
        self.parse(data)

    def parse(self, data):
        if data[:16] == LOCRES_MAGIC:
            self.version = data[16]
            pos = 17
        else:
            self.version = VERSION_LEGACY
            pos = 0
        if self.version > VERSION_OPTIMIZED_CITYHASH64_UTF16:
            raise ValueError(f"unsupported locres version {self.version}")

        strings = None
        if self.version >= VERSION_COMPACT:
            array_offset, = struct.unpack_from('<q', data, pos)
            pos += 8
            strings = self._parse_string_array(data, array_offset)
        if self.version >= VERSION_OPTIMIZED_CRC32:
            pos += 4  # total entry count

        namespace_count, = struct.unpack_from('<I', data, pos)
        pos += 4
        for _ in range(namespace_count):
            if self.version >= VERSION_OPTIMIZED_CRC32:
                pos += 4  # namespace hash
            namespace, pos = read_fstring(data, pos)
            key_count, = struct.unpack_from('<I', data, pos)
            pos += 4
            table = self.entries.setdefault(namespace, {})
            for _ in range(key_count):
                if self.version >= VERSION_OPTIMIZED_CRC32:
                    pos += 4  # key hash
                key, pos = read_fstring(data, pos)
                pos += 4  # source string hash
                if strings is not None:
                    index, = struct.unpack_from('<i', data, pos)
                    pos += 4
                    table[key] = strings[index]
                else:
                    table[key], pos = read_fstring(data, pos)

    def _parse_string_array(self, data, pos):
        count, = struct.unpack_from('<I', data, pos)
        pos += 4
        strings = []
        for _ in range(count):
            s, pos = read_fstring(data, pos)
            if self.version >= VERSION_OPTIMIZED_CRC32:
                pos += 4  # ref count
            strings.append(s)
        return strings

    def __len__(self):
        return sum(len(t) for t in self.entries.values())

    def get(self, key, namespace="", default=None):
        return self.entries.get(namespace, {}).get(key, default)

    def update(self, other):
        """Merge another table in, e.g. the base table and its loc chunks"""
        for namespace, table in other.entries.items():
            self.entries.setdefault(namespace, {}).update(table)
