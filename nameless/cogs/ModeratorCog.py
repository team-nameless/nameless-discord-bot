import logging
from typing import Awaitable, Callable, Type

import discord
from discord import Forbidden, HTTPException, app_commands
from discord.ext import commands

import nameless
from nameless.customs.DiscordWaiter import DiscordWaiter
from nameless.database import CRUD
from NamelessConfig import NamelessConfig


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

        msg: discord.Message = await client.wait_for("message", check=DiscordWaiter.message_waiter(ctx), timeout=30)
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
        val: Type,
        zero_fn: Callable[[commands.Context, discord.Member, str], Awaitable[None]],
        max_fn: Callable[[commands.Context, discord.Member, str], Awaitable[None]],
        diff_fn: Callable[[commands.Context, discord.Member, str, int, int], Awaitable[None]],
    ):
        await ctx.defer()

        db_user = CRUD.get_or_create_user_record(member)
        db_guild = CRUD.get_or_create_guild_record(ctx.guild)

        max_warn_count = db_guild.max_warn_count

        if (db_user.warn_count == 0 and val < 0) or (db_user.warn_count == max_warn_count and val > 0):
            await ctx.send(f"The user already have {db_user.warn_count} warn(s).")
            return

        db_user.warn_count += val
        CRUD.save_changes()

        if db_user.warn_count == 0:
            await zero_fn(ctx, member, reason)
        elif db_user.warn_count == max_warn_count:
            await max_fn(ctx, member, reason)
        else:
            await diff_fn(ctx, member, reason, db_user.warn_count, db_user.warn_count - val)

        await ctx.send(
            f"{'Removed' if val < 0 else 'Added'} {abs(val)} warning(s) to {member.mention} with reason: {reason}\n"
            f"Now they are having {db_user.warn_count} warning(s)"
        )

    @staticmethod
    async def __generic_mute(
        ctx: commands.Context,
        member: discord.Member,
        reason: str,
        mute: bool = True,
    ):
        await ctx.defer()

        db_guild = CRUD.get_or_create_guild_record(ctx.guild)
        mute_role = ctx.guild.get_role(db_guild.mute_role_id)

        if db_guild.is_timeout_preferred or mute_role is None:
            is_muted = member.is_timed_out()
            if is_muted:
                if not mute:
                    await member.timeout(None, reason=reason)
                    await ctx.send("Unmuted")
                else:
                    await ctx.send("Already muted")
            else:
                if mute:
                    await member.timeout(discord.utils.utcnow().replace(day=7), reason=reason)
                    await ctx.send("Muted")
                else:
                    await ctx.send("Already unmuted")
        elif mute_role is not None:
            is_muted = any([role.id == mute_role.id for role in member.roles])
            if is_muted:
                if not mute:
                    await member.remove_roles(mute_role, reason=reason)
                    await ctx.send("Unmuted")
                else:
                    await ctx.send("Already muted")
            else:
                if mute:
                    await member.add_roles(mute_role, reason=reason)
                    await ctx.send("Muted")
                else:
                    await ctx.send("Already unmuted")

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.describe(delete_message_days="Past message days to delete", reason="Ban reason")
    async def ban(
        self,
        ctx: commands.Context,
        delete_message_days: int = 0,
        reason: str = "Rule violation",
    ):
        """Ban members, in batch"""
        if not 0 <= delete_message_days <= 7:
            await ctx.send("delete_message_days must be in range of [0,7]")
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
        await self.__generic_ban_kick(ctx, reason, "kick", ctx.guild.kick)  # pyright: ignore

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="Target member",
        reason="Warn addition reason",
        count="Warn count, useful for varied warning count per violation",
    )
    async def warn_add(
        self,
        ctx: commands.Context,
        member: discord.Member,
        count=commands.Range[int, 1],
        reason: str = "Rule violation",
    ):
        """Add warning(s) to a member"""

        async def zero_fn(_ctx: commands.Context, m: discord.Member, r: str):
            pass

        async def diff_fn(_ctx: commands.Context, m: discord.Member, r: str, curr: int, prev: int):
            pass

        async def max_fn(_ctx: commands.Context, m: discord.Member, r: str):
            await self.__generic_mute(_ctx, m, r)

        await ModeratorCog.__generic_warn(ctx, member, reason, count, zero_fn, max_fn, diff_fn)

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="Target member",
        reason="Warn removal reason",
        count="Warn count, useful for varied warning count per violation",
    )
    async def warn_remove(
        self,
        ctx: commands.Context,
        member: discord.Member,
        count=commands.Range[int, 1],
        reason: str = "Good behavior",
    ):
        """Remove warning(s) from a member"""
        db_guild = CRUD.get_or_create_guild_record(ctx.guild)

        async def zero_fn(_ctx: commands.Context, m: discord.Member, r: str):
            pass

        async def diff_fn(_ctx: commands.Context, m: discord.Member, r: str, current: int, prev: int):
            if prev == db_guild.max_warn_count:
                await self.__generic_mute(_ctx, m, r, False)

        async def max_fn(_ctx: commands.Context, m: discord.Member, r: str):
            pass

        await ModeratorCog.__generic_warn(ctx, member, reason, -count.real, zero_fn, max_fn, diff_fn)  # type: ignore

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

    @mod.command()
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
        """Unmute a member"""
        await self.__generic_mute(ctx, member, reason, False)

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(count="Max warn count, useful for varied warning count per violation")
    async def set_max_warn_count(self, ctx: commands.Context, count: commands.Range[int, 1]):
        """Set max warn count for this server"""
        await ctx.defer()
        db_guild = CRUD.get_or_create_guild_record(ctx.guild)
        db_guild.max_warn_count = count

        await ctx.send(f"Set max warning count to {count}")

    @mod.command()
    @commands.guild_only()
    @commands.has_guild_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(role="Role to be used as a mute role")
    async def set_mute_role(self, ctx: commands.Context, role: discord.Role):
        """Set mute role"""
        await ctx.defer()
        db_guild = CRUD.get_or_create_guild_record(ctx.guild)
        db_guild.mute_role_id = role.id

        await ctx.send(f"Set mute role to `{role.name}` with ID `{role.id}`")


async def setup(bot: nameless.Nameless):
    await bot.add_cog(ModeratorCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ModeratorCog")
    logging.warning("Cog of %s removed!", __name__)
