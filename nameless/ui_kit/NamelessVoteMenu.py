import math

import discord
import wavelink

__all__ = ["NamelessVoteMenu"]


class NamelessVoteMenuView(discord.ui.View):
    __slots__ = ("user", "value")

    def __init__(self):
        super().__init__(timeout=15)
        self.user = None
        self.value = None

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.user = interaction.user.mention

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey, emoji="❌")
    async def disapprove(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.user = interaction.user.mention

        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        return True


class NamelessVoteMenu:
    __slots__ = (
        "action",
        "content",
        "interaction",
        "max_vote_user",
        "total_vote",
        "approve_member",
        "disapprove_member",
    )

    def __init__(
        self,
        interaction: discord.Interaction,
        wavelink_player: wavelink.Player,
        action: str,
        content: str,
    ):
        self.action = action
        self.content = f"{content[:50]}..."
        self.interaction = interaction
        self.max_vote_user = math.ceil(len(wavelink_player.channel.members) / 2)
        self.total_vote = 1

        self.approve_member: list[str] = [interaction.user.mention]
        self.disapprove_member: list[str] = []

    async def start(self) -> bool:
        if self.max_vote_user <= 1:
            return True

        await self.interaction.response.edit_message(embed=self.__eb())

        while len(self.disapprove_member) < self.max_vote_user and len(self.approve_member) < self.max_vote_user:
            menu = NamelessVoteMenuView()
            await self.interaction.response.edit_message(embed=self.__eb(), view=menu)
            await menu.wait()

            if menu.user in self.approve_member or menu.user in self.disapprove_member:
                continue

            self.total_vote += 1

            if menu.value:
                self.approve_member.append(menu.user)  # pyright: ignore
            else:
                self.disapprove_member.append(menu.user)  # pyright: ignore

        pred = len(self.disapprove_member) < len(self.approve_member)
        if pred:
            await self.interaction.response.edit_message(
                content=f"{self.action.title()} {self.content}!", embed=None, view=None
            )
        else:
            await self.interaction.response.edit_message(
                content=f"Not enough votes to {self.action}!", embed=None, view=None
            )

        return pred

    def __eb(self):
        return (
            discord.Embed(
                title=f"Vote {self.action} {self.content}",
                description=f"Total vote: {self.total_vote}/{self.max_vote_user}",
            )
            .add_field(name="Approve", value="\n".join(self.approve_member), inline=True)
            .add_field(
                name="Disapprove",
                value="\n".join(self.disapprove_member) if self.disapprove_member else "None",
                inline=True,
            )
            .set_footer(text=f"Requested by {self.interaction.user.name}#{self.interaction.user.discriminator}")
        )
