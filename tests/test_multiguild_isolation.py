"""Core guild-scoped data must never leak between Discord servers. Run: pytest"""

import asyncio

from bot.db import Database


def run(coro_factory):
    return asyncio.run(coro_factory())


def test_events_settings_and_profiles_are_guild_scoped(tmp_path):
    async def go():
        db = Database(str(tmp_path / "multi.db"))
        await db.connect()

        await db.set_setting(1, "language", "en")
        await db.set_setting(2, "language", "fr")

        await db.add_character(1, 42, "Meilink", "Gladiator", "dps")
        await db.add_character(2, 42, "Ramzon", "Ranger", "dps")

        await db.create_event(
            message_id=1001,
            channel_id=11,
            guild_id=1,
            creator_id=42,
            creator_name="Meilink",
            title="Guild one",
            activity="Dungeon",
            compo="standard",
            size=5,
        )
        await db.create_event(
            message_id=2001,
            channel_id=22,
            guild_id=2,
            creator_id=42,
            creator_name="Meilink",
            title="Guild two",
            activity="Raid",
            compo="standard",
            size=10,
        )

        result = (
            await db.get_language(1),
            await db.get_language(2),
            [r["char_name"] for r in await db.get_profiles(1, 42)],
            [r["char_name"] for r in await db.get_profiles(2, 42)],
            [e["message_id"] for e in await db.get_open_events(1)],
            [e["message_id"] for e in await db.get_open_events(2)],
        )
        await db.close()
        return result

    assert run(go) == (
        "en",
        "fr",
        ["Meilink"],
        ["Ramzon"],
        [1001],
        [2001],
    )
