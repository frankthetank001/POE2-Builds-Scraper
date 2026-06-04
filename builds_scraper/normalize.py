"""Turn a raw poe.ninja mod string into the template form POE2-PathOfCrafting keys on.

poe.ninja gives, e.g.::

    "Adds 21 to 35 [Cold] damage to [Attack|Attacks]"

The app stores mods templated, e.g. "Adds # to # Cold damage to Attacks". Two steps:

1. Strip PoE display markup: "[a|b]" -> "b"   (show the display half),  "[a]" -> "a".
2. Replace every numeric literal with "#".

NOTE: this is intentionally NOT the app's own `_normalize_stat_text`
(pob_data_loader.py:629). That one only templates "(X-Y)" ranges / signed / percent
values, so it would leave poe.ninja's bare "21 to 35" untouched. We need an
all-numbers->"#" rule to land on the same template the app derives from its ModItem.json.
"""

from __future__ import annotations

import re

_MARKUP_PIPE = re.compile(r"\[([^\]|]+)\|([^\]]+)\]")  # [internal|Display] -> Display
_MARKUP_PLAIN = re.compile(r"\[([^\]]+)\]")  # [Cold] -> Cold
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WS = re.compile(r"\s+")


def strip_markup(s: str) -> str:
    s = _MARKUP_PIPE.sub(r"\2", s)
    s = _MARKUP_PLAIN.sub(r"\1", s)
    return s


def template_values(s: str) -> str:
    return _NUMBER.sub("#", s)


def normalize_mod(s: str) -> str:
    """Markup-free, value-templated, whitespace-collapsed mod text."""
    s = strip_markup(s)
    s = template_values(s)
    return _WS.sub(" ", s).strip()


def extract_values(s: str) -> list[float]:
    """The concrete rolled numbers from a (markup-stripped) mod string, for tier work."""
    out: list[float] = []
    for m in _NUMBER.finditer(strip_markup(s)):
        v = float(m.group())
        out.append(int(v) if v.is_integer() else v)
    return out
