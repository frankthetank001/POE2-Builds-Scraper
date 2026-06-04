"""Offline tests for the builds-browser trim/sample pipeline against a real character fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from builds_scraper.build_sample import sample_builds
from builds_scraper.build_trim import (
    decode_pob_classes,
    poeninja_character_url,
    trim_build,
)
from builds_scraper.models import Build, BuildsArtifact

FIXTURE = Path(__file__).parent / "fixtures" / "character_sample.json"


@pytest.fixture(scope="module")
def character() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def build(character: dict) -> Build:
    b = trim_build(character, "runesofaldur")
    assert b is not None
    return b


def test_identity_and_links(build: Build):
    assert build.id == "heygyus-0416__ResurrectGodAura"
    assert build.account == "heygyus-0416"
    assert build.character == "ResurrectGodAura"
    assert build.level == 99
    assert build.poeninja_url == (
        "https://poe.ninja/poe2/builds/runesofaldur/character/heygyus-0416/ResurrectGodAura"
    )
    assert build.pob_export and len(build.pob_export) > 1000  # PoB code inlined


def test_pob_class_decode(build: Build):
    # poe.ninja `class` is the ASCENDANCY; base class comes from the decoded PoB export.
    assert build.base_class == "Monk"
    assert build.ascendancy == "Martial Artist"


def test_decode_pob_classes_handles_garbage():
    assert decode_pob_classes(None) == (None, None)
    assert decode_pob_classes("not-a-valid-pob-code") == (None, None)


def test_main_skill_is_highest_dps(build: Build):
    # The old main_skills() always returned []; selection must be by precomputed DPS, so the
    # real damage skill (Twister) wins over the trivial first-listed skill (Hollow Focus, dps 84).
    assert build.main_skills, "expected at least one main skill"
    assert build.main_skills[0].name == "Twister"
    assert build.main_skills[0].dps == 98238
    assert build.main_skills[0].supports  # support gems captured
    # Sorted by DPS descending.
    dps = [s.dps for s in build.main_skills]
    assert dps == sorted(dps, reverse=True)


def test_defense_summary(build: Build):
    d = build.defense
    assert d.life == 1394
    assert d.energy_shield == 2085
    assert d.ehp == 16373
    assert d.chaos_res == 66


def test_items_extracted_without_rune_currency(build: Build):
    # 16 raw items include 5 socketed-rune "currency" lines (inventoryId Chakra) -> 11 equipped.
    assert len(build.items) == 11
    slots = [it.slot for it in build.items]
    assert "ring" in slots and "amulet" in slots and "body_armour" in slots
    # No rune-currency leaked in as gear.
    assert all(it.rarity in ("normal", "magic", "rare", "unique") for it in build.items)


def test_item_mods_markup_stripped_with_values(build: Build):
    ring = next(it for it in build.items if it.name == "The Taming")
    res_mod = next(m for m in ring.mods if "all Elemental Resistances" in m.text)
    assert res_mod.text == "+24% to all Elemental Resistances"  # markup stripped, number kept
    assert res_mod.values == [24.0]
    assert res_mod.origin == "explicit"
    assert "[" not in res_mod.text and "]" not in res_mod.text


def test_socketed_runes_captured(build: Build):
    helm = next(it for it in build.items if it.slot == "helmet")
    assert any("Rune" in r for r in helm.runes)


def test_sample_dedupes_and_caps(build: Build):
    # Duplicate the same build many times across two ascendancies; sampling dedupes by id.
    dupes = [build] * 5
    sampled = sample_builds(dupes, target=30)
    assert len(sampled) == 1  # all share one id

    # A spread across ascendancies stays balanced and capped.
    many = []
    for i in range(50):
        b = build.model_copy(update={"id": f"acc{i}__char{i}", "account": f"acc{i}",
                                     "ascendancy": ["Titan", "Deadeye", "Invoker"][i % 3]})
        many.append(b)
    sampled = sample_builds(many, target=12)
    assert len(sampled) == 12
    classes = {b.ascendancy for b in sampled}
    assert len(classes) == 3  # round-robin pulled from every ascendancy


def test_artifact_roundtrips(build: Build):
    art = BuildsArtifact(
        league="Runes of Aldur", league_slug="runesofaldur", snapshot_version="v",
        snapshot_name="snap", scraped_at="2026-06-04T00:00:00+00:00",
        sample_size=1, roster_size=1, builds=[build],
    )
    dumped = art.model_dump_json()
    again = BuildsArtifact.model_validate_json(dumped)
    assert again.builds[0].id == build.id
    assert again.disclaimer  # default disclaimer present


def test_poeninja_url_encodes():
    url = poeninja_character_url("runesofaldur", "Name-1234", "My Char")
    assert "My%20Char" in url
