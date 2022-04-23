import nextcord
from nextcord import SlashOption, Forbidden, HTTPException
from nextcord.ext import commands, application_checks

from config import Config
from customs import Utility
from globals import crud_database
from database.models import DbUser

MUTE_ROLE_NAME = "you-are-muted"


class ModeratorCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot) -> None:
        self.bot = bot

    @nextcord.slash_command(
        description="Moderation commands", guild_ids=Config.GUILD_IDs
    )
    async def mod(self, _: nextcord.Interaction):
        pass

    @staticmethod
    async def __generic_ban_kick(
        interaction: nextcord.Interaction, reason: str, action: str, caller, d=-1
    ):
        client: nextcord.Client = interaction.client

        await interaction.response.defer()
        await interaction.edit_original_message(
            content=f"Mention members you want to {action} with reason {reason}"
        )
        msg: nextcord.Message = await client.wait_for(
            "message", check=Utility.message_waiter(interaction), timeout=30
        )
        mentioned_members = msg.mentions
        responses = []

        for member in mentioned_members:
            response = f"Trying to {action} member {member.display_name}#{member.discriminator}. "

            if member.id == interaction.user.id:
                response += "And that is you."
            elif member.id == client.user.id:
                response += "And that is me."
            else:
                try:
                    if d != -1:
                        await caller(member, reason=reason, delete_message_days=d)
                    else:
                        await caller(member, reason=reason)
                except Forbidden:
                    response += "And I lack the permissions to do it."
                except HTTPException:
                    response += "And Discord refused to do it."

            responses.append(response)

        await interaction.followup.send(content="\n".join(responses))

    @staticmethod
    async def __generic_warn(
        interaction: nextcord.Interaction,
        member: nextcord.Member,
        reason: str,
        val: int,
        zero_fn,
        three_fn,
        diff_fn,
    ):
        await interaction.response.defer()

        u, _ = crud_database.get_or_create_user_record(member)

        if (u.warn_count == 0 and val < 0) or (u.warn_count == 3 and val > 0):
            await interaction.edit_original_message(
                content=f"The user already have {u.warn_count} warn(s)."
            )
            return

        u.warn_count = DbUser.warn_count + val
        crud_database.save_changes()

        if u.warn_count == 0:
            await zero_fn(interaction, member, reason)
        elif u.warn_count == 3:
            await three_fn(interaction, member, reason)
        else:
            await diff_fn(interaction, member, reason, u.warn_count, u.warn_count - val)

        # await member.send()
        await interaction.edit_original_message(
            content=f"{'Removed' if val < 0 else 'Added'} {abs(val)} warn to {member.mention} with reason: {reason}\n"
            f"Now they have {u.warn_count} warn(s)"
        )

    @staticmethod
    async def __generic_mute(
        interaction: nextcord.Interaction,
        member: nextcord.Member,
        reason: str,
        mute: bool = 1,
    ):
        await interaction.response.defer()
        mute_role, is_new = await Utility.get_or_create_role(
            interaction, MUTE_ROLE_NAME, "Mute role creation"
        )

        if is_new:
            for channel in interaction.guild.channels:
                await channel.set_permissions(
                    mute_role,
                    send_messages=False,
                    send_messages_in_threads=False,
                    reason="Mute role channel override",
                )

        is_muted = mute_role in member.roles
        if is_muted:
            if not mute:
                await member.remove_roles(mute_role, reason=reason)
                await interaction.edit_original_message(content="Unmuted")
            else:
                await interaction.edit_original_message(content="Already muted")
        else:
            if mute:
                await member.add_roles(mute_role, reason=reason)
                await interaction.edit_original_message(content="Muted")
            else:
                await interaction.edit_original_message(content="Already unmuted")

    @mod.subcommand(description="Ban members, in batch")
    @application_checks.bot_has_guild_permissions(ban_members=True)
    @application_checks.has_guild_permissions(ban_members=True)
    async def ban(
        self,
        interaction: nextcord.Interaction,
        delete_message_days: int = SlashOption(
            description="Past message days to delete", default=0
        ),
        reason: str = SlashOption(description="Ban reason", default="Rule violation"),
    ):
        if not 0 <= delete_message_days <= 7:
            await interaction.send(
                content="delete_message_days must satisfy 0 <= delete_message_days <= 7"
            )
        else:
            await self.__generic_ban_kick(
                interaction, reason, "ban", interaction.guild.ban, delete_message_days
            )

    @mod.subcommand(description="Kick members, in batch")
    @application_checks.bot_has_guild_permissions(kick_members=True)
    @application_checks.has_guild_permissions(kick_members=True)
    async def kick(
        self,
        interaction: nextcord.Interaction,
        reason: str = SlashOption(description="Kick reason", default="Rule violation"),
    ):
        await self.__generic_ban_kick(
            interaction, reason, "kick", interaction.guild.kick
        )

    @mod.subcommand(description="Add a warning to a member")
    @application_checks.has_guild_permissions(moderate_members=True)
    async def warn_add(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = SlashOption(description="Target member"),
        reason: str = SlashOption(
            description="Reason to add", default="Rule violation"
        ),
    ):
        async def zero_fn(i: nextcord.Interaction, m: nextcord.Member, r: str):
            pass

        async def diff_fn(
            i: nextcord.Interaction, m: nextcord.Member, r: str, current: int, prev: int
        ):
            pass

        async def three_fn(i: nextcord.Interaction, m: nextcord.Member, r: str):
            role, no = await Utility.get_or_create_role(
                interaction=i, name=MUTE_ROLE_NAME, reason="Mute role creation"
            )

            if no:
                for channel in i.guild.channels:
                    await channel.set_permissions(
                        role,
                        send_messages=False,
                        send_messages_in_threads=False,
                        reason="Mute role channel override",
                    )

            if not any(grole.name == MUTE_ROLE_NAME for grole in m.roles):
                await m.add_roles(role, reason=r)

        await ModeratorCog.__generic_warn(
            interaction, member, reason, 1, zero_fn, three_fn, diff_fn
        )

    @mod.subcommand(description="Remove a warning from a member")
    @application_checks.has_guild_permissions(moderate_members=True)
    async def warn_remove(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = SlashOption(description="Target member"),
        reason: str = SlashOption(
            description="Reason to remove", default="Good behavior"
        ),
    ):
        async def zero_fn(i: nextcord.Interaction, m: nextcord.Member, r: str):
            pass

        async def diff_fn(
            i: nextcord.Interaction, m: nextcord.Member, r: str, current: int, prev: int
        ):
            if prev == 3:
                role, _ = await Utility.get_or_create_role(
                    interaction=i, name=MUTE_ROLE_NAME, reason="Mute role creation"
                )
                if any(grole.name == MUTE_ROLE_NAME for grole in m.roles):
                    await m.remove_roles(role, reason=r)

        async def three_fn(i: nextcord.Interaction, m: nextcord.Member, r: str):
            pass

        await ModeratorCog.__generic_warn(
            interaction, member, reason, -1, zero_fn, three_fn, diff_fn
        )

    @mod.subcommand(description="Mute a member")
    @application_checks.has_guild_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = SlashOption(description="Target member"),
        reason: str = SlashOption(
            description="Reason to mute", default="Rule violation"
        ),
    ):
        await self.__generic_mute(interaction, member, reason)

    @mod.subcommand(description="Unmute a member")
    @application_checks.has_guild_permissions(moderate_members=True)
    async def unmute(
        self,
        interaction: nextcord.Interaction,
        member: nextcord.Member = SlashOption(description="Target member"),
        reason: str = SlashOption(
            description="Reason to unmute", default="Good behavior"
        ),
    ):
        await self.__generic_mute(interaction, member, reason, False)
