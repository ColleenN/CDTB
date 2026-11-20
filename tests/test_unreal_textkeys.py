import json
import struct

from cdtb.__main__ import main
from cdtb.unreal.textkeys import find_text_references
from test_unreal_pak import build_pak, KEY
from test_unreal_locres import build_locres

FRONTMAN = "1F777F094AD4B14BB621D38CB4D91A86"
LOCKE = "3C0035CE4987E472505CB69897931AAB"


def fstring(s, utf16=False):
    if utf16:
        raw = s.encode('utf-16-le') + b'\0\0'
        return struct.pack('<i', -(len(raw) // 2)) + raw
    raw = s.encode() + b'\0'
    return struct.pack('<i', len(raw)) + raw


def ftext(namespace, key, source, utf16=False):
    # flags, history type 0 (base), then namespace, key and source strings
    return struct.pack('<I', 0) + b'\0' + fstring(namespace) + fstring(key) + fstring(source, utf16)


def test_find_text_references_from_real_layout():
    # bytes around the key in DA_Frontman19.uasset
    data = (bytes.fromhex("0003000000000001000000002100000031463737374630393441443442313442")
            + b"B621D38CB4D91A86\x00\x09\x00\x00\x00Frontman\x00\x00\x00\x00\x00\x01")
    refs = find_text_references(data, "DA_Frontman19.uasset")
    assert [(r.asset, r.namespace, r.key, r.source) for r in refs] == [("DA_Frontman19.uasset", "", FRONTMAN, "Frontman")]


def test_find_text_references_variants():
    data = (b"junk" + ftext("", FRONTMAN, "Frontman")
            + ftext("ST_Keybinds", LOCKE, "Locke ★", utf16=True)
            + ftext("", "0" * 32, "")
            + b"\x00" * 3)
    refs = find_text_references(data)
    assert [(r.namespace, r.key, r.source) for r in refs] == [
        ("", FRONTMAN, "Frontman"),
        ("ST_Keybinds", LOCKE, "Locke ★"),
        ("", "0" * 32, ""),
    ]


def test_find_text_references_ignores_other_ids():
    # 32-digit hex strings that aren't serialized text
    data = FRONTMAN.encode() + b"\x00" + b"xx" + fstring(LOCKE)[:-1] + b"Z" + fstring("source")
    data += b"\x21\x00\x00\x00" + LOCKE.encode() + b"\x00\xff\xff\xff\x7f"
    assert find_text_references(data) == []


def test_cli_ue_text_keys(tmp_path):
    pak = tmp_path / "test.pak"
    pak.write_bytes(build_pak({
        "TFT/Set_19/Traits/DA_Frontman19.uasset": (b"x" + ftext("", FRONTMAN, "Frontman"), False),
        "TFT/Set_19/Champions/DA_Locke19.uasset": (ftext("", LOCKE, "Locke"), True),
        "TFT/Set_19/notes.txt": (ftext("", "A" * 32, "skipped"), False),
    }, encrypted=True))
    locres = tmp_path / "Game.locres"
    locres.write_bytes(build_locres({"": {FRONTMAN: "Frontman (loc)"}}, 3))
    out = tmp_path / "keys.json"
    main(["ue-text-keys", "-k", KEY.hex(), "-l", str(locres), "-o", str(out), str(pak)])
    assert json.loads(out.read_text(encoding="utf-8")) == [
        {"asset": "TFT/Set_19/Champions/DA_Locke19.uasset", "namespace": "", "key": LOCKE, "source": "Locke", "text": None},
        {"asset": "TFT/Set_19/Traits/DA_Frontman19.uasset", "namespace": "", "key": FRONTMAN, "source": "Frontman", "text": "Frontman (loc)"},
    ]
