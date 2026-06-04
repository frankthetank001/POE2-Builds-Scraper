"""CLI orchestrator: index-state -> roster -> per-character -> aggregate -> JSON.

    python -m builds_scraper.run --league runesofaldur --limit 100   # live scrape
    python -m builds_scraper.run --list-leagues                      # discover leagues (incl. hardcore)
    python -m builds_scraper.run --from-cache                        # rebuild from accumulated cache (bigger sample)
    python -m builds_scraper.run --offline                           # decode bundled fixtures, no network

Writes two files: a versioned archive in output/ and a stable data/latest-<slug>.json
that POE2-PathOfCrafting fetches (mirrors the repoe-fork/pob-data -> app pattern).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import sys
from pathlib import Path

from .aggregate import Aggregator
from .build_sample import sample_builds
from .build_trim import trim_build
from .character import fetch_character
from .config import Settings
from .extract import extract_items, main_skills
from .http_client import PoeNinjaClient
from .models import BuildsArtifact, BuildStats
from .roster.base import RosterEntry
from .roster.poeninja_search import (
    PoeNinjaSearchRoster,
    decode_search_columns,
    roster_from_columns,
)
from .snapshot import (
    Snapshot,
    list_build_leagues,
    load_snapshot_from_index_state_json,
    resolve_snapshot,
)

logger = logging.getLogger(__name__)
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _write_artifact(stats: BuildStats, settings: Settings) -> Path:
    settings.ensure_dirs()
    payload = stats.model_dump_json(indent=2)
    versioned = settings.output_dir / f"build-stats-{stats.league_slug}-{stats.snapshot_version}.json"
    versioned.write_text(payload, encoding="utf-8")
    # Stable pointer the app fetches (committed by the GitHub Action).
    latest = settings.published_dir / f"latest-{stats.league_slug}.json"
    latest.write_text(payload, encoding="utf-8")
    logger.info(
        "wrote %s and %s  (%d bases, %d mods from %d builds)",
        versioned.name, latest.name, len(stats.base_usage), len(stats.mod_usage), stats.sample_size,
    )
    return versioned


def _aggregate(roster: list[RosterEntry], character_jsons, snapshot: Snapshot) -> BuildStats:
    agg = Aggregator()
    for data in character_jsons:
        if data:
            agg.add_character(extract_items(data), main_skills(data))
    return agg.build(
        league=snapshot.league_name, league_slug=snapshot.league_slug,
        version=snapshot.version, snapshot_name=snapshot.snapshot_name,
        scraped_at=_now_iso(), roster_size=len(roster),
    )


def _build_browser_artifact(
    character_jsons, snapshot: Snapshot, roster_size: int
) -> BuildsArtifact:
    """Trim each character into a compact Build, then sample a representative subset."""
    trimmed = []
    for data in character_jsons:
        if not data:
            continue
        b = trim_build(data, snapshot.league_slug)
        if b is not None:
            trimmed.append(b)
    sampled = sample_builds(trimmed)
    return BuildsArtifact(
        league=snapshot.league_name, league_slug=snapshot.league_slug,
        snapshot_version=snapshot.version, snapshot_name=snapshot.snapshot_name,
        scraped_at=_now_iso(), sample_size=len(sampled), roster_size=roster_size,
        builds=sampled,
    )


def _write_builds_artifact(artifact: BuildsArtifact, settings: Settings) -> Path:
    settings.ensure_dirs()
    payload = artifact.model_dump_json(indent=2)
    versioned = settings.output_dir / f"builds-{artifact.league_slug}-{artifact.snapshot_version}.json"
    versioned.write_text(payload, encoding="utf-8")
    # Stable pointer the app fetches (committed by the GitHub Action), separate from the
    # aggregate latest-<slug>.json so the stats file stays small.
    latest = settings.published_dir / f"builds-{artifact.league_slug}.json"
    latest.write_text(payload, encoding="utf-8")
    logger.info(
        "wrote %s and %s  (%d builds sampled from %d)",
        versioned.name, latest.name, artifact.sample_size, artifact.roster_size,
    )
    return latest


def run(settings: Settings, limit: int, *, dump_raw: bool = False) -> Path:
    settings.ensure_dirs()
    with PoeNinjaClient(settings) as client:
        snapshot = resolve_snapshot(client, settings.league_slug)
        roster = PoeNinjaSearchRoster(client).fetch(snapshot, limit)

        def _iter():
            for i, entry in enumerate(roster, 1):
                data = fetch_character(client, snapshot, entry)
                if dump_raw and i == 1 and data:
                    (settings.cache_dir / "sample_character.json").write_text(
                        json.dumps(data, indent=2), encoding="utf-8"
                    )
                if i % 10 == 0:
                    logger.info("fetched %d/%d", i, len(roster))
                yield data

        chars = list(_iter())
        stats = _aggregate(roster, chars, snapshot)
        stats_path = _write_artifact(stats, settings)
        builds = _build_browser_artifact(chars, snapshot, len(roster))
    _write_builds_artifact(builds, settings)
    return stats_path


def run_from_cache(settings: Settings) -> Path:
    """Rebuild the artifact from ALL cached characters for the current league.

    Grows the sample beyond the /search top-~100 cap: run the daily cron, the cache
    accumulates distinct characters across snapshots, and this re-aggregates the union
    (deduped by account/character, filtered to the current league).
    """
    settings.ensure_dirs()
    with PoeNinjaClient(settings) as client:
        snapshot = resolve_snapshot(client, settings.league_slug)

    cache_glob = sorted((settings.cache_dir / "characters").glob("*.json"))
    by_char: dict[tuple[str, str], dict] = {}
    for path in cache_glob:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("league") and data["league"] != snapshot.league_name:
            continue  # different league in a shared cache
        key = (data.get("account", ""), data.get("name", ""))
        prev = by_char.get(key)
        if prev is None or (data.get("updatedUtc", "") > prev.get("updatedUtc", "")):
            by_char[key] = data

    logger.info("from-cache: %d cache files -> %d distinct characters", len(cache_glob), len(by_char))
    roster = [RosterEntry(account=a, character=c) for (a, c) in by_char]
    chars = list(by_char.values())
    stats = _aggregate(roster, chars, snapshot)
    stats_path = _write_artifact(stats, settings)
    builds = _build_browser_artifact(chars, snapshot, len(roster))
    _write_builds_artifact(builds, settings)
    return stats_path


def run_offline(limit: int) -> int:
    snap = load_snapshot_from_index_state_json(str(FIXTURES / "index-state.json"), "runesofaldur")
    payload = (FIXTURES / "search_runesofaldur.pb").read_bytes()
    roster = roster_from_columns(decode_search_columns(payload), limit)
    print(f"snapshot: {snap.league_name}  version={snap.version}  overview={snap.snapshot_name}")
    print(f"roster: {len(roster)} builds")
    for e in roster[:15]:
        print(f"  {e.account:24s} {e.character:24s} {e.extra}")
    return len(roster)


def list_leagues(settings: Settings) -> None:
    with PoeNinjaClient(settings) as client:
        leagues = list_build_leagues(client)
    print("Build leagues on poe.ninja (slug | hardcore | indexed | name):")
    for lg in leagues:
        flag = "HC" if lg.hardcore else "SC"
        idx = "indexed" if lg.indexed else "       "
        print(f"  {lg.slug:28s} {flag}  {idx}  {lg.name}")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # non-ASCII names on cp1252 consoles
        except Exception:
            pass

    p = argparse.ArgumentParser(description="poe.ninja PoE2 builds scraper (Phase 1)")
    p.add_argument("--league", default=None, help="poe.ninja league slug (e.g. runesofaldur)")
    p.add_argument("--limit", type=int, default=None, help="max builds to pull")
    p.add_argument("--list-leagues", action="store_true", help="list available build leagues and exit")
    p.add_argument("--from-cache", action="store_true", help="rebuild artifact from accumulated cache")
    p.add_argument("--offline", action="store_true", help="decode bundled fixtures, no network")
    p.add_argument("--dump-raw", action="store_true", help="dump the first character JSON for inspection")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings()
    if args.league:
        settings.league_slug = args.league
    limit = args.limit if args.limit is not None else settings.roster_limit

    if args.list_leagues:
        list_leagues(settings)
    elif args.offline:
        run_offline(limit)
    elif args.from_cache:
        run_from_cache(settings)
    else:
        run(settings, limit, dump_raw=args.dump_raw)


if __name__ == "__main__":
    main()
