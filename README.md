# POE2-Builds-Scraper

Scrapes poe.ninja's Path of Exile 2 builds into a versioned **usage artifact** -
which item bases and which mods popular builds actually use - to feed crafting and
buy/sell recommendations in [POE2-PathOfCrafting](../POE2-PathOfCrafting).

This is **Phase 1**: the standalone scraper that produces the artifact. It does not
touch POE2-PathOfCrafting; that app ingests the artifact in a later phase.

## Why this exists

Build analysis was a stated core feature of POE2-PathOfCrafting but was never built.
The app already prices items (POE2 Trade API) and estimates craft cost; it was only
missing the demand signal - "which items/mods are worth crafting or buying." poe.ninja
supplies that.

## How it works

```
GET /poe2/api/data/index-state                      -> current {version, snapshotName} for the league
GET /poe2/api/builds/{version}/search?overview=...   -> protobuf columnar table -> (account, character) roster
GET /poe2/api/builds/{version}/character?...          -> JSON per character: items[] + full mod arrays
                                                         -> aggregate -> build-stats-<league>-<version>.json
```

- No OAuth. poe.ninja gates on a normal browser `User-Agent` + a `Referer` to the
  builds page. The `account` column is already in poe.ninja's `Name-1234` form.
- The `/search` payload is `application/x-protobuf` with no published schema; we decode
  it generically (`builds_scraper/protobuf_decode.py`) and lift the `name`/`account`
  columns. Verified against a captured payload in `tests/fixtures` (100 builds, aligned).
- The `version` rotates ~daily and resets each league - always resolved at run start.

## Quick start

PowerShell does not support `&&`; run each line on its own.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Offline sanity check (decodes the bundled fixtures, no network):
python -m builds_scraper.run --offline

# Discover available leagues (incl. hardcore variants):
python -m builds_scraper.run --list-leagues

# Real run against the live league:
python -m builds_scraper.run --league runesofaldur --limit 100 --dump-raw

# Rebuild from the accumulated cache (grows the sample past the /search ~100 cap):
python -m builds_scraper.run --from-cache --league runesofaldur
```

Each run writes two files: `output/build-stats-<slug>-<version>.json` (versioned archive,
gitignored) and `data/latest-<slug>.json` (stable, committed - the file the app fetches).

## Publishing for the app (Phase 2 integration)

The roster endpoint returns ~100 top builds per snapshot. To grow the sample, the bundled
GitHub Action (`.github/workflows/scrape.yml`) runs daily: it scrapes the current top builds,
caches each character, re-aggregates the accumulated cache with `--from-cache`, and commits
`data/latest-<slug>.json`. POE2-PathOfCrafting then fetches it from:

```
https://raw.githubusercontent.com/<your-user>/POE2-Builds-Scraper/main/data/latest-runesofaldur.json
```

Set that URL as `BUILDS_ARTIFACT_URL` in the backend once you push this repo to GitHub.
For a bigger one-shot sample without the cron, the GGG-ladder roster (OAuth) can be added
behind the existing `RosterSource` protocol.

`--dump-raw` writes the first character JSON to `cache/sample_character.json` so you can
confirm the item field nesting on first use (see note in `extract.py`).

## Output

`build-stats-<league>-<version>.json`: `base_usage[]` (bases ranked by how many builds
use them, with rarity mix + common skills) and `mod_usage[]` (templated mod text per
base, ranked, with value samples). Mods are templated to the form the app keys on
(`"+# to maximum Mana"`); resolving them to the app's `mod_id`/`tier` happens at in-app
ingest (Phase 2), reusing the app's `ItemConverter`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Roster sources

Default: `roster/poeninja_search.py` (no auth). The `RosterSource` protocol
(`roster/base.py`) leaves room for a GGG-ladder source (OAuth `client_credentials`,
scope `service:leagues:ladder`) later, without changing the rest of the pipeline.

## Disclaimer

Not affiliated with or endorsed by Grinding Gear Games. Build data sourced from poe.ninja.
