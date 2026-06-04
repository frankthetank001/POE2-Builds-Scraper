"""Trim a raw poe.ninja character JSON into a compact `Build` for the builds browser.

`character.py` caches the full ~220-340 KB per-character payload; the aggregate pipeline
(extract.py / aggregate.py) only counts base/mod frequencies and discards the rest. This
module keeps the rich per-build data a real builds browser needs - gear, skills, defenses,
class/ascendancy and out-links - in a much smaller shape.

Two deliberate choices:
- Mod text is markup-STRIPPED but NOT value-templated (numbers kept), so the app can show
  the real rolled values and resolve tier/mod_id itself (via its BuildResolver on `text`).
- Base class comes from the decoded PoB export (`className`); poe.ninja's `class` field is
  actually the ASCENDANCY, so we keep that as `ascendancy`.
"""

from __future__ import annotations

import base64
import logging
import re
import zlib
from urllib.parse import quote

from .extract import _MOD_ARRAYS, _RARITY, _SLOT_MAP, _item_fields
from .models import Build, BuildDefense, BuildItem, BuildItemMod, BuildSkill
from .normalize import extract_values, strip_markup

logger = logging.getLogger(__name__)

# Inventory ids that are not wearable equipment (runes shown as separate currency lines, etc.)
_SKIP_INVENTORY = {"Chakra"}
_RUNE_HINT = re.compile(r"\b(Rune|Soul Core)\b", re.IGNORECASE)
_CLASS_NAME = re.compile(r'className="([^"]*)"')
_ASCEND_NAME = re.compile(r'ascendClassName="([^"]*)"')


def poeninja_character_url(league_slug: str, account: str, character: str) -> str:
    """Public poe.ninja build page for a character.

    NOTE: the exact path is worth a live re-verify (poe.ninja's builds SPA); the league-slug
    form below matches the live-tested note. Account is already in "Name-1234" form.
    """
    return (
        f"https://poe.ninja/poe2/builds/{quote(league_slug)}"
        f"/character/{quote(account)}/{quote(character)}"
    )


def decode_pob_classes(pob_export: str | None) -> tuple[str | None, str | None]:
    """(base_class, ascendancy) from a PoB2 export code, or (None, None) on any failure.

    The export is base64url-encoded, zlib-compressed XML whose <Build> element carries
    className (base class) and ascendClassName (ascendancy).
    """
    if not pob_export:
        return None, None
    try:
        raw = base64.urlsafe_b64decode(pob_export)
        xml = zlib.decompress(raw).decode("utf-8", "replace")
    except Exception as e:  # malformed / truncated export
        logger.debug("pob decode failed: %s", e)
        return None, None
    cm = _CLASS_NAME.search(xml)
    am = _ASCEND_NAME.search(xml)
    base_class = cm.group(1) if cm and cm.group(1) else None
    ascendancy = am.group(1) if am and am.group(1) else None
    return base_class, ascendancy


def _main_skills(character: dict, top: int = 3) -> list[BuildSkill]:
    """Top skills by precomputed DPS (the old main_skills() read a non-existent top-level
    'name' and always returned []). Each skill: active gem name + its support gems."""
    scored: list[tuple[int, BuildSkill]] = []
    for sk in character.get("skills", []) or []:
        if not isinstance(sk, dict):
            continue
        gems = sk.get("allGems") or []
        if not gems:
            continue
        active = gems[0].get("name")
        if not active:
            continue
        dps = 0
        dps_arr = sk.get("dps") or []
        if dps_arr and isinstance(dps_arr[0], dict):
            dps = int(dps_arr[0].get("dps") or 0)
        supports = [g.get("name") for g in gems[1:] if g.get("name")]
        scored.append((dps, BuildSkill(name=active, dps=dps, supports=supports)))

    if not scored:
        return []
    # Prefer skills that actually deal damage; if none are scored, keep the first listed.
    damaging = [s for s in scored if s[0] > 0]
    pool = damaging or scored[:1]
    pool.sort(key=lambda s: -s[0])
    return [bs for _, bs in pool[:top]]


def _defense(character: dict) -> BuildDefense:
    ds = character.get("defensiveStats") or {}

    def gi(key: str) -> int:
        v = ds.get(key)
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    return BuildDefense(
        life=gi("life"),
        energy_shield=gi("energyShield"),
        mana=gi("mana"),
        spirit=gi("spirit"),
        ehp=gi("effectiveHealthPool"),
        fire_res=gi("fireResistance"),
        cold_res=gi("coldResistance"),
        lightning_res=gi("lightningResistance"),
        chaos_res=gi("chaosResistance"),
    )


def _socketed_rune_names(item: dict) -> list[str]:
    """Rune / soul-core names socketed into an item (skip granted skill gems)."""
    runes: list[str] = []
    for s in item.get("socketedItems") or []:
        if not isinstance(s, dict):
            continue
        name = s.get("name") or s.get("baseType") or ""
        # Runes/soul-cores carry runeMods or a Rune/Soul Core name; skill gems do not.
        if (s.get("runeMods") or _RUNE_HINT.search(name)) and name:
            runes.append(name)
    return runes


def _items(character: dict) -> list[BuildItem]:
    out: list[BuildItem] = []
    for raw in character.get("items", []) or []:
        it = _item_fields(raw)
        if it.get("inventoryId") in _SKIP_INVENTORY:
            continue
        frame = it.get("frameType", it.get("rarity"))
        rarity = _RARITY.get(frame) if isinstance(frame, int) else (
            str(frame).lower() if frame is not None else None
        )
        if rarity not in ("normal", "magic", "rare", "unique"):
            continue
        base_type = it.get("baseType") or it.get("typeLine")
        if not base_type:
            continue
        inv = it.get("inventoryId", "")
        slot = _SLOT_MAP.get(inv, (inv or "unknown").lower())

        mods: list[BuildItemMod] = []
        for arr_key, origin in _MOD_ARRAYS.items():
            for raw_mod in it.get(arr_key, []) or []:
                if not isinstance(raw_mod, str) or not raw_mod.strip():
                    continue
                text = re.sub(r"\s+", " ", strip_markup(raw_mod)).strip()
                mods.append(BuildItemMod(text=text, origin=origin, values=extract_values(raw_mod)))

        out.append(BuildItem(
            slot=slot,
            name=it.get("name") or None,
            base_type=base_type,
            rarity=rarity,
            item_level=int(it.get("ilvl") or 0),
            icon=it.get("icon") or None,
            corrupted=bool(it.get("corrupted")),
            mods=mods,
            runes=_socketed_rune_names(it),
        ))
    return out


def trim_build(character: dict, league_slug: str) -> Build | None:
    """Compact `Build` from a raw character JSON, or None if it lacks identity."""
    account = character.get("account") or ""
    name = character.get("name") or ""
    if not account or not name:
        return None

    base_class, ascend_from_pob = decode_pob_classes(character.get("pathOfBuildingExport"))
    ascendancy = character.get("class") or ascend_from_pob

    return Build(
        id=f"{account}__{name}",
        account=account,
        character=name,
        level=int(character.get("level") or 0),
        base_class=base_class,
        ascendancy=ascendancy,
        main_skills=_main_skills(character),
        defense=_defense(character),
        items=_items(character),
        poeninja_url=poeninja_character_url(league_slug, account, name),
        pob_export=character.get("pathOfBuildingExport") or None,
        updated_utc=character.get("updatedUtc") or "",
    )
