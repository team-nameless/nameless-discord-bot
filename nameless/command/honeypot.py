from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from nameless.custom.cache import nameless_cache
from nameless.db import db
from nameless.db.repositories import GuildRepository
from nameless.utils import create_cache_key

if TYPE_CHECKING:
    from nameless import Nameless

__all__ = ["HoneypotCommand"]


class HoneypotCommand(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot: Nameless = bot

    def _create_honeypot_cache_key(self, this_guild: discord.Guild) -> str:
        """Create honeypot cache key."""
        return create_cache_key("honeypot", str(this_guild.id))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        assert message.author is not None
        assert message.guild is not None
        assert message.channel is not None
        assert self.bot.user is not None

        if not nameless_cache.get_key(self._create_honeypot_cache_key(message.guild)):
            return

        # don't ban self, let admin do it.
        if message.author.id == self.bot.user.id:
            return

        assert isinstance(message.author, discord.Member)

        async with db.get_session_context() as session, GuildRepository(session) as guild_repo:
            db_guild = await guild_repo.get_or_create(pk_id=message.guild.id)

        if message.channel.id == db_guild.HoneypotChannelId:
            with contextlib.suppress(discord.errors.Forbidden):
                await message.author.ban(
                    delete_message_days=0,
                    reason="Chat in spam bait channel.",
                )

    @commands.hybrid_group(fallback="activate")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def honeypot(self, ctx: commands.Context[Nameless]):
        """Create a spam-bait channel."""
        await ctx.defer()

        assert ctx.guild is not None

        async with db.get_session_context() as session, GuildRepository(session) as guild_repo:
            await guild_repo.get_or_create(pk_id=ctx.guild.id)

        if nameless_cache.get_key(self._create_honeypot_cache_key(ctx.guild)):
            await ctx.send("You already activated the honeypot.")
            return

        created_channel = await ctx.guild.create_text_channel("spam-goes-here", reason="Spam-bait activation.")

        await created_channel.send("# DO NOT TEXT IN HERE, YOU WILL BE BANNED.")

        async with db.get_session_context() as session:
            guild_repo = GuildRepository(session)
            await guild_repo.update(
                ctx.guild.id,
                {"HoneypotChannelId": created_channel.id},
            )

        nameless_cache.set_key(self._create_honeypot_cache_key(ctx.guild))

        await ctx.send(
            f"Created spam-bait channel {created_channel.mention}. "
            + "Make sure everyone does not *accidentally* chat in it. "
        )

    @honeypot.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def deactivate(self, ctx: commands.Context[Nameless]):
        """Deactivate spam-bait."""
        await ctx.defer()

        assert ctx.guild is not None

        if not nameless_cache.get_key(self._create_honeypot_cache_key(ctx.guild)):
            await ctx.send("You don't have spam-bait activated.")
            return

        async with db.get_session_context() as session, GuildRepository(session) as guild_repo:
            db_guild = await guild_repo.get_or_create(pk_id=ctx.guild.id)

        created_channel = await ctx.guild.fetch_channel(db_guild.HoneypotChannelId)

        nameless_cache.invalidate_key(self._create_honeypot_cache_key(ctx.guild))
        await created_channel.delete()

        await ctx.send(f"Deleted spam-bait channel `#{created_channel.name}`.")


async def setup(bot: Nameless):
    await bot.add_cog(HoneypotCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(HoneypotCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
