"""/profile commands and /roster: the legion's character directory.

A member registers as many characters as they like (up to MAX_CHARACTERS);
exactly one of them is their main, and that is the one the bot falls back on
whenever a character isn't named explicitly.
"""

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import config, i18n
from ..branding import brand
from ..embeds import ROLE_EMOJI, ROLE_LABEL
from ..logic import MAX_CHARACTERS, ROLES
from ..plaync import PlayNCClient, PlayNCError
from ..utils.permissions import member_is_admin

# The playable classes, taken from the emoji configuration so that adding one
# (Fist Fighter, on release) is a single line in config.py. This is the whole
# list a member may pick from, in the slash command as in the onboarding form.
AION_CLASSES = list(config.CLASS_EMOJI)

# Discord caps a choice list at 25; the class list is far shorter, so it fits
# whole and needs no paging.
CLASS_CHOICES = [app_commands.Choice(name=name, value=name) for name in AION_CLASSES]

ALL_CHARACTERS = "all"

# How many absentees one pruning pass will confirm against the API. A member
# missing from the cache is almost always someone who left, but a guild whose
# cache never filled would put every profile in that bucket, so the work is
# spread over successive passes rather than fired off at once.
PRUNE_BATCH = 25

log = logging.getLogger(__name__)


def _target_of(interaction: discord.Interaction):
    """Whose characters a command is about: the `member` option, or the caller."""
    return getattr(interaction.namespace, "member", None) or interaction.user


async def _character_choices(interaction: discord.Interaction, current: str):
    target = _target_of(interaction)
    rows = await interaction.client.db.get_profiles(interaction.guild_id, target.id)
    cur = current.lower()
    return [
        app_commands.Choice(
            name=f"{'⭐ ' if row['is_main'] else ''}{row['char_name']} "
            f"({row['char_class']})"[:100],
            value=str(row["id"]),
        )
        for row in rows
        if cur in row["char_name"].lower()
    ]


async def character_autocomplete(interaction: discord.Interaction, current: str):
    return (await _character_choices(interaction, current))[:25]


async def plaync_server_autocomplete(
    interaction: discord.Interaction, current: str
):
    """Official EU server/race choices from PLAYNC.

    The value encodes region, race and server id so the slash command does not
    have to trust a free-text server name.
    """
    client = getattr(interaction.client, "plaync", None)
    if client is None:
        return []
    try:
        servers = await client.servers("eu")
    except PlayNCError:
        return []
    cur = current.casefold()
    race_label = {1: "Elyos", 2: "Asmodian"}
    choices = []
    for server in servers:
        label = f"{race_label.get(server.race_id, server.race_id)} · {server.name}"
        if cur and cur not in label.casefold():
            continue
        choices.append(app_commands.Choice(name=label[:100], value=server.value))
        if len(choices) == 25:
            break
    return choices


async def deletable_autocomplete(interaction: discord.Interaction, current: str):
    """Same list, with "everything" as the first entry."""
    lang = await i18n.resolve_lang(interaction.client.db, interaction.guild)
    choices = [
        app_commands.Choice(
            name=i18n.t("profile.every_character", lang), value=ALL_CHARACTERS
        )
    ] + await _character_choices(interaction, current)
    return choices[:25]


async def resolve_character(db, guild_id: int, user_id: int, value: str):
    """The character an option refers to: the id an autocomplete choice
    carries, or a name typed out by hand. None when it matches nothing."""
    value = value.strip()
    if value.isdigit():
        row = await db.get_character(guild_id, user_id, int(value))
        if row is not None:
            return row
    for row in await db.get_profiles(guild_id, user_id):
        if row["char_name"].lower() == value.lower():
            return row
    return None


def _roster_order(entry) -> tuple:
    """Roster order: role first, then class, then character name.

    Keyed on the member's main, the character the roster line shows. Sorting
    by role first lines the roster up as tanks, then heals, then DPS — the
    question a legion actually asks it. A role that isn't one of the three
    (data from a future version) sorts last rather than raising.
    """
    main = entry[1][0]
    rank = ROLES.index(main["role"]) if main["role"] in ROLES else len(ROLES)
    return (rank, main["char_class"].lower(), main["char_name"].lower())


