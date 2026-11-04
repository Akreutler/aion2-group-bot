"""Structured AION 2 event content and validation."""

from __future__ import annotations

from . import config


class EventCatalogError(ValueError):
    """Raised when an event's structured content is inconsistent."""


def _canonical(value: str | None, choices: tuple[str, ...]) -> str | None:
    if not value:
        return None
    wanted = value.strip().casefold()
    return next((choice for choice in choices if choice.casefold() == wanted), value.strip())


def content_choices(activity: str | None) -> tuple[str, ...]:
    if activity == "Expedition":
        return config.EXPEDITION_CONTENT
    if activity == "Sanctuary":
        return config.SANCTUARY_CONTENT
    return ()


def mode_choices(activity: str | None) -> tuple[str, ...]:
    return config.EXPEDITION_MODES if activity == "Expedition" else ()


def difficulty_choices(activity: str | None, mode: str | None) -> tuple[str, ...]:
    if activity == "Sanctuary":
        return config.DIFFICULTIES
    if activity == "Expedition" and mode == "Conquest":
        return config.DIFFICULTIES
    return ()


def normalize_event_details(
    *,
    activity: str,
    mode: str | None,
    content: str | None,
    difficulty: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Validate and normalize structured event metadata."""
    mode = _canonical(mode, config.EXPEDITION_MODES)
    content = _canonical(
        content, config.EXPEDITION_CONTENT + config.SANCTUARY_CONTENT
    )
    difficulty = _canonical(difficulty, config.DIFFICULTIES)

    if activity == "Expedition":
        if mode not in config.EXPEDITION_MODES:
            raise EventCatalogError("Expedition requires Exploration or Conquest.")
        if content not in config.EXPEDITION_CONTENT:
            raise EventCatalogError("Pick a valid Expedition instance.")
        if mode == "Exploration":
            if difficulty is not None:
                raise EventCatalogError("Exploration has no difficulty.")
            return mode, content, None
        if difficulty not in config.DIFFICULTIES:
            raise EventCatalogError("Conquest requires Normal or Hard.")
        return mode, content, difficulty

    if activity == "Sanctuary":
        if mode is not None:
            raise EventCatalogError("Sanctuary is separate from Expedition.")
        if content not in config.SANCTUARY_CONTENT:
            raise EventCatalogError("Pick a valid Sanctuary.")
        if difficulty not in config.DIFFICULTIES:
            raise EventCatalogError("Sanctuary requires Normal or Hard.")
        return None, content, difficulty

    if mode or content or difficulty:
        raise EventCatalogError(
            "Mode, content and difficulty only apply to Expedition or Sanctuary."
        )
    return None, None, None


def event_display_name(
    *,
    title: str | None,
    activity: str,
    content: str | None,
) -> str:
    """Use the selected instance as the default event title."""
    if title and title.strip():
        return title.strip()
    if content:
        return content
    return activity


def event_subtitle(event) -> str:
    """Human-readable structured PvE path for embeds."""
    try:
        mode = event["mode"]
    except (KeyError, IndexError):
        mode = None
    try:
        content = event["content"]
    except (KeyError, IndexError):
        content = None
    try:
        difficulty = event["difficulty"]
    except (KeyError, IndexError):
        difficulty = None

    bits = [event["activity"]]
    if mode:
        bits.append(mode)
    if content:
        bits.append(content)
    if difficulty:
        bits.append(difficulty)
    return " · ".join(bits)
