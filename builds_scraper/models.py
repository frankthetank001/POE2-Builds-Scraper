"""Pydantic models for the Phase 1 output artifact.

Deliberately omits mod_id / tier: that resolution reuses the app's ModItem.json +
ItemConverter and happens at in-app ingest (Phase 2). Phase 1 emits human-inspectable
base names + templated mod text + counts (+ value samples for later tier analysis).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_DISCLAIMER = (
    "This product isn't affiliated with or endorsed by Grinding Gear Games. "
    "Build data sourced from poe.ninja."
)


class BaseUsage(BaseModel):
    base_name: str  # poe.ninja baseType == app base name == Bases/*.json object key
    slot: str
    usage_count: int = 0
    usage_pct: float = 0.0
    rarity_mix: dict[str, int] = Field(default_factory=dict)  # {"rare": n, "unique": n, ...}
    common_skills: list[str] = Field(default_factory=list)


class ModUsage(BaseModel):
    base_name: str
    slot: str
    mod_template: str  # markup-free, value-templated; e.g. "+# to maximum Mana"
    mod_origin: str  # explicit | implicit | rune | crafted | fractured | desecrated | enchant
    usage_count: int = 0
    usage_pct: float = 0.0
    value_samples: list[float] = Field(default_factory=list)


class BuildStats(BaseModel):
    league: str
    league_slug: str
    snapshot_version: str
    snapshot_name: str
    scraped_at: str  # ISO-8601, stamped by the caller (no clock access mid-pipeline)
    sample_size: int  # characters successfully aggregated
    roster_size: int  # characters in the roster (attempted)
    base_usage: list[BaseUsage] = Field(default_factory=list)
    mod_usage: list[ModUsage] = Field(default_factory=list)
    disclaimer: str = DEFAULT_DISCLAIMER


# ---------------------------------------------------------------------------
# Builds-browser artifact (data/builds-<slug>.json)
#
# A separate, smaller file holding a representative SAMPLE of real builds with their
# gear, skills, defenses and out-links. Published alongside (not inside) the aggregate
# BuildStats so the stats file stays lean. Mod text is markup-stripped but NOT templated
# (numbers kept) for display; the app resolves tier/mod_id at query time from `text`.
# ---------------------------------------------------------------------------
class BuildItemMod(BaseModel):
    text: str  # markup-stripped, numbers intact; e.g. "+24% to all Elemental Resistances"
    origin: str  # explicit | implicit | rune | crafted | fractured | desecrated | enchant
    values: list[float] = Field(default_factory=list)  # the rolled numbers, for in-app tiering


class BuildItem(BaseModel):
    slot: str  # app slot vocab: weapon | helmet | body_armour | gloves | boots | amulet | ring | belt | ...
    name: str | None = None  # unique/rare display name; None for plain bases
    base_type: str  # may carry a Runeforged/Runemastered prefix (strip at app ingest for lookups)
    rarity: str  # normal | magic | rare | unique
    item_level: int = 0
    icon: str | None = None  # absolute web.poecdn.com URL
    corrupted: bool = False
    mods: list[BuildItemMod] = Field(default_factory=list)
    runes: list[str] = Field(default_factory=list)  # socketed rune / soul-core names


class BuildSkill(BaseModel):
    name: str
    dps: int = 0
    supports: list[str] = Field(default_factory=list)


class BuildDefense(BaseModel):
    life: int = 0
    energy_shield: int = 0
    mana: int = 0
    spirit: int = 0
    ehp: int = 0  # poe.ninja effectiveHealthPool
    fire_res: int = 0
    cold_res: int = 0
    lightning_res: int = 0
    chaos_res: int = 0


class Build(BaseModel):
    id: str  # stable key, "{account}__{character}"
    account: str  # poe.ninja "Name-1234" form
    character: str
    level: int = 0
    base_class: str | None = None  # from the PoB export (className); class field is the ascendancy
    ascendancy: str | None = None  # poe.ninja `class` / PoB ascendClassName
    main_skills: list[BuildSkill] = Field(default_factory=list)
    defense: BuildDefense = Field(default_factory=BuildDefense)
    items: list[BuildItem] = Field(default_factory=list)
    poeninja_url: str = ""
    pob_export: str | None = None  # ready-to-paste PoB2 import code (inlined)
    updated_utc: str = ""


class BuildsArtifact(BaseModel):
    league: str
    league_slug: str
    snapshot_version: str
    snapshot_name: str
    scraped_at: str
    sample_size: int  # number of builds in this artifact (after sampling)
    roster_size: int = 0  # characters considered before sampling
    builds: list[Build] = Field(default_factory=list)
    disclaimer: str = DEFAULT_DISCLAIMER
