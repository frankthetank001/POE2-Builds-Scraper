"""Validate roster extraction against a real captured /search payload (offline)."""

import re
from pathlib import Path

from builds_scraper.roster.poeninja_search import decode_search_columns, roster_from_columns
from builds_scraper.snapshot import load_snapshot_from_index_state_json

FIXTURES = Path(__file__).parent / "fixtures"
ACCT_RE = re.compile(r"^[A-Za-z0-9_]+-\d{3,6}$")


def _payload() -> bytes:
    return (FIXTURES / "search_runesofaldur.pb").read_bytes()


def test_columns_present_and_aligned():
    cols = decode_search_columns(_payload())
    assert "name" in cols and "account" in cols
    assert len(cols["name"]) == len(cols["account"]) == 100


def test_accounts_in_poeninja_form():
    cols = decode_search_columns(_payload())
    # The vast majority should already be "Name-1234"; a few may be plain (no discriminator).
    matched = sum(1 for a in cols["account"] if ACCT_RE.match(a))
    assert matched >= 90


def test_roster_zips_account_to_character():
    roster = roster_from_columns(decode_search_columns(_payload()), limit=100)
    assert len(roster) == 100
    assert all(e.account and e.character for e in roster)
    # spot-check a known pair from the capture
    first = roster[0]
    assert first.account == "heygyus-0416"
    assert first.character == "ResurrectGodAura"


def test_limit_is_respected():
    roster = roster_from_columns(decode_search_columns(_payload()), limit=10)
    assert len(roster) == 10


def test_snapshot_from_index_state_fixture():
    snap = load_snapshot_from_index_state_json(str(FIXTURES / "index-state.json"), "runesofaldur")
    assert snap.snapshot_name == "runes-of-aldur"
    assert re.match(r"^\d{4}-\d{8}-\d+$", snap.version)
