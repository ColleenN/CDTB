"""Build TFT data in the shape of CDragon's old `cdragon/tft/<lang>.json`

A stopgap equivalent of `cdtb.tftdata` for the Unreal client. It reads the
champion, trait, item and augment data assets (`DA_*.uasset`) and fills in
what can be read without a mappings file: names, descriptions, costs,
roles, traits, item tags and recipes, icons, and the stats stored as
name/value pairs. Values that come from curve tables (attack damage,
some health values, ability and trait numbers) are left as None.

Cooked assets omit fields that hold their default value, so a champion
with no starting mana or attack range stored gets 0 and 1 (melee).
"""
import fnmatch
import logging
import re
import struct

from .iostore import IoStoreReader
from .textkeys import find_text_references
from .zen import ZenPackage

logger = logging.getLogger(__name__)

COSTS = {"OneCost": 1, "TwoCost": 2, "ThreeCost": 3, "FourCost": 4, "FiveCost": 5,
         "SixCost": 6, "SevenCost": 7, "EightCost": 8}

# stat names stored in champion assets -> old en_us.json stat keys
STAT_KEYS = {
    "Armor": "armor",
    "AttackRange": "range",
    "AttackSpeed": "attackSpeed",
    "CritChance": "critChance",
    "CritDamage": "critMultiplier",
    "HealthMax": "hp",
    "MagicResist": "magicResist",
    "ManaMax": "mana",
    "ManaStarting": "initialMana",
}
OLD_STAT_KEYS = ["armor", "attackSpeed", "critChance", "critMultiplier", "damage",
                 "hp", "initialMana", "magicResist", "mana", "range"]

# a stat stored as an FString name, then an index, two equal negative ints and a float value
STAT_PATTERN = re.compile(rb'(?s)([\x02-\x40])\x00\x00\x00([A-Za-z][A-Za-z0-9]*)\x00'
                          rb'\x01\x00\x00\x00.{8}(.{4})(.{4})(.{4})')

# "(2) ..." or "2) ..."
TIER_PATTERN = re.compile(r'^\(?(\d+)\)')
PLACEHOLDER = "???"


def package_path(file_path):
    """Convert a container file path to the package path used in references

    `TFT/Plugins/GameFeatures/Set_19/Content/A/DA_X.uasset` -> `/Set_19/A/DA_X`
    """
    path = file_path.rsplit('.', 1)[0]
    m = re.match(r'(?:[^/]+/)*?Plugins/(?:GameFeatures/)?([^/]+)/Content/(.*)', path)
    if m:
        return f"/{m.group(1)}/{m.group(2)}"
    m = re.match(r'[^/]+/Content/(.*)', path)
    if m:
        return f"/Game/{m.group(1)}"
    return "/" + path


def icon_path(package):
    """Return the lowercase path of a texture as exported by CDragon (.png)"""
    m = re.match(r'/([^/]+)/(.*)', package)
    if not m:
        return None
    plugin, rest = m.groups()
    if plugin == "Game":
        return f"tft/content/{rest}.png".lower()
    return f"tft/plugins/gamefeatures/{plugin}/content/{rest}.png".lower()


def read_stats(data):
    """Return {stat name: value} for stats stored as name/value pairs"""
    stats = {}
    for m in STAT_PATTERN.finditer(data):
        n, name = m.group(1)[0], m.group(2).decode()
        if len(name) + 1 != n:
            continue
        a, = struct.unpack('<i', m.group(3))
        b, = struct.unpack('<i', m.group(4))
        if a != b or a >= 0:
            continue
        value, = struct.unpack('<f', m.group(5))
        # curve-based stats have other data here, which reads as a tiny or huge float
        if value == value and (value == 0 or 1e-4 <= value < 100000):
            stats.setdefault(name, round(value, 4))
    return stats


def _plain(text):
    return ('<' not in text and '\n' not in text and '\r' not in text and len(text) <= 60
            and PLACEHOLDER not in text and not TIER_PATTERN.match(text))


class TftAsset:
    """A champion, trait, item or augment data asset"""

    def __init__(self, path, data, strings=None):
        self.path = path
        self.package = package_path(path)
        self.api_name = self.package.rsplit('/', 1)[1]
        zen = ZenPackage(data)
        self.names = zen.names
        self.imports = zen.imported_packages
        identifier = zen.identifier() or ""
        parts = identifier.split('.')
        self.kind = parts[1] if len(parts) >= 3 else None
        self.identifier = identifier or None
        self.texts = []
        for ref in find_text_references(data):
            text = strings.get(ref.key, ref.namespace) if strings is not None else None
            self.texts.append(ref.source if text is None else text)
        self.data = data

    def textures(self):
        return [n for n in self.names if n.startswith('/') and '/T_' in n]

    def texture(self, suffix):
        for t in self.textures():
            if t.lower().endswith(suffix.lower()):
                return icon_path(t)
        return None


def _name_and_desc(texts, fallback=None):
    """Pick a name (shortest plain text) and description (longest text)"""
    if not texts:
        return fallback, None
    desc = max(texts, key=len)
    # names are short and aren't sentences; a lone text is a description
    plain = [t for t in texts if _plain(t) and t != desc and not t.endswith('.')]
    name = min(plain, key=len) if plain else fallback
    return name, (None if desc == name else desc)


