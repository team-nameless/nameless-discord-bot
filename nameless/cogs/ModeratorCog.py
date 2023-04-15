import logging
import typing
from typing import Awaitable, Callable, Type

import discord
from discord import Forbidden, HTTPException, app_commands
from discord.app_commands import Range
from discord.ext import commands

import nameless
from nameless.database.crud import CRUD

__all__ = ["ModeratorCog"]

from nameless.ui_kit import YesNoButtonPrompt


class ModeratorCog(commands.GroupCog):
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
        client = interaction.client
        response = f"Trying to {action} member {member.display_name}#{member.discriminator}. "

        if member.id == interaction.user.id:
            response += "And that is you."
        elif member.id == client.user.id:
            response += "And that is me."
        else:
            try:
                if delete_past_message_days != -1:
                    await action_function(member, reason=reason, delete_message_days=delete_past_message_days)
                else:
                    await action_function(member, reason=reason)
            except Forbidden:
                response += "And I lack the permissions to do it."
            except HTTPException:
                response += "And Discord refused to do it."

        await interaction.followup.send(response)

    @staticmethod
    async def __generic_warn(
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        val: Type,
        zero_fn: Callable[[discord.Interaction, discord.Member, str], Awaitable[None]],
        max_fn: Callable[[discord.Interaction, discord.Member, str], Awaitable[None]],
        diff_fn: Callable[[discord.Interaction, discord.Member, str, int, int], Awaitable[None]],
    ):
        await interaction.response.defer()

        db_user = CRUD.get_or_create_user_record(member)
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        max_warn_count = db_guild.max_warn_count

        if (db_user.warn_count == 0 and val < 0) or (db_user.warn_count == max_warn_count and val > 0):
            await interaction.response.edit_message(content=f"The user already have {db_user.warn_count} warn(s).")
            return

        db_user.warn_count += val
        CRUD.save_changes()

        if db_user.warn_count == 0:
            await zero_fn(interaction, member, reason)
        elif db_user.warn_count == max_warn_count:
            await max_fn(interaction, member, reason)
        else:
            await diff_fn(interaction, member, reason, db_user.warn_count, db_user.warn_count - val)

        await interaction.response.edit_message(
            content=f"{'Removed' if val < 0 else 'Added'} {abs(val)} warning(s) to {member.mention} with reason: {reason}\n"
            f"Now they are having {db_user.warn_count} warning(s)"
        )

    @staticmethod
    async def __generic_mute(
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        mute: bool = True,
    ):
        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        mute_role = interaction.guild.get_role(db_guild.mute_role_id)

        # Pass #1: Mute role retrieval
        if mute_role is None:
            prompt = YesNoButtonPrompt()
            await interaction.followup.send(
                "Mute role not configured. Do you want me to create a temporary role?", view=prompt
            )

            is_timed_out = await prompt.wait()

            if is_timed_out:
                await interaction.response.edit_message(content="Timed out", view=None)
            else:
                perms = discord.Permissions()

                perms.send_messages = False
                perms.send_messages_in_threads = False

                role = await interaction.guild.create_role(
                    name="muted by nameless*", reason="temporary role creation", permissions=perms
                )

                mute_role = role

        # Pass #2: Is native timeout preferred?
        use_native_timeout = db_guild.is_timeout_preferred

        if not use_native_timeout:
            if mute_role is None:
                await interaction.followup.send("No mean of muting the member. Exiting....")
                return

        if db_guild.is_timeout_preferred or mute_role is None:
            is_muted = member.is_timed_out()

            if is_muted:
                if not mute:
                    await member.timeout(None, reason=reason)
                    await interaction.response.edit_message(content="Unmuted")
                else:
                    await interaction.response.edit_message(content="Already muted")
            else:
                if mute:
                    await member.timeout(discord.utils.utcnow().replace(day=7), reason=reason)
                    await interaction.response.edit_message(content="Muted")
                else:
                    await interaction.response.edit_message(content="Already unmuted")

        elif mute_role is not None:
            is_muted = any([role.id == mute_role.id for role in member.roles])
            if is_muted:
                if not mute:
                    await member.remove_roles(mute_role, reason=reason)
                    await interaction.response.edit_message(content="Unmuted")
                else:
                    await interaction.response.edit_message(content="Already muted")
            else:
                if mute:
                    await member.add_roles(mute_role, reason=reason)
                    await interaction.response.edit_message(content="Muted")
                else:
                    await interaction.response.edit_message(content="Already unmuted")

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
        action: typing.Literal["ban", "kick"],
        reason: str,
        delete_past_message_days: Range[int, 0, 7] = 0,
    ):
        """Execute an action to a member"""

        await self.__generic_execute(
            interaction,
            member,
            reason,
            action,
            action_function=interaction.guild.ban,  # pyright: ignore
            delete_past_message_days=delete_past_message_days,
        )

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        action="Action to execute",
        member="Target member",
        reason="Reason for executed warn action",
        count="Warn count, useful for varied warning count per violation",
    )
    async def warn_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        action: typing.Literal["add", "remove"] = "add",
        count: Range[int, 1] = 1,
        reason: str = "Rule violation",
    ):
        """Add warning(s) to a member"""
        await interaction.response.defer()

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
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="Target member",
        reason="Warn removal reason",
        count="Warn count, useful for varied warning count per violation",
    )
    async def warn_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        count: Range[int, 1],
        reason: str = "Good behavior",
    ):
        """Remove warning(s) from a member"""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)

        async def zero_fn(_interaction: discord.Interaction, _member: discord.Member, _reason: str):
            pass

        async def diff_fn(
            _interaction: discord.Interaction, _member: discord.Member, _reason: str, current: int, prev: int
        ):
            if prev == db_guild.max_warn_count:
                await self.__generic_mute(_interaction, _member, _reason, False)

        async def max_fn(_interaction: discord.Interaction, _member: discord.Member, _reason: str):
            pass

        await ModeratorCog.__generic_warn(interaction, member, reason, -count, zero_fn, max_fn, diff_fn)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Mute reason")
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Rule violation",
    ):
        """Mute a member"""
        await self.__generic_mute(interaction, member, reason)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(member="Target member", reason="Unmute reason")
    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Good behavior",
    ):
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

        await interaction.response.edit_message(content=f"Set max warning count to `{count}` warn(s).")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True, manage_guild=True)
    @app_commands.describe(role="New mute role.")
    async def set_mute_role(self, interaction: discord.Interaction, role: discord.Role):
        """Set mute role."""
        await interaction.response.defer()

        db_guild = CRUD.get_or_create_guild_record(interaction.guild)
        db_guild.mute_role_id = role.id

        await interaction.response.edit_message(content=f"Set mute role to `{role.name}` with ID `{role.id}`.")


async def setup(bot: nameless.Nameless):
    await bot.add_cog(ModeratorCog(bot))
    logging.info("%s cog added!", __name__)


async def teardown(bot: nameless.Nameless):
    await bot.remove_cog("ModeratorCog")
    logging.warning("%s cog removed!", __name__)
