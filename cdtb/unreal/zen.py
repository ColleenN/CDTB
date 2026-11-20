"""Read the name tables of cooked (zen) Unreal packages

IoStore assets are "zen" packages. Their property values are stored
without names or types, but each package lists the names it uses, and the
packages it imports, in clear. That's enough to identify an asset and its
references without a mappings file.
"""
import struct

# summary layout written by the TFT client's engine version, before the name table
SUMMARY_SIZE = 60
IMPORTED_PACKAGE_NAMES_OFFSET = 48


def read_name_batch(data, pos):
    """Read a name batch: count, buffer size, hash version, hashes, lengths, then strings"""
    count, _ = struct.unpack_from('<II', data, pos)
    pos += 8 + 8 + 8 * count
    lengths = struct.unpack_from(f'>{count}h', data, pos)
    pos += 2 * count
    names = []
    for n in lengths:
        if n < 0:  # UTF-16
            n &= 0x7fff
            names.append(data[pos:pos + 2 * n].decode('utf-16-le'))
            pos += 2 * n
        else:
            names.append(data[pos:pos + n].decode('utf-8', 'replace'))
            pos += n
    return names


class ZenPackage:
    """Names and imported package paths of a zen package"""

    def __init__(self, data):
        has_versioning, = struct.unpack_from('<I', data, 0)
        pos = SUMMARY_SIZE
        if has_versioning:
            pos += 4 + 4 * 3  # zen version, UE4 and UE5 file versions, licensee version
            n, = struct.unpack_from('<i', data, pos)
            pos += 4 + 20 * n  # custom versions: GUID and version
        self.names = read_name_batch(data, pos)
        offset, = struct.unpack_from('<I', data, IMPORTED_PACKAGE_NAMES_OFFSET)
        self.imported_packages = read_name_batch(data, offset) if offset else []

    def names_with_prefix(self, prefix):
        return [n for n in self.names if n.startswith(prefix)]

    def identifier(self):
        """Return the `Identifier.<Kind>.<Name>` tag of the asset, or None"""
        ids = self.names_with_prefix("Identifier.")
        return ids[0] if ids else None
