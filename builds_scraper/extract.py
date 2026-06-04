"""Pull craftable signal out of a character JSON: per equipped item, its base + mods.

The exact nesting of the character payload's item objects (fields at the item level vs
under an `itemData` sub-object) should be confirmed on the first live pull -- run with
`--dump-raw` and eyeball cache/characters/*.json. We read defensively so either shape works.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import extract_values, normalize_mod

# poe.ninja inventoryId -> POE2-PathOfCrafting slot vocabulary.
_SLOT_MAP = {
    "Weapon": "weapon", "Weapon2": "weapon", "Offhand": "offhand", "Offhand2": "offhand",
    "Helm": "helmet", "Helmet": "helmet", "BodyArmour": "body_armour",
    "Gloves": "gloves", "Boots": "boots",
    "Amulet": "amulet", "Ring": "ring", "Ring2": "ring", "Belt": "belt",
}

# frameType -> rarity. >=4 (gem/currency/quest/etc.) is not craftable equipment -> skipped.
_RARITY = {0: "normal", 1: "magic", 2: "rare", 3: "unique"}

# Each mod array on an item and the "origin" we tag it with.
_MOD_ARRAYS = {
    "explicitMods": "explicit",
    "implicitMods": "implicit",
    "runeMods": "rune",
    "craftedMods": "crafted",
    "fracturedMods": "fractured",
    "desecratedMods": "desecrated",
    "enchantMods": "enchant",
}


@dataclass
class ExtractedMod:
    template: str
    origin: str
    values: list[float] = field(default_factory=list)


@dataclass
class ExtractedItem:
    base_name: str
    slot: str
    rarity: str
    mods: list[ExtractedMod] = field(default_factory=list)


def _item_fields(item: dict) -> dict:
    """Items may carry fields directly or under itemData; merge with itemData winning."""
    inner = item.get("itemData")
    if isinstance(inner, dict):
        merged = dict(item)
        merged.update(inner)
        return merged
    return item


def extract_items(character: dict) -> list[ExtractedItem]:
    out: list[ExtractedItem] = []
    for raw in character.get("items", []) or []:
        it = _item_fields(raw)
        frame = it.get("frameType", it.get("rarity"))
        rarity = _RARITY.get(frame) if isinstance(frame, int) else (
            str(frame).lower() if frame is not None else None
        )
        if rarity not in ("normal", "magic", "rare", "unique"):
            continue  # skip gems, jewels-as-currency, flasks handled elsewhere, etc.
        base_name = it.get("baseType") or it.get("typeLine")
        if not base_name:
            continue
        inv = it.get("inventoryId", "")
        slot = _SLOT_MAP.get(inv, inv.lower() or "unknown")

        mods: list[ExtractedMod] = []
        for arr_key, origin in _MOD_ARRAYS.items():
            for raw_mod in it.get(arr_key, []) or []:
                if not isinstance(raw_mod, str):
                    continue
                template = normalize_mod(raw_mod)
                if template:
                    mods.append(ExtractedMod(template, origin, extract_values(raw_mod)))
        out.append(ExtractedItem(base_name=base_name, slot=slot, rarity=rarity, mods=mods))
    return out


def main_skills(character: dict, top: int = 3) -> list[str]:
    """Best-effort: a few skill names for the build, for the base_usage common_skills hint."""
    names: list[str] = []
    for sk in character.get("skills", []) or []:
        nm = sk.get("name") if isinstance(sk, dict) else None
        if nm:
            names.append(nm)
        if len(names) >= top:
            break
    return names
