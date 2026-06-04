"""Roster from poe.ninja's builds /search overview (protobuf, no auth).

GET /poe2/api/builds/{version}/search?overview={snapshotName}
  -> application/x-protobuf: a columnar result table.

Structure (reverse-engineered from a live capture, see tests/fixtures + protobuf_decode):
  root .1                      = result message
       .1.5  (repeated)        = one block per column
            .5.1               = column key   (e.g. "name", "account", "class")
            .5.2.1 (repeated)  = the column's string values, in row order

`name` and `account` are string columns and align 1:1 by row, so zip() gives the roster.
`account` is already in poe.ninja's "Name-1234" form (no #->- transform needed).
"""

from __future__ import annotations

import logging

from ..protobuf_decode import fields, parse
from ..snapshot import Snapshot
from .base import RosterEntry

logger = logging.getLogger(__name__)

# Columns we lift out of the table. name/account drive the roster; the rest is metadata.
_WANT = ("name", "account", "class", "level")


def decode_search_columns(payload: bytes) -> dict[str, list[str]]:
    """Decode the /search protobuf into {column_key: [string values...]}."""
    root = parse(payload)
    top = fields(root, 1)
    if not top or not isinstance(top[0], list):
        raise ValueError("unexpected /search payload: no field .1 message")
    table = top[0]

    columns: dict[str, list[str]] = {}
    for block in fields(table, 5):
        if not isinstance(block, list):
            continue
        keys = [v for v in fields(block, 1) if isinstance(v, str)]
        if not keys:
            continue
        key = keys[0]
        values: list[str] = []
        for container in fields(block, 2):
            if isinstance(container, list):
                values += [v for v in fields(container, 1) if isinstance(v, str)]
        columns[key] = values
    return columns


def roster_from_columns(columns: dict[str, list[str]], limit: int) -> list[RosterEntry]:
    names = columns.get("name", [])
    accounts = columns.get("account", [])
    classes = columns.get("class", [])
    levels = columns.get("level", [])
    if not names or not accounts:
        raise ValueError(f"missing name/account columns; got keys {list(columns)}")
    if len(names) != len(accounts):
        logger.warning(
            "name/account column lengths differ (%d vs %d); zipping to the shorter",
            len(names), len(accounts),
        )
    out: list[RosterEntry] = []
    for i, (acct, char) in enumerate(zip(accounts, names)):
        extra: dict = {}
        if i < len(classes):
            extra["class"] = classes[i]
        if i < len(levels):
            extra["level"] = levels[i]
        out.append(RosterEntry(account=acct, character=char, extra=extra))
        if len(out) >= limit:
            break
    return out


class PoeNinjaSearchRoster:
    def __init__(self, client):
        self.client = client

    def fetch(self, snapshot: Snapshot, limit: int) -> list[RosterEntry]:
        url = f"{self.client.settings.poeninja_base}/builds/{snapshot.version}/search"
        resp = self.client.get(url, params={"overview": snapshot.snapshot_name})
        resp.raise_for_status()
        columns = decode_search_columns(resp.content)
        roster = roster_from_columns(columns, limit)
        logger.info("roster: %d builds from /search", len(roster))
        return roster
