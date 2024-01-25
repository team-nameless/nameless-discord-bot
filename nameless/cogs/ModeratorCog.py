import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Literal

import discord
from discord import HTTPException, app_commands
from discord.app_commands import Range
from discord.ext import commands

import nameless
from nameless.database.crud import CRUD
from nameless.ui_kit import NamelessYNPrompt

__all__ = ["ModeratorCog"]


class ModeratorCog(commands.GroupCog, name="mod"):
    def __init__(self, bot: nameless.Nameless):
        self.bot = bot

    @staticmethod
    async def __generic_execute(
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        action: str,
        *,
        action_function: Callable,
        delete_past_message_days=-1,
    ):
        await interaction.response.defer()

        if member.id in [interaction.user.id, interaction.client.user.id]:
            await interaction.followup.send("You can not do this to yourself, or me.")
            return

        response = f"Trying to {action} member @{member.display_name}. "

        try:
            if delete_past_message_days != -1:
                await action_function(member, reason=reason, delete_message_days=delete_past_message_days)
            else:
                await action_function(member, reason=reason)

            response += "And it was successful."
        except discord.Forbidden:
            response += "And I lack the permissions to do it."
        except HTTPException:
            response += "And Discord refused to do it."

        await interaction.followup.send(response)

    @staticmethod
    async def __generic_warn(
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        val: int,
        zero_fn: Callable[[discord.Interaction, discord.Member, str], Awaitable[None]],
        max_fn: Callable[[discord.Interaction, discord.Member, str], Awaitable[None]],
        diff_fn: Callable[[discord.Interaction, discord.Member, str, int, int], Awaitable[None]],
    ):
        await interaction.response.defer()

        if member.id in [interaction.user.id, interaction.client.user.id]:
            await interaction.followup.send("You can not do this to yourself, or me.")
            return

        db_user = CRUD.get_or_create_user_record(member)
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        max_warn_count = db_guild.max_warn_count

        if (db_user.warn_count == 0 and val < 0) or (db_user.warn_count == max_warn_count and val > 0):
            await interaction.followup.send(content=f"The user already have {db_user.warn_count} warn(s).")
            return

        db_user.warn_count += val

        if db_user.warn_count == 0:
            await zero_fn(interaction, member, reason)
        elif db_user.warn_count == max_warn_count:
            await max_fn(interaction, member, reason)
        else:
            await diff_fn(interaction, member, reason, db_user.warn_count, db_user.warn_count - val)

        await interaction.followup.send(
            content=f"{'Removed' if val < 0 else 'Added'} {abs(val)} warning(s) to {member.mention} "
            f"with reason: {reason}\n"
            f"Now they are having {db_user.warn_count} warning(s)"
        )

    @staticmethod
    async def __generic_mute(interaction: discord.Interaction, member: discord.Member, reason: str, mute: bool = True):
        await interaction.response.defer()

        if member.id in [interaction.user.id, interaction.client.user.id]:
            await interaction.followup.send("You can not do this to yourself, or me.")
            return

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        try:
            mute_role = (
                interaction.guild.get_role(db_guild.mute_role_id)
                or [role for role in interaction.guild.roles if role.name == "muted by nameless*"][0]
            )
        except IndexError:
            mute_role = None

        use_native_timeout = db_guild.is_timeout_preferred

        if not use_native_timeout and not mute_role:
            prompt = NamelessYNPrompt()
            prompt.timeout = 30

            m = await interaction.followup.send(
                "Mute role not configured. Do you want me to create a temporary role?", view=prompt
            )

            is_timed_out = await prompt.wait()

            if is_timed_out:
                await m.edit(content="Timed out", view=None)  # pyright: ignore
                return
            else:
                perms = discord.Permissions.text()

                perms.send_messages = False
                perms.send_messages_in_threads = False
                perms.add_reactions = False

                role = await interaction.guild.create_role(
                    name="muted by nameless*", reason="temporary role creation", permissions=perms
                )

                mute_role = role
                db_guild.mute_role_id = role.id

                await m.edit(content="Creation complete!", view=None)  # pyright: ignore

        if not use_native_timeout and not mute_role:
            await interaction.followup.send("No mean of muting the member. Exiting....")
            return

        if db_guild.is_timeout_preferred or mute_role is None:
            is_muted = member.is_timed_out()

            if is_muted:
                if not mute:
                    await member.timeout(None, reason=reason)
                    await interaction.followup.send(f"Lifting timeout for {member.mention}")
                else:
                    await interaction.followup.send(f"Timeout already applied for {member.mention}")
            else:
                if mute:
                    await member.timeout(db_guild.mute_timeout_interval, reason=reason)
                    await interaction.followup.send(f"Applying timeout for {member.mention}")
                else:
                    await interaction.followup.send(f"Timeout already lifted for {member.mention}")

        elif mute_role is not None:
            is_muted = any([role.id == mute_role.id for role in member.roles])
            if is_muted:
                if not mute:
                    await member.remove_roles(mute_role, reason=reason)
                    await interaction.followup.send(f"Removed mute role for {member.mention}")
                else:
                    await interaction.followup.send(f"Already muted {member.mention} with mute role!")
            else:
                if mute:
                    await member.add_roles(mute_role, reason=reason)
                    await interaction.followup.send(f"Muted {member.mention} with mute role!")
                else:
                    await interaction.followup.send(f"Mute role already removed for {member.mention}")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        member="Member to execute",
        action="Action to execute",
        delete_past_message_days="Past message days to delete (only in 'ban' action)",
        reason="Reason to execute",
    )
    async def execute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        action: Literal["ban", "kick"],
        reason: str = "Bad behavior",
        delete_past_message_days: Range[int, 0, 7] = 0,
    ):
        """Execute an action to a member"""

        await self.__generic_execute(
            interaction,
            member,
            reason,
            action,
            action_function=interaction.guild.ban if action == "ban" else interaction.guild.kick,  # pyright: ignore
            delete_past_message_days=delete_past_message_days,
        )

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="Target member",
        reason="Reason for addition",
        count="Warn count, useful for varied warning count per violation",
    )
    async def warn_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        count: Range[int, 1] = 1,
        reason: str = "Rule violation",
    ):
        """Add warning(s) to a member"""

        async def zero_fn(_interaction: discord.Interaction, _member: discord.Member, _reason: str):
            pass

        async def diff_fn(
            _interaction: discord.Interaction, _member: discord.Member, _reason: str, curr: int, prev: int
        ):
            pass

        async def max_fn(_interaction: discord.Interaction, _member: discord.Member, _reason: str):
            await self.__generic_mute(_interaction, _member, _reason)

        await ModeratorCog.__generic_warn(interaction, member, reason, count, zero_fn, max_fn, diff_fn)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="Target member",
        reason="Reason for removal",
        count="Warn count, useful for varied warning count per violation",
    )
    async def warn_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        count: Range[int, 1] = 1,
        reason: str = "Good behavior",
    ):
        """Remove warning(s) from a member"""

        async def zero_fn(_interaction: discord.Interaction, _member: discord.Member, _reason: str):
            pass

        async def diff_fn(
            _interaction: discord.Interaction, _member: discord.Member, _reason: str, current: int, prev: int
        ):
            db_guild = CRUD.get_or_create_guild_record(interaction.guild)
            if prev == db_guild.max_warn_count:
                await self.__generic_mute(_interaction, _member, _reason, False)

        async def max_fn(_interaction: discord.Interaction, _member: discord.Member, _reason: str):
            pass

        await ModeratorCog.__generic_warn(interaction, member, reason, -count, zero_fn, max_fn, diff_fn)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Mute reason")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Rule violation"):
        """Mute a member"""
        await self.__generic_mute(interaction, member, reason)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Unmute reason")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Good behavior"):
        """Unmute a member"""
        await self.__generic_mute(interaction, member, reason, False)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True, manage_guild=True)
    @app_commands.describe(count="Maximum warn count.")
    async def set_max_warn_count(self, interaction: discord.Interaction, count: Range[int, 1]):
        """Set max warn count."""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.max_warn_count = count

        await interaction.followup.send(content=f"Set max warning count to `{count}` warn(s).")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True, manage_guild=True)
    @app_commands.describe(role="New mute role.")
    async def set_mute_role(self, interaction: discord.Interaction, role: discord.Role):
        """Set mute role."""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.mute_role_id = role.id

        await interaction.followup.send(content=f"Set mute role to `{role.name}` with ID `{role.id}`.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True, manage_guild=True)
    async def clear_mute_role_selection(self, interaction: discord.Interaction):
        """Clear mute role selection."""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.mute_role_id = 0

        await interaction.followup.send(content="Cleared mute role selection.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle_native_timeout(self, interaction: discord.Interaction):
        """Toggle using native 'Timeout' feature instead of using 'Mute role'"""
        await interaction.response.defer()
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.is_timeout_preferred = not db_guild.is_timeout_preferred

        await interaction.followup.send(
            f"Use native `Timeout` feature: {'on' if db_guild.is_timeout_preferred else 'off'}"
        )

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True, manage_guild=True)
    @app_commands.describe(duration="Default mute duration.")
    async def set_mute_timeout_duration(
        self, interaction: discord.Interaction, duration: Literal["60s", "5m", "10m", "1h", "1d", "1w"]
    ):
        """Set default mute duration for timeout."""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        delta: timedelta = timedelta(seconds=60)

        match duration:
            case "5m":
                delta = timedelta(minutes=5)
            case "10m":
                delta = timedelta(minutes=10)
            case "1h":
                delta = timedelta(hours=1)
            case "1d":
                delta = timedelta(days=1)
            case "1w":
                delta = timedelta(weeks=1)

        db_guild.mute_timeout_interval = delta

        await interaction.followup.send(f"Set mute timeout duration to {delta}")


async def setup(bot: nameless.Nameless):
    await bot.add_cog(ModeratorCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ModeratorCog")
    logging.warning("%s cog removed!", __name__)
