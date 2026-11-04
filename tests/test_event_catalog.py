"""Structured AION 2 event catalog behavior. Run: pytest"""

import pytest

from bot.event_catalog import (
    EventCatalogError,
    event_display_name,
    event_subtitle,
    normalize_event_details,
    normalize_stage,
)


def test_exploration_has_no_difficulty():
    mode, content, difficulty = normalize_event_details(
        activity="Expedition",
        mode="Exploration",
        content="Fire Temple",
        difficulty=None,
    )
    assert (mode, content, difficulty) == ("Exploration", "Fire Temple", None)


def test_conquest_requires_difficulty():
    with pytest.raises(EventCatalogError):
        normalize_event_details(
            activity="Expedition",
            mode="Conquest",
            content="Fire Temple",
            difficulty=None,
        )


def test_conquest_uses_same_expedition_instances():
    mode, content, difficulty = normalize_event_details(
        activity="Expedition",
        mode="conquest",
        content="vakron sky island",
        difficulty="hard",
    )
    assert (mode, content, difficulty) == (
        "Conquest",
        "Vakron Sky Island",
        "Hard",
    )


def test_sanctuary_is_separate_and_requires_difficulty():
    mode, content, difficulty = normalize_event_details(
        activity="Sanctuary",
        mode=None,
        content="abyssal forge: ludra",
        difficulty="normal",
    )
    assert (mode, content, difficulty) == (
        None,
        "Abyssal Forge: Ludra",
        "Normal",
    )


def test_sanctuary_rejects_expedition_mode():
    with pytest.raises(EventCatalogError):
        normalize_event_details(
            activity="Sanctuary",
            mode="Conquest",
            content="Abyssal Forge: Ludra",
            difficulty="Hard",
        )


def test_non_structured_events_reject_pve_metadata():
    with pytest.raises(EventCatalogError):
        normalize_event_details(
            activity="Raid",
            mode=None,
            content="Fire Temple",
            difficulty=None,
        )


def test_instance_becomes_default_title():
    assert (
        event_display_name(
            title=None,
            activity="Expedition",
            content="Fire Temple",
        )
        == "Fire Temple"
    )


def test_embed_subtitle_shows_full_conquest_path():
    event = {
        "activity": "Expedition",
        "mode": "Conquest",
        "content": "Draupnir",
        "difficulty": "Hard",
    }
    assert event_subtitle(event) == "Expedition · Conquest · Draupnir · Hard"


def test_embed_subtitle_shows_sanctuary_without_expedition_mode():
    event = {
        "activity": "Sanctuary",
        "mode": None,
        "content": "Abyssal Forge: Ludra",
        "difficulty": "Normal",
    }
    assert event_subtitle(event) == "Sanctuary · Abyssal Forge: Ludra · Normal"


def test_transcendence_uses_two_dungeons():
    for name in ("Deus Research Base", "Shattered Arkanis"):
        mode, content, difficulty = normalize_event_details(
            activity="Transcendence",
            mode=None,
            content=name,
            difficulty=None,
        )
        assert (mode, content, difficulty) == (None, name, None)


def test_transcendence_requires_stage_1_to_4():
    assert normalize_stage("Transcendence", 1) == 1
    assert normalize_stage("Transcendence", 4) == 4
    with pytest.raises(EventCatalogError):
        normalize_stage("Transcendence", None)
    with pytest.raises(EventCatalogError):
        normalize_stage("Transcendence", 5)


def test_stage_is_rejected_outside_transcendence():
    with pytest.raises(EventCatalogError):
        normalize_stage("Expedition", 2)


def test_transcendence_subtitle_uses_stage_not_difficulty():
    event = {
        "activity": "Transcendence",
        "mode": None,
        "content": "Shattered Arkanis",
        "difficulty": None,
        "stage": 4,
    }
    assert event_subtitle(event) == "Transcendence · Shattered Arkanis · Stage 4"
