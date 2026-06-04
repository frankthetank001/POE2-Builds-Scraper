# Development Context for Claude Code

## Project
POE2-Builds-Scraper - scrapes poe.ninja PoE2 builds into a versioned usage artifact
(`build-stats-<league>-<version>.json`) consumed by ../POE2-PathOfCrafting. Phase 1 =
this scraper only; no app changes.

## Tech
Python 3.11+, httpx, pydantic v2 + pydantic-settings, tenacity. No DB. Stdlib protobuf
decoder (no `.proto` available for poe.ninja's builds API).

## Verified facts (live-tested 2026-06-04; don't re-derive blindly, but re-verify if stale)
- Endpoints:
  - `GET poe.ninja/poe2/api/data/index-state` -> JSON. `snapshotVersions[]` entry where
    `url == league_slug` gives `version` (path segment, rotates ~daily) + `snapshotName`
    (the `?overview=` param). Same version feeds /search and /character.
  - `GET poe.ninja/poe2/api/builds/{version}/search?overview={snapshotName}` ->
    application/x-protobuf, ~100 builds, columnar. Columns incl. `name` (character) and
    `account` (already "Name-1234"). They align 1:1 -> zip = roster.
  - `GET poe.ninja/poe2/api/builds/{version}/character?account=&name=&overview=` ->
    ~220 KB JSON: items[] with baseType + explicit/implicit/rune/crafted/fractured/
    desecrated mod arrays, skills[], pathOfBuildingExport.
  - No auth; needs browser UA + `Referer: poe.ninja/poe2/builds/{slug}`. Behind Cloudflare.
- Protobuf shape: root .1 message; .1.5 repeated = one block per column; block .1 = key,
  block .2.1 (repeated) = string values. Decoder must prefer "clean text" over
  "looks like a nested message" or ~5% of short account names get mis-recursed.
- Mapping into the app (POE2-PathOfCrafting):
  - Base name: poe.ninja `baseType` IS the app base name == object key in
    source_data/pob-data/Bases/*.json. Direct lookup (`get_item_base_by_name`), not fuzzy.
    Verified on a live 3-build pull: 20/26 direct hits; the 6 misses all carried a
    "Runeforged "/"Runemastered " prefix (PoE2 socketed-rune display name). Stripping that
    prefix at ingest -> 25/26 (96%). Last miss ("Fists of Stone") is likely stale pob-data
    (app snapshot is Dec-2025; refresh from repoe-fork). Keep raw base_name in the artifact;
    do the prefix-strip in the Phase 2 ingest (where the Bases dict lives).
  - Mod template: strip `[a|b]`->b / `[a]`->a, then ALL numbers -> `#`. This is NOT the
    app's `_normalize_stat_text` (which only templates `(X-Y)`/signed/`%`). Don't reuse it.
  - mod_id/tier: resolved at in-app ingest (Phase 2) via the app's ItemConverter; the
    scraper only emits `mod_template`. Tiers are precomputed in-app by stat_max desc.
  - Split RARE (craftable, has mod_usage) vs UNIQUE (fixed mods, buy-only).

## Layout
- `protobuf_decode.py` - schema-less wire decoder (the core trick).
- `snapshot.py` - index-state -> Snapshot(version, snapshot_name, league).
- `roster/` - RosterSource protocol + poeninja_search (default, no auth).
- `http_client.py` - throttled/retrying httpx GET (browser UA + Referer).
- `character.py` - per-character fetch + on-disk cache (resumable).
- `normalize.py` - markup strip + value templating + value extraction.
- `extract.py` - character JSON -> ExtractedItem(base, slot, rarity, mods). Confirm item
  field nesting on first live pull (`--dump-raw`); reads itemData defensively.
- `aggregate.py` - base_usage + mod_usage rollup (count each per character once).
- `run.py` - CLI: `--offline` (fixtures), real run, `--dump-raw`, `--limit`.

## Commands
- `python -m builds_scraper.run --offline`  - decode bundled fixtures, no network.
- `python -m builds_scraper.run --league runesofaldur --limit 100 --dump-raw`
- `pytest`  - offline tests against tests/fixtures (real captured payloads).

## Etiquette / scope
Personal/low-volume. Self-throttle (poe.ninja publishes no limit). poe.ninja ToS is a
grey area; keep volume modest. Display the GGG non-affiliation disclaimer (in the
artifact + any UI). Data ultimately derives from GGG's public APIs.

## Deferred (not Phase 1)
mod_id/tier resolution (Phase 2 ingest), pricing/buy-vs-craft recs (Phase 3, reuse app's
ItemPricer + CraftingSimulator), tier-impact regression, alerts. League hardcore variant
slug not yet confirmed.
