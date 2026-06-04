"""RosterSource protocol.

Default impl is poe.ninja's /search overview (no OAuth). A GGG-ladder impl (OAuth
client_credentials, scope service:leagues:ladder) can be added later behind this same
interface without touching the rest of the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..snapshot import Snapshot


@dataclass(frozen=True)
class RosterEntry:
    account: str  # poe.ninja form, e.g. "GuyThatDies-7619" (already #->- )
    character: str  # e.g. "GuyThatDies"
    extra: dict = field(default_factory=dict)  # class, level, etc. when available


@runtime_checkable
class RosterSource(Protocol):
    def fetch(self, snapshot: Snapshot, limit: int) -> list[RosterEntry]:
        """Return up to `limit` (account, character) pairs for the snapshot's league."""
        ...
