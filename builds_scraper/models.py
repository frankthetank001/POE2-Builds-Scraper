"""Pydantic models for the Phase 1 output artifact.

Deliberately omits mod_id / tier: that resolution reuses the app's ModItem.json +
ItemConverter and happens at in-app ingest (Phase 2). Phase 1 emits human-inspectable
base names + templated mod text + counts (+ value samples for later tier analysis).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    disclaimer: str = (
        "This product isn't affiliated with or endorsed by Grinding Gear Games. "
        "Build data sourced from poe.ninja."
    )
