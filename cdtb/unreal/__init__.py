"""Readers for Unreal Engine game files, used by the standalone TFT client.

These play the same role for the Unreal client as `wad`, `rstfile` and
`tftdata` do for the League client.
"""
import os


def open_container(path, aes_key=None):
    """Open a .pak or IoStore container (given its .utoc or .ucas file)"""
    from .pak import PakFile
    from .iostore import IoStoreReader
    base, ext = os.path.splitext(path)
    ext = ext.lower()
    if ext == ".pak":
        return PakFile(path, aes_key=aes_key)
    if ext in (".utoc", ".ucas"):
        return IoStoreReader(base + ".utoc", aes_key=aes_key)
    raise ValueError(f"not an Unreal container: {path}")
