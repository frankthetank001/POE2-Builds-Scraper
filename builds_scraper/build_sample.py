"""Pick a representative subset of builds for the published browser artifact.

The artifact is committed to git and fetched over HTTP, and a trimmed build (with its PoB
code) is ~25 KB, so we publish a curated sample rather than every character. The sample is
balanced across ascendancies - round-robin over class groups - so the browser shows variety
instead of N copies of the single dominant meta build.
"""

from __future__ import annotations

from collections import defaultdict

from .models import Build

DEFAULT_SAMPLE_SIZE = 30


def _quality(b: Build) -> tuple[int, int]:
    """Sort key within an ascendancy group: higher level, then higher top-skill DPS."""
    top_dps = max((s.dps for s in b.main_skills), default=0)
    return (b.level, top_dps)


def sample_builds(builds: list[Build], target: int = DEFAULT_SAMPLE_SIZE) -> list[Build]:
    """Up to `target` builds, deduped by id and balanced across ascendancy.

    Within each ascendancy the strongest builds (level, then DPS) come first; we then
    round-robin across ascendancies so no single class dominates the sample.
    """
    # Dedupe by id, keeping the newest (latest updated_utc) record.
    by_id: dict[str, Build] = {}
    for b in builds:
        prev = by_id.get(b.id)
        if prev is None or b.updated_utc > prev.updated_utc:
            by_id[b.id] = b

    groups: dict[str, list[Build]] = defaultdict(list)
    for b in by_id.values():
        groups[b.ascendancy or b.base_class or "Unknown"].append(b)
    for g in groups.values():
        g.sort(key=_quality, reverse=True)

    # Round-robin: take the current-best from each ascendancy in turn until we hit target.
    # Order the groups by their best build so stronger classes lead the first pass.
    ordered = sorted(groups.values(), key=lambda g: _quality(g[0]), reverse=True)
    out: list[Build] = []
    idx = 0
    while len(out) < target:
        took_any = False
        for g in ordered:
            if idx < len(g):
                out.append(g[idx])
                took_any = True
                if len(out) >= target:
                    break
        if not took_any:
            break
        idx += 1
    return out
