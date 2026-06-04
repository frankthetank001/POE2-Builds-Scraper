"""Fetch per-character build JSON, cached to disk for free resumability.

GET /poe2/api/builds/{version}/character?account={account}&name={character}&overview={snapshotName}
  -> ~220 KB JSON: items[], skills[], pathOfBuildingExport, defensiveStats, ...
"""

from __future__ import annotations

import json
import logging
import re

from .config import Settings
from .http_client import PoeNinjaClient
from .roster.base import RosterEntry
from .snapshot import Snapshot

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _cache_path(settings: Settings, snapshot: Snapshot, entry: RosterEntry):
    key = _SAFE.sub("_", f"{snapshot.version}__{entry.account}__{entry.character}")
    return settings.cache_dir / "characters" / f"{key}.json"


def fetch_character(
    client: PoeNinjaClient, snapshot: Snapshot, entry: RosterEntry, *, use_cache: bool = True
) -> dict | None:
    """Return the character JSON (from cache if present), or None on 404/failure."""
    path = _cache_path(client.settings, snapshot, entry)
    if use_cache and path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("corrupt cache %s; refetching", path.name)

    url = f"{client.settings.poeninja_base}/builds/{snapshot.version}/character"
    params = {"account": entry.account, "name": entry.character, "overview": snapshot.snapshot_name}
    try:
        resp = client.get(url, params=params)
    except Exception as e:
        logger.warning("fetch failed for %s/%s: %s", entry.account, entry.character, e)
        return None
    if resp.status_code == 404:
        logger.info("404 (no snapshot) for %s/%s", entry.account, entry.character)
        return None
    if resp.status_code != 200:
        logger.warning("status %s for %s/%s", resp.status_code, entry.account, entry.character)
        return None
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data
