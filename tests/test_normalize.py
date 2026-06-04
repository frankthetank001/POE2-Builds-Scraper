"""Markup stripping + value templating, incl. the cases the app's own normalizer misses."""

import pytest

from builds_scraper.normalize import extract_values, normalize_mod, strip_markup

CASES = [
    # poe.ninja raw -> app-style template
    ("Adds 21 to 35 [Cold] damage to [Attack|Attacks]", "Adds # to # Cold damage to Attacks"),
    ("+77 to maximum Mana", "+# to maximum Mana"),
    ("15% increased [Attack] Speed", "#% increased Attack Speed"),
    ("+40% to [Resistances|Fire Resistance]", "+#% to Fire Resistance"),
    ("[LifeLeech|Leech] 9.9% of [Physical] [Attack] Damage as Life",
     "Leech #% of Physical Attack Damage as Life"),
    ("+18% to [Resistances|Cold Resistance]", "+#% to Cold Resistance"),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_normalize_mod(raw, expected):
    assert normalize_mod(raw) == expected


def test_strip_markup_pipe_and_plain():
    assert strip_markup("[Attack|Attacks]") == "Attacks"
    assert strip_markup("[Cold]") == "Cold"


def test_extract_values():
    assert extract_values("Adds 21 to 35 [Cold] damage to [Attack|Attacks]") == [21, 35]
    assert extract_values("9.9% of Damage") == [9.9]