def character_line(row, *, star: bool = True) -> str:
    """One compact roster/profile line, enriched when PLAYNC data is linked."""
    emoji = config.CLASS_EMOJI.get(row["char_class"])
    char_class = f"{emoji} {row['char_class']}" if emoji else row["char_class"]
    prefix = "⭐ " if star and row["is_main"] else ""
    line = f"{prefix}{ROLE_EMOJI[row['role']]} **{row['char_name']}** ({char_class})"
    if row["combat_power"] is not None or row["item_level"] is not None:
        bits = []
        if row["combat_power"] is not None:
            bits.append(f"{row['combat_power']:,} AP")
        if row["item_level"] is not None:
            bits.append(f"{row['item_level']:,} GS")
        line += " · " + " · ".join(bits)
    return line


def character_detail_line(row) -> str:
    """Detailed profile view for one character."""
    line = character_line(row)
    meta = []
    if row["race_name"]:
        meta.append(row["race_name"])
    if row["server_name"]:
        meta.append(row["server_name"])
    if row["character_level"] is not None:
        meta.append(f"Lv. {row['character_level']}")
    if meta:
        line += "\n  ↳ " + " · ".join(meta)
    if row["title_name"]:
        line += f"\n  🏅 *{row['title_name']}*"
    return line


@app_commands.guild_only()
class Profile(commands.GroupCog, name="profile"):
    """Register and browse the members' characters."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "plaync"):
            bot.plaync = PlayNCClient()
        super().__init__()

    async def cog_load(self):
        self.prune_departed.start()

    async def cog_unload(self):
        self.prune_departed.cancel()

    @app_commands.command(
        name="add", description="Add or update a character from the official AION 2 profile"
    )
    @app_commands.describe(
        name="Exact in-game character name",
        server="Server and faction (pick a suggestion)",
        role="Its party role",
        main="Make it your main character (your first one always is)",
    )
    @app_commands.autocomplete(server=plaync_server_autocomplete)
    @app_commands.choices(
        role=[
            app_commands.Choice(name="🛡️ Tank", value="tank"),
            app_commands.Choice(name="💚 Heal", value="heal"),
            app_commands.Choice(name="🗡️ DPS", value="dps"),
        ],
    )
    async def add(
        self,
        interaction: discord.Interaction,
        name: app_commands.Range[str, 1, 32],
        server: str,
        role: app_commands.Choice[str],
        main: bool = False,
    ):
        lang = await i18n.resolve_lang(self.bot.db, interaction.guild)
        characters = await self.bot.db.get_profiles(
            interaction.guild_id, interaction.user.id
        )
        known = {row["char_name"].lower() for row in characters}
        if name.strip().lower() not in known and len(characters) >= MAX_CHARACTERS:
            await interaction.response.send_message(
                i18n.t("profile.cap_reached", lang, max=MAX_CHARACTERS),
                ephemeral=True,
            )
            return

        try:
            region, race_raw, server_raw = server.split(":", 2)
            race_id, server_id = int(race_raw), int(server_raw)
        except (ValueError, AttributeError):
            await interaction.response.send_message(
                "Pick a server from the autocomplete list.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            official = await self.bot.plaync.character(
                name=name.strip(),
                region=region,
                race_id=race_id,
                server_id=server_id,
            )
        except PlayNCError as exc:
            await interaction.followup.send(
                f"❌ Could not find that character on PLAYNC: {exc}",
                ephemeral=True,
            )
            return

        character_id = await self.bot.db.add_character(
            interaction.guild_id,
            interaction.user.id,
            official.name,
            official.char_class,
            role.value,
            make_main=main,
        )
        await self.bot.db.update_plaync_character(
            character_id,
            plaync_character_id=official.character_id,
            region=official.region,
            race_id=official.race_id,
            race_name=official.race_name,
            server_id=official.server_id,
            server_name=official.server_name,
            character_level=official.level,
            combat_power=official.combat_power,
            item_level=official.item_level,
            title_name=official.title_name,
            profile_image=official.profile_image,
            updated_at=int(time.time()),
        )

        detail = (
            f"{ROLE_EMOJI[role.value]} **{official.name}** "
            f"({official.char_class}, {ROLE_LABEL[role.value]})\n"
            f"{official.race_name} · {official.server_name} · Lv. {official.level}\n"
            f"⚔️ {official.combat_power:,} AP · 🛡️ {official.item_level:,} GS"
        )
        was_first = not characters
        note = i18n.t(
            "profile.note_main" if main or was_first else "profile.note_alt", lang
        )
        await interaction.followup.send(
            f"✅ Added from PLAYNC\n{detail}\n{note}", ephemeral=True
        )

    @app_commands.command(
        name="refresh", description="Refresh a linked character from PLAYNC"
    )
    @app_commands.describe(character="The linked character to refresh")
    @app_commands.autocomplete(character=character_autocomplete)
    async def refresh(self, interaction: discord.Interaction, character: str):
        lang = await i18n.resolve_lang(self.bot.db, interaction.guild)
        row = await resolve_character(
            self.bot.db, interaction.guild_id, interaction.user.id, character
        )
        if row is None:
            await interaction.response.send_message(
                i18n.t("profile.main_not_found", lang, character=character),
                ephemeral=True,
            )
            return
        if not row["plaync_character_id"] or not row["region"] or not row["server_id"]:
            await interaction.response.send_message(
                "This character is not linked to PLAYNC yet. Use /profile add first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            official = await self.bot.plaync.character_by_id(
                character_id=row["plaync_character_id"],
                region=row["region"],
                server_id=row["server_id"],
                race_id=row["race_id"] or 0,
            )
        except PlayNCError as exc:
            await interaction.followup.send(
                f"❌ Could not refresh from PLAYNC: {exc}", ephemeral=True
            )
            return

        await self.bot.db.update_plaync_character(
            row["id"],
            plaync_character_id=official.character_id,
            region=official.region,
            race_id=official.race_id,
            race_name=official.race_name,
            server_id=official.server_id,
            server_name=official.server_name,
            character_level=official.level,
            combat_power=official.combat_power,
            item_level=official.item_level,
            title_name=official.title_name,
            profile_image=official.profile_image,
            updated_at=int(time.time()),
        )
        await interaction.followup.send(
            f"✅ Refreshed **{official.name}** · "
            f"{official.combat_power:,} AP · {official.item_level:,} GS",
            ephemeral=True,
        )

    @app_commands.command(
        name="main", description="Choose which of your characters is your main"
    )
    @app_commands.describe(character="The character to promote")
    @app_commands.autocomplete(character=character_autocomplete)
    async def main(self, interaction: discord.Interaction, character: str):
        lang = await i18n.resolve_lang(self.bot.db, interaction.guild)
        row = await resolve_character(
            self.bot.db, interaction.guild_id, interaction.user.id, character
        )
        if row is None:
            await interaction.response.send_message(
                i18n.t("profile.main_not_found", lang, character=character),
                ephemeral=True,
            )
            return

        await self.bot.db.set_main_character(
            interaction.guild_id, interaction.user.id, row["id"]
        )
        await interaction.response.send_message(
            i18n.t("profile.main_set", lang, name=row["char_name"]), ephemeral=True
        )

    @app_commands.command(name="show", description="See a member's profile")
    @app_commands.describe(member="The member to look up (empty = you)")
    async def show(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ):
        lang = await i18n.resolve_lang(self.bot.db, interaction.guild)
        target = member or interaction.user
        is_self = target == interaction.user
        characters = await self.bot.db.get_profiles(interaction.guild_id, target.id)
        if not characters:
            key = "profile.show_none_self" if is_self else "profile.show_none_other"
            await interaction.response.send_message(
                i18n.t(key, lang, name=target.display_name),
                ephemeral=True,
            )
            return

        title = (
            i18n.t("profile.show_title_self", lang)
            if is_self
            else i18n.t("profile.show_title_other", lang, name=target.display_name)
        )
        embed = discord.Embed(
            title=title,
            description="\n\n".join(character_detail_line(row) for row in characters),
            colour=discord.Colour.blurple(),
        )
        brand(embed)
        embed.set_footer(text=i18n.t("profile.show_footer", lang, n=len(characters)))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="delete", description="Delete one character, or your whole profile"
    )
    @app_commands.describe(
        character="Which character to remove (empty = every one of them)",
        member="Moderators only: whose profile to delete (default: yours)",
    )
    @app_commands.autocomplete(character=deletable_autocomplete)
    async def delete(
        self,
        interaction: discord.Interaction,
        character: str | None = None,
        member: discord.Member | None = None,
    ):
        lang = await i18n.resolve_lang(self.bot.db, interaction.guild)
        target = member or interaction.user
        is_self = target == interaction.user
        if not is_self and not await member_is_admin(self.bot.db, interaction.user):
            await interaction.response.send_message(
                i18n.t("profile.delete_mod_only", lang), ephemeral=True
            )
            return

        row = None
        if character is not None and character != ALL_CHARACTERS:
            row = await resolve_character(
                self.bot.db, interaction.guild_id, target.id, character
            )
            if row is None:
                key = (
                    "profile.delete_not_found_self"
                    if is_self
                    else "profile.delete_not_found_other"
                )
                await interaction.response.send_message(
                    i18n.t(key, lang, name=target.display_name, character=character),
                    ephemeral=True,
                )
                return

        count = await self.bot.db.delete_profile(
            interaction.guild_id, target.id, None if row is None else row["id"]
        )
        if count == 0:
            key = "profile.delete_none_self" if is_self else "profile.delete_none_other"
            await interaction.response.send_message(
                i18n.t(key, lang, name=target.display_name), ephemeral=True
            )
            return

        if row is None:
            key = (
                "profile.deleted_self_profile"
                if is_self
                else "profile.deleted_other_profile"
            )
            message = i18n.t(key, lang, name=target.display_name, count=count)
        else:
            key = (
                "profile.deleted_self_char" if is_self else "profile.deleted_other_char"
            )
            message = i18n.t(key, lang, name=target.display_name, char=row["char_name"])
        await interaction.response.send_message(message, ephemeral=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """When a member leaves (or is kicked/banned), forget their data."""
        if member.bot:
            return
        await self.bot.db.purge_member(member.guild.id, member.id)

    # ----- Catching the departures the listener missed -----

    @tasks.loop(hours=24)
    async def prune_departed(self):
        """Forgets members who left while the bot wasn't there to see it.

        on_member_remove only fires while the bot is connected, so anyone who
        left during a restart — or before that listener existed — keeps their
        characters on the roster forever. This runs once at startup and daily
        after that, and cleans them up.

        Deleting from a cold cache would wipe every profile on the server, so
        a member missing from it is never trusted: only an explicit 404 from
        the API counts as proof they are gone. Anything else (a network blip,
        a rate limit) leaves the profile alone for the next pass.
        """
        for guild in self.bot.guilds:
            checked = 0
            for user_id in await self.bot.db.profile_user_ids(guild.id):
                if guild.get_member(user_id) is not None:
                    continue
                if checked >= PRUNE_BATCH:
                    break
                checked += 1
                try:
                    await guild.fetch_member(user_id)
                except discord.NotFound:
                    await self.bot.db.purge_member(guild.id, user_id)
                    log.info(
                        "Purged %s: no longer a member of %s (%s)",
                        user_id,
                        guild.name,
                        guild.id,
                    )
                except discord.HTTPException:
                    continue

    @prune_departed.before_loop
    async def _wait_ready(self):
        # Guilds are chunked by the time the bot is ready (the members intent
        # is on), so the member cache is trustworthy for the cheap check.
        await self.bot.wait_until_ready()


@app_commands.guild_only()
class Roster(commands.Cog):
    """The /roster command, kept top-level for quick access."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="roster", description="The legion's character roster")
    async def roster(self, interaction: discord.Interaction):
        lang = await i18n.resolve_lang(self.bot.db, interaction.guild)
        characters = await self.bot.db.all_profiles(interaction.guild_id)
        if not characters:
            await interaction.response.send_message(
                i18n.t("roster.empty", lang),
                ephemeral=True,
            )
            return

        # Group each member's characters (rows arrive main first, then by
        # class, then by name).
        by_member: dict[int, list] = {}
        for row in characters:
            by_member.setdefault(row["user_id"], []).append(row)

        lines = []
        for user_id, chars in sorted(by_member.items(), key=_roster_order):
            line = f"• <@{user_id}>: {character_line(chars[0], star=False)}"
            if len(chars) > 1:
                alts = ", ".join(row["char_name"] for row in chars[1:])
                line += i18n.t("roster.alts", lang, alts=alts)
            lines.append(line)

        # Safety margin under Discord's 4096-character description limit.
        text = "\n".join(lines)
        if len(text) > 3900:
            text = text[:3900] + "\n…"

        embed = discord.Embed(
            title=i18n.t(
                "roster.title",
                lang,
                members=len(by_member),
                chars=len(characters),
            ),
            description=text,
            colour=discord.Colour.blurple(),
        )
        brand(embed)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
    await bot.add_cog(Roster(bot))
