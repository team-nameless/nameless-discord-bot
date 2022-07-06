import logging
from typing import Awaitable, Callable

import discord
from discord import Forbidden, HTTPException, app_commands
from discord.ext import commands

import nameless
from NamelessConfig import NamelessConfig
from nameless.customs.DiscordWaiter import DiscordWaiter
from nameless.shared_vars import crud_database

__all__ = ["ModeratorCog"]


class ModeratorCog(commands.Cog):
    def __init__(self, bot: nameless.Nameless) -> None:
        self.bot = bot

    @commands.hybrid_group(fallback="do-not-use")
    @app_commands.guilds(*getattr(NamelessConfig, "GUILD_IDs", []))
    @commands.guild_only()
    async def mod(self, ctx: commands.Context):
        """Nothing here!"""
        await ctx.send("You found the matrix!")

    @staticmethod
    async def __generic_ban_kick(
        ctx: commands.Context,
        reason: str,
        action: str,
        caller: Callable,
        d=-1,
    ):
        client = ctx.bot

        await ctx.send(f"Mention members you want to {action} with reason {reason}")

        msg: discord.Message = await client.wait_for(
            "message", check=DiscordWaiter.message_waiter(ctx), timeout=30
        )
        mentioned_members = msg.mentions
        responses = []

        for member in mentioned_members:
            response = f"Trying to {action} member {member.display_name}#{member.discriminator}. "

            if member.id == ctx.author.id:
                response += "And that is you."
            elif member.id == client.user.id:
                response += "And that is me."
            else:
                try:
                    # ignore kwargs typings
                    if d != -1:
                        await caller(member, reason=reason, delete_message_days=d)
                    else:
                        await caller(member, reason=reason)
                except Forbidden:
                    response += "And I lack the permissions to do it."
                except HTTPException:
                    response += "And Discord refused to do it."

            responses.append(response)

        await ctx.send("\n".join(responses))

    @staticmethod
    async def __generic_warn(
        ctx: commands.Context,
        member: discord.Member,
        reason: str,
        val: int,
        zero_fn: Callable[[commands.Context, discord.Member, str], Awaitable[None]],
        three_fn: Callable[[commands.Context, discord.Member, str], Awaitable[None]],
        diff_fn: Callable[
            [commands.Context, discord.Member, str, int, int], Awaitable[None]
        ],
    ):
        await ctx.defer()

        u, _ = crud_database.get_or_create_user_record(member)

        if (u.warn_count == 0 and val < 0) or (u.warn_count == 3 and val > 0):
            await ctx.send(f"The user already have {u.warn_count} warn(s).")
            return

        u.warn_count += val
        crud_database.save_changes()

        if u.warn_count == 0:
            await zero_fn(ctx, member, reason)
        elif u.warn_count == 3:
            await three_fn(ctx, member, reason)
        else:
            await diff_fn(ctx, member, reason, u.warn_count, u.warn_count - val)

        # await member.send()
        await ctx.send(
            f"{'Removed' if val < 0 else 'Added'} {abs(val)} warn to {member.mention}"
            "with reason: {reason}\n"
            f"Now they have {u.warn_count} warn(s)"
        )

    @staticmethod
    async def __generic_mute(
        ctx: commands.Context,
        member: discord.Member,
        reason: str,
        mute: bool = True,
    ):
        await ctx.defer()

        is_muted = member.is_timed_out()
        if is_muted:
            if not mute:
                await member.timeout(None, reason=reason)
                await ctx.send("Unmuted")
            else:
                await ctx.send("Already muted")
        else:
            if mute:
                await member.timeout(
                    discord.utils.utcnow().replace(day=7), reason=reason
                )
                await ctx.send("Muted")
            else:
                await ctx.send("Already unmuted")

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        delete_message_days="Past message days to delete", reason="Ban reason"
    )
    async def ban(
        self,
        ctx: commands.Context,
        delete_message_days: int = 0,
        reason: str = "Rule violation",
    ):
        """Ban members, in batch"""
        if not 0 <= delete_message_days <= 7:
            await ctx.send(
                "delete_message_days must satisfy 0 <= delete_message_days <= 7"
            )
        else:
            await self.__generic_ban_kick(
                ctx,
                reason,
                "ban",
                ctx.guild.ban,  # pyright: ignore
                delete_message_days,
            )

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(kick_members=True)
    @commands.bot_has_guild_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    @app_commands.describe(reason="Kick reason")
    async def kick(
        self,
        ctx: commands.Context,
        reason: str = "Rule violation",
    ):
        """Kick members, in batch"""
        await self.__generic_ban_kick(
            ctx, reason, "kick", ctx.guild.kick  # pyright: ignore
        )

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Warn addition reason")
    async def warn_add(
        self,
        ctx: commands.Context,
        member: discord.Member,
        reason: str = "Rule violation",
    ):
        """Add a warning to a member"""

        async def zero_fn(_ctx: commands.Context, m: discord.Member, r: str):
            pass

        async def diff_fn(
            _ctx: commands.Context, m: discord.Member, r: str, curr: int, prev: int
        ):
            pass

        async def three_fn(_ctx: commands.Context, m: discord.Member, r: str):
            await m.timeout(discord.utils.utcnow().replace(day=7), reason=r)

        await ModeratorCog.__generic_warn(
            ctx, member, reason, 1, zero_fn, three_fn, diff_fn
        )

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Warn removal reason")
    async def warn_remove(
        self,
        ctx: commands.Context,
        member: discord.Member,
        reason: str = "Good behavior",
    ):
        """Remove a warning from a member"""

        async def zero_fn(_ctx: commands.Context, m: discord.Member, r: str):
            pass

        async def diff_fn(
            _ctx: commands.Context, m: discord.Member, r: str, current: int, prev: int
        ):
            if prev == 3:
                await m.timeout(None, reason=r)

        async def three_fn(_ctx: commands.Context, m: discord.Member, r: str):
            pass

        await ModeratorCog.__generic_warn(
            ctx, member, reason, -1, zero_fn, three_fn, diff_fn
        )

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Mute reason")
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        reason: str = "Rule violation",
    ):
        """Mute a member"""
        await self.__generic_mute(ctx, member, reason)

    @mod.command(description="Unmute a member")
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Unmute reason")
    async def unmute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        reason: str = "Good behavior",
    ):
        await self.__generic_mute(ctx, member, reason, False)


async def setup(bot: nameless.Nameless):
    await bot.add_cog(ModeratorCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ModeratorCog")
    logging.warning("Cog of %s removed!", __name__)
