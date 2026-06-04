"""Roll per-character extractions up into base_usage + mod_usage."""

from __future__ import annotations

from collections import Counter, defaultdict

from .extract import ExtractedItem
from .models import BaseUsage, BuildStats, ModUsage


class Aggregator:
    def __init__(self) -> None:
        self.sample_size = 0
        # base key = (base_name, slot)
        self._base_count: Counter[tuple[str, str]] = Counter()
        self._base_rarity: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        self._base_skills: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        # mod key = (base_name, slot, mod_template, origin)
        self._mod_count: Counter[tuple[str, str, str, str]] = Counter()
        self._mod_samples: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)

    def add_character(self, items: list[ExtractedItem], skills: list[str]) -> None:
        self.sample_size += 1
        # Count each (base, slot) at most once per character.
        seen_bases: set[tuple[str, str]] = set()
        seen_mods: set[tuple[str, str, str, str]] = set()
        for it in items:
            bkey = (it.base_name, it.slot)
            if bkey not in seen_bases:
                seen_bases.add(bkey)
                self._base_count[bkey] += 1
                self._base_rarity[bkey][it.rarity] += 1
                for s in skills:
                    self._base_skills[bkey][s] += 1
            # Mods only meaningful for craftable rares (uniques have fixed mods).
            if it.rarity != "rare":
                continue
            for mod in it.mods:
                mkey = (it.base_name, it.slot, mod.template, mod.origin)
                if mkey not in seen_mods:
                    seen_mods.add(mkey)
                    self._mod_count[mkey] += 1
                if len(self._mod_samples[mkey]) < 50 and mod.values:
                    self._mod_samples[mkey].append(mod.values[0])

    def build(self, *, league: str, league_slug: str, version: str, snapshot_name: str,
              scraped_at: str, roster_size: int) -> BuildStats:
        n = max(self.sample_size, 1)
        base_usage = [
            BaseUsage(
                base_name=bn, slot=slot, usage_count=c, usage_pct=round(c / n, 4),
                rarity_mix=dict(self._base_rarity[(bn, slot)]),
                common_skills=[s for s, _ in self._base_skills[(bn, slot)].most_common(3)],
            )
            for (bn, slot), c in self._base_count.most_common()
        ]
        mod_usage = [
            ModUsage(
                base_name=bn, slot=slot, mod_template=tpl, mod_origin=origin,
                usage_count=c, usage_pct=round(c / n, 4),
                value_samples=self._mod_samples[(bn, slot, tpl, origin)],
            )
            for (bn, slot, tpl, origin), c in self._mod_count.most_common()
        ]
        return BuildStats(
            league=league, league_slug=league_slug, snapshot_version=version,
            snapshot_name=snapshot_name, scraped_at=scraped_at,
            sample_size=self.sample_size, roster_size=roster_size,
            base_usage=base_usage, mod_usage=mod_usage,
        )
