"""Find which assets use which localized text

Gameplay text in the Unreal client is keyed by IDs like
`1F777F094AD4B14BB621D38CB4D91A86`, generated when the text is authored.
They aren't hashes, so the only way to know what an ID belongs to is to
find the asset that stores it. Assets serialize text as a namespace, the
key and the English source string, in clear, so they can be found without
parsing the asset format.

This is the first step towards the Unreal equivalent of `tftdata`: it
links the strings of a .locres table to unit, trait and item assets.
"""
import fnmatch
import logging
import re
import struct

logger = logging.getLogger(__name__)

# a 32-digit hex key, serialized as an FString: length 33, then the key and a null
KEY_PATTERN = re.compile(rb'\x21\x00\x00\x00([0-9A-F]{32})\x00')
MAX_NAMESPACE_LENGTH = 256


class TextReference:
    """A localized text stored in an asset"""

    def __init__(self, asset, namespace, key, source):
        self.asset = asset
        self.namespace = namespace
        self.key = key
        self.source = source

    def __repr__(self):
        return f"<TextReference {self.asset!r} {self.namespace!r}/{self.key} {self.source!r}>"

    def to_dict(self, table=None):
        """Return a dict; with a LocresFile, add its string as `text` (None if missing)"""
        d = {"asset": self.asset, "namespace": self.namespace, "key": self.key, "source": self.source}
        if table is not None:
            d["text"] = table.get(self.key, self.namespace)
        return d


def _read_namespace(data, end):
    """Read the FString that ends at `end`; return None if there isn't one"""
    # most text uses the empty namespace, serialized as an empty or null-only string
    if data[end - 5:end] == b'\x01\x00\x00\x00\x00':
        return ""
    if data[end - 4:end] == b'\x00\x00\x00\x00':
        return ""
    if end < 1 or data[end - 1] != 0:
        return None
    for n in range(2, min(MAX_NAMESPACE_LENGTH, end - 4) + 1):
        if struct.unpack_from('<i', data, end - n - 4)[0] == n:
            raw = data[end - n:end - 1]
            if all(32 <= c < 127 for c in raw):
                return raw.decode('ascii')
            return None
    return None


def _read_source(data, pos):
    """Read the FString at `pos`; return None if it doesn't look like one"""
    if pos + 4 > len(data):
        return None
    n, = struct.unpack_from('<i', data, pos)
    pos += 4
    if n == 0:
        return ""
    if n > 0:
        raw = data[pos:pos + n]
        if len(raw) != n or raw[-1] != 0:
            return None
        return raw[:-1].decode('utf-8', 'replace')
    raw = data[pos:pos - 2 * n]
    if len(raw) != -2 * n or raw[-2:] != b'\0\0':
        return None
    return raw[:-2].decode('utf-16-le', 'replace')


def find_text_references(data, asset=None):
    """Return the TextReference of each localized text serialized in `data`"""
    refs = []
    for m in KEY_PATTERN.finditer(data):
        namespace = _read_namespace(data, m.start())
        if namespace is None:
            continue
        source = _read_source(data, m.end())
        if source is None:
            continue
        refs.append(TextReference(asset, namespace, m.group(1).decode('ascii'), source))
    return refs


def index_containers(containers, patterns=("*.uasset",)):
    """Scan the assets of containers, return a list of TextReference

    `containers` are PakFile or IoStoreReader instances.
    """
    from .iostore import IoStoreReader
    refs = []
    for container in containers:
        entries = [e for e in container.entries if any(fnmatch.fnmatchcase(e.path, p) for p in patterns)]
        logger.info(f"scanning {len(entries)} assets of {container.path}")
        # keep files open across reads
        if isinstance(container, IoStoreReader):
            handles = {}
            files = handles.values
            read = lambda e: container.read(e, handles)  # noqa: E731
        else:
            f = open(container.path, 'rb')
            files = lambda: [f]  # noqa: E731
            read = lambda e: container.read(e, f)  # noqa: E731
        try:
            for entry in entries:
                refs.extend(find_text_references(read(entry), entry.path))
        finally:
            for handle in list(files()):
                handle.close()
    return refs
