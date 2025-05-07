import contextlib
import logging

import discord
import discord.ui
from discord.ext import commands
from prisma.models import Guild

from nameless import Nameless
from nameless.custom.cache import nameless_cache
from nameless.custom.prisma import NamelessPrisma
from nameless.utils import create_cache_key

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

        db_guild = await Guild.prisma().find_unique_or_raise(
            where={"Id": message.guild.id}
        )

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

        await NamelessPrisma.get_guild_entry(ctx.guild)

        if nameless_cache.get_key(self._create_honeypot_cache_key(ctx.guild)):
            await ctx.send("You already activated the honeypot.")
            return

        created_channel = await ctx.guild.create_text_channel(
            "spam-goes-here", reason="Spam-bait activation."
        )

        await created_channel.send("# DO NOT TEXT IN HERE, YOU WILL BE BANNED.")

        await Guild.prisma().update_many(
            data={"HoneypotChannelId": created_channel.id}, where={"Id": ctx.guild.id}
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

        await NamelessPrisma.get_guild_entry(ctx.guild)
        db_guild = await Guild.prisma().find_unique_or_raise(where={"Id": ctx.guild.id})

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
