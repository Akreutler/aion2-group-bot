"""Async client for AION 2's public PLAYNC character endpoints.

These are the same public endpoints used by the official character page.  The
bot keeps this client deliberately small so a future PLAYNC API change is
isolated here instead of leaking through Discord commands and database code.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass

import aiohttp


SEARCH_URL = "https://api-search.plaync.com/aion2global/search/v2/character"
INFO_URL = "https://aion2.plaync.com/api/character/info"
SERVERS_URL = "https://aion2.plaync.com/en-us/api/gameinfo/servers"

_TAG_RE = re.compile(r"<[^>]+>")


class PlayNCError(RuntimeError):
    """Raised when PLAYNC cannot return usable public character data."""


@dataclass(frozen=True)
class Server:
    region: str
    race_id: int
    server_id: int
    name: str

    @property
    def value(self) -> str:
        return f"{self.region}:{self.race_id}:{self.server_id}"


@dataclass(frozen=True)
class Character:
    character_id: str
    name: str
    char_class: str
    level: int
    race_id: int
    race_name: str
    server_id: int
    server_name: str
    combat_power: int
    item_level: int
    title_name: str | None
    profile_image: str | None
    region: str


class PlayNCClient:
    """Small cached client around PLAYNC's public character pages."""

    def __init__(self) -> None:
        self._servers: dict[str, tuple[float, list[Server]]] = {}

    async def _json(self, url: str, *, params: dict) -> dict:
        timeout = aiohttp.ClientTimeout(total=8)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Kisk-AION2-Discord-Bot/1.0",
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        raise PlayNCError(
                            f"PLAYNC returned HTTP {response.status} for {response.url}"
                        )
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise PlayNCError("PLAYNC request failed") from exc
        if not isinstance(payload, dict):
            raise PlayNCError("PLAYNC returned an unexpected response")
        return payload

    async def servers(self, region: str = "eu") -> list[Server]:
        region = region.lower()
        cached = self._servers.get(region)
        now = time.monotonic()
        if cached and now - cached[0] < 3600:
            return cached[1]

        payload = await self._json(
            SERVERS_URL,
            params={"lang": "en-US", "region": region},
        )
        rows = payload.get("serverList") or []
        result = [
            Server(
                region=region,
                race_id=int(row["raceId"]),
                server_id=int(row["serverId"]),
                name=str(row["serverName"]),
            )
            for row in rows
            if row.get("raceId") is not None
            and row.get("serverId") is not None
            and row.get("serverName")
        ]
        self._servers[region] = (now, result)
        return result

    async def find_character(
        self,
        *,
        name: str,
        region: str,
        race_id: int,
        server_id: int,
    ) -> tuple[str, str]:
        payload = await self._json(
            SEARCH_URL,
            params={
                "keyword": name,
                "race": race_id,
                "serverId": server_id,
                "page": 1,
                "size": 30,
                "region": region,
                "localeInfo": "en-US",
            },
        )
        wanted = name.casefold()
        for row in payload.get("list") or []:
            clean_name = html.unescape(_TAG_RE.sub("", str(row.get("name") or "")))
            if clean_name.casefold() == wanted:
                character_id = row.get("characterId")
                if character_id:
                    # Search returns the id URL-encoded while /info accepts the
                    # encoded form directly as a query parameter value.
                    return str(character_id), clean_name
        raise PlayNCError(f"Character {name!r} was not found on that server")

    async def character(
        self,
        *,
        name: str,
        region: str,
        race_id: int,
        server_id: int,
    ) -> Character:
        character_id, _ = await self.find_character(
            name=name,
            region=region,
            race_id=race_id,
            server_id=server_id,
        )
        payload = await self._json(
            INFO_URL,
            params={
                "region": region,
                "lang": "en-US",
                "characterId": character_id,
                "serverId": server_id,
            },
        )
        profile = payload.get("profile") or {}
        stat_list = (payload.get("stat") or {}).get("statList") or []
        item_level = next(
            (
                int(stat.get("value") or 0)
                for stat in stat_list
                if stat.get("type") == "ItemLevel"
            ),
            0,
        )
        if not profile.get("characterName") or not profile.get("className"):
            raise PlayNCError("PLAYNC returned an incomplete character profile")

        return Character(
            character_id=str(profile.get("characterId") or character_id),
            name=str(profile["characterName"]),
            char_class=str(profile["className"]),
            level=int(profile.get("characterLevel") or 0),
            race_id=int(profile.get("raceId") or race_id),
            race_name=str(profile.get("raceName") or ""),
            server_id=int(profile.get("serverId") or server_id),
            server_name=str(profile.get("serverName") or ""),
            combat_power=int(profile.get("combatPower") or 0),
            item_level=item_level,
            title_name=profile.get("titleName"),
            profile_image=profile.get("profileImage"),
            region=region,
        )
