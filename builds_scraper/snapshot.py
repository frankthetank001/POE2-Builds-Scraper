"""Resolve the rotating snapshot for a league from poe.ninja's index-state.

The `version` token (e.g. "0252-20260604-56084") rotates ~daily; calling the build
endpoints with a stale one 404s. Always resolve it at run start. The same version +
snapshotName feed both /search and /character.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from .http_client import PoeNinjaClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Snapshot:
    league_slug: str  # "runesofaldur"
    league_name: str  # "Runes of Aldur"
    version: str  # "0252-20260604-56084"  -> path segment
    snapshot_name: str  # "runes-of-aldur"      -> ?overview= param


@dataclass(frozen=True)
class BuildLeague:
    slug: str
    name: str
    hardcore: bool
    indexed: bool


def _fetch_index_state(client: PoeNinjaClient) -> dict:
    resp = client.get(f"{client.settings.poeninja_base}/data/index-state")
    resp.raise_for_status()
    return resp.json()


def list_build_leagues(client: PoeNinjaClient) -> list[BuildLeague]:
    """All leagues with build data (incl. hardcore variants), from index-state."""
    data = _fetch_index_state(client)
    out: list[BuildLeague] = []
    for lg in data.get("buildLeagues", []):
        out.append(
            BuildLeague(
                slug=lg.get("url", ""),
                name=lg.get("displayName") or lg.get("name", ""),
                hardcore=bool(lg.get("hardcore", False)),
                indexed=bool(lg.get("indexed", False)),
            )
        )
    return out


def resolve_snapshot(client: PoeNinjaClient, league_slug: str) -> Snapshot:
    return _pick(_fetch_index_state(client), league_slug)


def _pick(index_state: dict, league_slug: str) -> Snapshot:
    """Choose the live snapshotVersions entry for the league (overviewType 0 = current)."""
    candidates = [
        s for s in index_state.get("snapshotVersions", []) if s.get("url") == league_slug
    ]
    if not candidates:
        known = sorted({s.get("url") for s in index_state.get("snapshotVersions", [])})
        raise ValueError(f"league slug {league_slug!r} not in index-state. Known: {known}")
    # Prefer the live overview (overviewType == 0) over time-machine snapshots.
    live = [c for c in candidates if c.get("overviewType") == 0]
    chosen = (live or candidates)[0]
    snap = Snapshot(
        league_slug=league_slug,
        league_name=chosen.get("name", league_slug),
        version=chosen["version"],
        snapshot_name=chosen["snapshotName"],
    )
    logger.info("snapshot: league=%s version=%s overview=%s",
                snap.league_name, snap.version, snap.snapshot_name)
    return snap


def load_snapshot_from_index_state_json(path: str, league_slug: str) -> Snapshot:
    """Offline helper for tests / fixtures."""
    with open(path, encoding="utf-8") as f:
        return _pick(json.load(f), league_slug)