def build_champion(asset, traits_by_package):
    texts = asset.texts
    name = texts[0] if texts else None
    rest = [t for t in texts[1:] if t != name]
    desc = max(rest, key=len) if rest else None
    ability_name = next((t for t in rest if _plain(t) and t != desc), None)
    stats = {k: None for k in OLD_STAT_KEYS}
    for stat, value in read_stats(asset.data).items():
        if stat in STAT_KEYS:
            stats[STAT_KEYS[stat]] = value
    if stats["armor"] is not None:
        # omitted because they hold the default value
        if stats["initialMana"] is None:
            stats["initialMana"] = 0
        if stats["range"] is None:
            stats["range"] = 1
    cost = next((COSTS[n] for n in asset.names if n in COSTS), None)
    role = next((n for n in asset.names if n.startswith("DA_Role_")), None)
    traits = [traits_by_package[p].get("name") for p in asset.imports if p in traits_by_package]
    return {
        "ability": {
            "desc": desc,
            "icon": asset.texture("SpellIcon"),
            "name": ability_name,
            "variables": [],
        },
        "apiName": asset.api_name,
        "characterName": asset.identifier.rsplit('.', 1)[1],
        "cost": cost,
        "icon": asset.texture("_PC"),
        "name": name,
        "role": role,
        "squareIcon": asset.texture("_TeamPlanner_Portrait"),
        "stats": stats,
        "tileIcon": asset.texture("_Mobile"),
        "traits": traits,
    }


def build_trait(asset):
    tier_texts = [t for t in asset.texts if TIER_PATTERN.match(t) and PLACEHOLDER not in t]
    tiers = sorted({int(TIER_PATTERN.match(t).group(1)) for t in tier_texts})
    other = [t for t in asset.texts if not TIER_PATTERN.match(t)]
    name, desc = _name_and_desc(other)
    if tier_texts:
        desc = "\n".join(([desc] if desc else []) + tier_texts)
    effects = [{"maxUnits": (tiers[i + 1] - 1 if i + 1 < len(tiers) else 25), "minUnits": n,
                "style": None, "variables": {}} for i, n in enumerate(tiers)]
    return {
        "apiName": asset.api_name,
        "desc": desc,
        "effects": effects,
        "icon": icon_path(asset.textures()[0]) if asset.textures() else None,
        "name": name,
    }


def build_item(asset, traits_by_package, items_by_package):
    name, desc = _name_and_desc(asset.texts, fallback=asset.identifier.rsplit('.', 1)[1])
    tags = [n for n in asset.names if n.startswith(("Item.", "Augment."))]
    associated = [traits_by_package[p].get("name") for p in asset.imports if p in traits_by_package]
    # augments reference the items they grant, which aren't a recipe
    components = [items_by_package[p].api_name for p in asset.imports
                  if asset.kind == "Item" and p in items_by_package and items_by_package[p].kind == "Item"]
    return {
        "apiName": asset.api_name,
        "associatedTraits": associated,
        "composition": components,
        "desc": desc,
        "effects": {},
        "from": None,
        "icon": icon_path(asset.textures()[0]) if asset.textures() else None,
        "id": None,
        "incompatibleTraits": [],
        "name": name,
        "tags": tags,
        "unique": None,
    }


def load_assets(containers, strings=None, patterns=("*/DA_*.uasset",)):
    """Read every champion, trait, item and augment data asset of the containers"""
    assets = []
    for container in containers:
        entries = [e for e in container.entries if any(fnmatch.fnmatchcase(e.path, p) for p in patterns)]
        logger.info(f"reading {len(entries)} data assets of {container.path}")
        handles = {} if isinstance(container, IoStoreReader) else open(container.path, 'rb')
        try:
            for entry in entries:
                try:
                    asset = TftAsset(entry.path, container.read(entry, handles), strings)
                except (struct.error, UnicodeDecodeError, ValueError):
                    logger.debug(f"skipping {entry.path}: not a readable zen package")
                    continue
                if asset.kind in ("Champion", "Trait", "Item", "Augment"):
                    assets.append(asset)
        finally:
            for f in (handles.values() if isinstance(handles, dict) else [handles]):
                f.close()
    return assets


def latest_set(assets):
    """Return the highest set number with champions, or None"""
    numbers = [int(m.group(1)) for a in assets if a.kind == "Champion"
               for m in [re.match(r'/Set_(\d+)/', a.package)] if m]
    return max(numbers) if numbers else None


def build_tft_data(assets, set_number):
    """Return data in the shape of the old `cdragon/tft/<lang>.json` for one set"""
    prefix = f"/Set_{set_number}/"
    traits_by_package = {a.package: build_trait(a) for a in assets
                         if a.kind == "Trait" and a.package.startswith(prefix)}
    champions = [build_champion(a, traits_by_package) for a in assets
                 if a.kind == "Champion" and a.package.startswith(prefix)]
    items_by_package = {a.package: a for a in assets if a.kind in ("Item", "Augment")}
    items = [build_item(a, traits_by_package, items_by_package) for a in items_by_package.values()]
    champions.sort(key=lambda c: (c["cost"] or 0, c["apiName"]))
    traits = sorted(traits_by_package.values(), key=lambda t: t["apiName"])
    items.sort(key=lambda i: i["apiName"])
    set_data = {"champions": champions, "mutator": f"TFTSet{set_number}",
                "name": f"Set{set_number}", "number": set_number, "traits": traits}
    return {
        "items": items,
        "setData": [set_data],
        "sets": {str(set_number): {"champions": champions, "name": set_data["name"], "traits": traits}},
    }
