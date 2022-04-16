import nextcord
from nextcord.ext import commands, menus
from nextcord_paginator import Paginator

from config import Config


class MyEmbedFieldPageSource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entries):
        embed = nextcord.Embed(title="Entries", description="\n".join(entries))
        embed.set_footer(text=f'Page {menu.current_page + 1}/{self.get_max_pages()}')
        return embed


class ExperimentSlashCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @nextcord.slash_command(description="Experimental commands", guild_ids=Config.GUILD_IDs)
    async def labs(self, _: nextcord.Interaction):
        pass

    @labs.subcommand(description="Pagination test #1")
    async def page_test1(self, interaction: nextcord.Interaction):
        await interaction.response.defer()
        fields = [
            ("Black", "#000000"),
            ("Blue", "#0000FF"),
            ("Brown", "#A52A2A"),
            ("Green", "#00FF00"),
            ("Grey", "#808080"),
            ("Orange", "#FFA500"),
            ("Pink", "#FFC0CB"),
            ("Purple", "#800080"),
            ("Red", "#FF0000"),
            ("White", "#FFFFFF"),
            ("Yellow", "#FFFF00"),
        ]
        pages = menus.ButtonMenuPages(
            source=MyEmbedFieldPageSource([f'Description for entry #{num}' for num in range(1, 51)]),
            clear_buttons_after=True,
        )
        await pages.start(interaction=interaction)

    @labs.subcommand(description="Pagination test #2")
    async def page_test2(self, interaction: nextcord.Interaction):
        await interaction.response.defer()
        e1 = nextcord.Embed(title='Test 1', description='Test 1', color=nextcord.Color.blue())
        e2 = nextcord.Embed(title='Test 2', description='Test 2', color=nextcord.Color.green())
        e3 = nextcord.Embed(title='Test 3', description='Test 3', color=nextcord.Color.blurple())

        emb = [e1, e2, e3]
        msg = await interaction.send(content="Never gonna give you up")

        pages = Paginator(msg, emb, interaction.user, interaction.client, timeout=15, footerpage=False,
                          footerdatetime=False,
                          footerboticon=False)
        await pages.start()
        # await pages.start(interaction=interaction)
