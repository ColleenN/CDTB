import json

import pytest

from cdtb.__main__ import main
from test_unreal_pak import build_pak, KEY, CONTENT
from test_unreal_iostore import build_container, FILES
from test_unreal_locres import build_locres


@pytest.fixture
def pak(tmp_path):
    path = tmp_path / "test.pak"
    path.write_bytes(build_pak({
        "TFT/Content/a.bin": (CONTENT, True),
        "TFT/Content/Sub/b.txt": (b"hello pak", False),
        "TFT/empty.txt": (b"", False),
    }, encrypted=True))
    return path


def test_ue_list_pak(pak, capsys):
    main(["ue-list", "-k", KEY.hex(), str(pak)])
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[-1] for line in lines] == ["TFT/Content/Sub/b.txt", "TFT/Content/a.bin", "TFT/empty.txt"]
    assert lines[1].split()[0] == str(len(CONTENT))


def test_ue_list_key_from_env(pak, capsys, monkeypatch):
    monkeypatch.setenv("CDTB_AES_KEY", "0x" + KEY.hex())
    main(["ue-list", "-p", "*.txt", str(pak)])
    assert len(capsys.readouterr().out.splitlines()) == 2


def test_ue_extract_iostore(tmp_path):
    utoc = build_container(tmp_path, FILES, encrypted=True)
    out = tmp_path / "out"
    main(["ue-extract", "-k", KEY.hex(), "-p", "TFT/*", "-o", str(out), str(utoc.with_suffix(".ucas"))])
    assert (out / "TFT" / "Content" / "a.uasset").read_bytes() == FILES["TFT/Content/a.uasset"]
    assert not (out / "Engine").exists()


def test_locres_dump_merges(tmp_path):
    base = tmp_path / "Game.locres"
    chunk = tmp_path / "Game_locchunk1.locres"
    base.write_bytes(build_locres({"": {"a": "A", "b": "old"}}, 3))
    chunk.write_bytes(build_locres({"": {"b": "B"}, "Store": {"buy": "Buy"}}, 3))
    out = tmp_path / "strings.json"
    main(["locres-dump", "-o", str(out), str(base), str(chunk)])
    assert json.loads(out.read_text(encoding="utf-8")) == {"": {"a": "A", "b": "B"}, "Store": {"buy": "Buy"}}
