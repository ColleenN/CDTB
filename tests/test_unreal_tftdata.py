import json
import struct

from cdtb.__main__ import main
from cdtb.unreal.tftdata import TftAsset, build_tft_data, latest_set, package_path, icon_path, read_stats
from cdtb.unreal.zen import ZenPackage
from test_unreal_pak import build_pak, KEY
from test_unreal_locres import build_locres
from test_unreal_textkeys import ftext, fstring

SET = "TFT/Plugins/GameFeatures/Set_19/Content"


def name_batch(names):
    raw = [n.encode() for n in names]
    out = struct.pack('<II', len(names), sum(map(len, raw))) + b'\0' * 8 + b'\0' * 8 * len(names)
    out += b''.join(struct.pack('>h', len(r)) for r in raw)
    return out + b''.join(raw)


def stat(name, value):
    return b'\x07' + fstring(name) + b'\x01\x00\x00\x00' + b'\0' * 8 + struct.pack('<iif', -25, -25, value)


def zen_asset(names, imports=(), body=b''):
    """A zen package: summary, name table, body, imported package names"""
    names_raw = name_batch(names)
    imports_offset = 60 + len(names_raw) + len(body)
    summary = bytearray(60)
    struct.pack_into('<I', summary, 48, imports_offset)
    return bytes(summary) + names_raw + body + name_batch(list(imports))


def locke():
    body = (ftext("", "A" * 32, "Locke") + ftext("", "B" * 32, "Soul Nail")
            + ftext("", "C" * 32, "Damage: <TFTAttribute/>") + ftext("", "D" * 32, "Attacks deal damage, then a lot more damage.")
            + stat("Armor", 65.0) + stat("AttackSpeed", 0.9) + stat("MagicResist", 65.0) + stat("ManaMax", 30.0)
            + b'\x07' + fstring("AttackDamage") + b'\x01\x00\x00\x00' + b'\0' * 8 + struct.pack('<ii', -25, -25) + b'\x80\x05\x03\x00')
    names = ["Identifier.Champion.Locke", "FourCost", "DA_Role_MagicAssassin", "Armor",
             "/Set_19/Champions/Locke/UI/T_19_Locke_PC", "/Set_19/Champions/Locke/UI/T_19_Locke_Mobile",
             "/Set_19/Champions/Locke/UI/T_19_Locke_TeamPlanner_Portrait", "/Set_19/Champions/Locke/Textures/T_Locke19_SpellIcon"]
    imports = ["/Set_19/Traits/Swiftstriker/Trait/DA_Swiftstriker19", "/Set_Shared/UnitLevelUp/CT_UnitCost"]
    return zen_asset(names, imports, body)


def swiftstriker():
    body = (ftext("", "E" * 32, "Swiftstrikers gain attack speed.") + ftext("", "F" * 32, "Swiftstriker")
            + ftext("", "1" * 32, "(2) <TFTCurveTable row=\"AS\"/>") + ftext("", "2" * 32, "(4) more")
            + ftext("", "3" * 32, "3) ???"))
    names = ["Identifier.Trait.Swiftstriker", "/Set_19/Traits/_TraitIcons/T_Swiftstriker19"]
    return zen_asset(names, [], body)


def emblem():
    body = ftext("", "4" * 32, "The holder gains the Swiftstriker trait.") + ftext("", "5" * 32, "Swiftstriker Emblem")
    names = ["Identifier.Item.SwiftstrikerEmblem", "Item.Equippable.Item.Emblem",
             "/Set_19/Traits/_TraitIcons/IconItem/T_Swiftstriker19_Emblem"]
    return zen_asset(names, ["/Set_19/Traits/Swiftstriker/Trait/DA_Swiftstriker19"], body)


def augment():
    body = ftext("", "6" * 32, "Allies that start combat isolated in pairs gain stats.")
    names = ["Identifier.Augment.StrangeDuet", "Augment.Tier.Gold"]
    return zen_asset(names, ["/Item_Shared/Item/Component_BFSword/DA_Component_BFSword"], body)


def component():
    body = ftext("", "7" * 32, "+10% Attack Damage") + ftext("", "8" * 32, "B.F. Sword")
    return zen_asset(["Identifier.Item.BFSword", "Item.Equippable.Item.Component"], [], body)


ASSETS = {
    f"{SET}/Champions/Locke/DA_Locke19.uasset": locke,
    f"{SET}/Traits/Swiftstriker/Trait/DA_Swiftstriker19.uasset": swiftstriker,
    f"{SET}/Traits/Swiftstriker/Emblem/DA_Swiftstriker19_Emblem.uasset": emblem,
    "TFT/Plugins/GameFeatures/Item_Shared/Content/Augment/StrangeDuet/DA_StrangeDuet.uasset": augment,
    "TFT/Plugins/GameFeatures/Item_Shared/Content/Item/Component_BFSword/DA_Component_BFSword.uasset": component,
}


def test_zen_package():
    zen = ZenPackage(emblem())
    assert zen.identifier() == "Identifier.Item.SwiftstrikerEmblem"
    assert zen.imported_packages == ["/Set_19/Traits/Swiftstriker/Trait/DA_Swiftstriker19"]


def test_paths():
    assert package_path(f"{SET}/Champions/Locke/DA_Locke19.uasset") == "/Set_19/Champions/Locke/DA_Locke19"
    assert package_path("TFT/Content/Foo/DA_X.uasset") == "/Game/Foo/DA_X"
    assert icon_path("/Set_19/Champions/Locke/UI/T_19_Locke_PC") == "tft/plugins/gamefeatures/set_19/content/champions/locke/ui/t_19_locke_pc.png"


def test_read_stats_skips_curve_values():
    assert read_stats(locke()) == {"Armor": 65.0, "AttackSpeed": 0.9, "MagicResist": 65.0, "ManaMax": 30.0}


def test_build_tft_data():
    assets = [TftAsset(path, build()) for path, build in ASSETS.items()]
    assert latest_set(assets) == 19
    data = build_tft_data(assets, 19)
    s = data["setData"][0]
    assert (s["number"], s["mutator"]) == (19, "TFTSet19")
    [champ] = s["champions"]
    assert champ["apiName"] == "DA_Locke19"
    assert (champ["name"], champ["characterName"], champ["cost"], champ["role"]) == ("Locke", "Locke", 4, "DA_Role_MagicAssassin")
    assert champ["traits"] == ["Swiftstriker"]
    assert champ["ability"]["name"] == "Soul Nail"
    assert champ["ability"]["desc"] == "Attacks deal damage, then a lot more damage."
    assert champ["ability"]["icon"].endswith("t_locke19_spellicon.png")
    assert champ["squareIcon"].endswith("t_19_locke_teamplanner_portrait.png")
    assert champ["stats"] == {"armor": 65.0, "attackSpeed": 0.9, "critChance": None, "critMultiplier": None,
                              "damage": None, "hp": None, "initialMana": 0, "magicResist": 65.0, "mana": 30.0, "range": 1}
    [trait] = s["traits"]
    assert trait["name"] == "Swiftstriker"
    assert [(e["minUnits"], e["maxUnits"]) for e in trait["effects"]] == [(2, 3), (4, 25)]
    assert "???" not in trait["desc"] and trait["desc"].startswith("Swiftstrikers gain")
    assert trait["icon"].endswith("t_swiftstriker19.png")
    items = {i["apiName"]: i for i in data["items"]}
    assert items["DA_Swiftstriker19_Emblem"]["associatedTraits"] == ["Swiftstriker"]
    assert items["DA_Swiftstriker19_Emblem"]["name"] == "Swiftstriker Emblem"
    assert items["DA_StrangeDuet"]["name"] == "StrangeDuet"
    assert items["DA_StrangeDuet"]["tags"] == ["Augment.Tier.Gold"]
    assert items["DA_StrangeDuet"]["composition"] == []
    assert items["DA_Component_BFSword"]["name"] == "B.F. Sword"


def test_cli_ue_tft_data(tmp_path):
    pak = tmp_path / "test.pak"
    pak.write_bytes(build_pak({path: (build(), True) for path, build in ASSETS.items()}, encrypted=True))
    locres = tmp_path / "Game.locres"
    locres.write_bytes(build_locres({"": {"A" * 32: "Locke (loc)"}}, 3))
    out = tmp_path / "tft.json"
    main(["ue-tft-data", "-k", KEY.hex(), "-l", str(locres), "-o", str(out), str(pak)])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["setData"][0]["champions"][0]["name"] == "Locke (loc)"
    assert list(data["sets"]) == ["19"]
    assert len(data["items"]) == 3
