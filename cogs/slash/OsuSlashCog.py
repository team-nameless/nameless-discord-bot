import datetime
from typing import Optional, List

from nextcord_paginator import Paginator
from ossapi import *
import nextcord
from nextcord import Color, SlashOption
from nextcord.ext import commands

from config import Config
import globals
from customs import Utility
from database.postgres.models import DbUser

osu_modes = {
    "osu": "Osu",
    "taiko": "Taiko",
    "fruits": "Fruits",
    "mania": "Mania"
}


def convert_to_game_mode(mode: str) -> GameMode:
    """Get gamemode matching with the provided string.

    Args:
        mode (str): Game mode in osu_mode. Look above this `def` code.

    Returns:
        GameMode: GameMode for ossapi
    """
    match mode.lower():
        case "osu":
            return GameMode.STD
        case "taiko":
            return GameMode.TAIKO
        case "fruits":
            return GameMode.CTB
        case "mania":
            return GameMode.MANIA


class FailInclusionConfirmationView(nextcord.ui.View):
    def __init__(self):
        super().__init__()
        self.is_confirmed = False

    @nextcord.ui.button(label='Yep!', style=nextcord.ButtonStyle.green)
    async def confirm(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        self.is_confirmed = True
        self.stop()

    @nextcord.ui.button(label='Cancel', style=nextcord.ButtonStyle.grey)
    async def cancel(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        self.stop()


class OsuSlashCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.api = OssapiV2(Config.OSU["client_id"], Config.OSU["client_secret"])

    @nextcord.slash_command(description="osu! commands", guild_ids=Config.GUILD_IDs)
    async def osu(self, _: nextcord.Interaction):
        pass

    @osu.subcommand(description="View your linked auto search data")
    async def me(self, interaction: nextcord.Interaction):
        await interaction.response.defer()
        dbu: DbUser = globals.postgres_database.get_user_record(interaction.user)
        embed = nextcord.Embed(description="Your linked osu! auto search with me",
                               timestamp=datetime.datetime.now(),
                               colour=Color.brand_red()) \
            .set_image(url=interaction.user.display_avatar.url) \
            .add_field(name="Username", value=dbu.osu_username, inline=True) \
            .add_field(name="Mode", value=dbu.osu_mode, inline=True)
        await interaction.edit_original_message(embeds=[embed])

    @osu.subcommand(description="Update your linked auto search data")
    async def update(self, interaction: nextcord.Interaction,
                     username: str = SlashOption(description="Your osu! username"),
                     mode: str = SlashOption(description="Your osu! mode",
                                             choices=osu_modes, default="osu")):
        await interaction.response.defer()
        dbu, _ = globals.postgres_database.get_or_create_user_record(interaction.user)
        dbu.osu_username, dbu.osu_mode = username, mode
        globals.postgres_database.save_changes()
        await interaction.edit_original_message(content="Updated")

    @osu.subcommand(description="Force update a member's linked auto search data")
    async def force_update(self, interaction: nextcord.Interaction,
                           member: nextcord.Member = SlashOption(description="Target member"),
                           username: str = SlashOption(description="osu! username"),
                           mode: str = SlashOption(description="osu! mode",
                                                   choices=osu_modes, default="osu")):
        await interaction.response.defer()
        dbu, _ = globals.postgres_database.get_or_create_user_record(member)
        dbu.osu_username, dbu.osu_mode = username, mode
        globals.postgres_database.save_changes()
        await interaction.edit_original_message(content="Updated")

    async def __generic_check(self, interaction: nextcord.Interaction, request: str, username: str, mode: str,
                              is_from_context: bool = False):
        await interaction.edit_original_message(content="Processing")

        osu_user: Optional[User]
        the_mode = None

        if mode != "default":
            the_mode = convert_to_game_mode(mode)

        osu_user: User = self.api.user(username, the_mode, key=UserLookupKey.USERNAME)
        user_stats = osu_user.statistics

        if request == "profile":
            eb = nextcord.Embed(
                color=Color.brand_red(),
                timestamp=datetime.datetime.now(),
                description=f"This user is now {'online' if osu_user.is_online else 'offline/invisible'}"
            ) \
                .set_author(name=f"Profile of {osu_user.username} in {osu_user.playmode if mode == 'default' else mode}"
                                 f" ( {'🖤' if not osu_user.is_supporter else '❤️'} )",
                            url=f"https://osu.ppy.sh/users/{osu_user.id}",
                            icon_url=f"https://flagcdn.com/h20/{osu_user.country_code.lower()}.jpg") \
                .set_thumbnail(url=osu_user.avatar_url) \
                .set_footer(text=f"Requested by {interaction.user.display_name}#{interaction.user.discriminator}") \
                .add_field(name="Formerly known as", value=", ".join(osu_user.previous_usernames)) \
                .add_field(name="Join date", value=osu_user.join_date) \
                .add_field(name="Level", value=f"{user_stats.level.current} ({user_stats.level.progress}%)",
                           inline=False) \
                .add_field(name="Accuracy", value=f"{user_stats.hit_accuracy}%") \
                .add_field(name="PP", value=user_stats.pp) \
                .add_field(name="Max combo", value=user_stats.maximum_combo) \
                .add_field(name="Play count",
                           value=f"{user_stats.play_count} plays over {user_stats.play_time} minutes") \
                .add_field(name="Leaderboard ranking",
                           value=f"#{user_stats.global_rank} - #{user_stats.country_rank} {osu_user.country_code}") \
                .add_field(name="Score ranking", value=f"{user_stats.grade_counts.ssh}/"
                                                       f"{user_stats.grade_counts.ss}/"
                                                       f"{user_stats.grade_counts.sh}/"
                                                       f"{user_stats.grade_counts.s}/"
                                                       f"{user_stats.grade_counts.a}")

            await interaction.edit_original_message(content="", embed=eb)
        else:
            request_type: ScoreType = ScoreType.BEST

            if request == "bests":
                request_type = ScoreType.BEST
            elif request == "firsts":
                request_type = ScoreType.FIRSTS
            elif request == "recents":
                request_type = ScoreType.RECENT

            limit: int
            prompt: str
            include_fails: bool
            msg: nextcord.Message

            # limit count
            if not is_from_context:
                try:
                    await interaction.send(content="How many records do you want to get?")
                    msg = await self.bot.wait_for("message",
                                                  check=Utility.message_waiter(interaction),
                                                  timeout=30)
                    prompt = msg.content
                    await msg.delete(delay=1.0)
                except TimeoutError:
                    await interaction.edit_original_message(content="Timed out")
                    return
            else:
                prompt = "1"

            try:
                limit = int(prompt)
            except ValueError:
                await interaction.followup.send(content="Invalid number provided. Please correct then run again.")
                return

            # fail inclusion prompt
            if not is_from_context and request == "recents":
                view = FailInclusionConfirmationView()
                await interaction.followup.send(content="Do you want to include fail scores?", view=view)
                await view.wait()

                if not view.is_confirmed:
                    await interaction.followup.send(content="Timed out")
                    return
                else:
                    include_fails = view.is_confirmed
            else:
                include_fails = True

            scores: List[Score] = self.api.user_scores(osu_user.id, request_type, include_fails, the_mode, limit)

            if len(scores) == 0:
                await interaction.followup.send(content="No suitable scores found")
                return

            embeds = []

            for idx, score in enumerate(scores):
                beatmap_set = score.beatmapset
                beatmap = score.beatmap
                sender = score.user()
                score_stats = score.statistics

                embed = nextcord.Embed(
                    description=f"Score position #{idx + 1}",
                    color=Color.brand_red(),
                    timestamp=datetime.datetime.now()
                ) \
                    .set_author(name=f"{beatmap_set.artist} - {beatmap_set.title} [{beatmap.version}] "
                                     f"+{score.mods.long_name().replace(' ', '')}",
                                url=beatmap.url,
                                icon_url=sender.avatar_url) \
                    .set_thumbnail(url=beatmap_set.covers.cover_2x) \
                    .add_field(name="Score",
                               value=f"{sender.country_code} #{score.rank_country} - GLB #{score.rank_global}",
                               inline=False) \
                    .add_field(name="Ranking", value=score.rank.name) \
                    .add_field(name="Accuracy", value=score.accuracy) \
                    .add_field(name="Max combo", value=f"{score.max_combo}x/{beatmap.max_combo}") \
                    .add_field(name="Hit count", value=f"{score_stats.count_300}/"
                                                       f"{score_stats.count_100}/"
                                                       f"{score_stats.count_50}/"
                                                       f"{score_stats.count_miss}") \
                    .add_field(name="PP", value=f"{score.pp} * {score.weight.percentage}% = {score.weight.pp}"
                               if score.weight is not None else "0") \
                    .add_field(name="Submission time", value=score.created_at)

                embeds.append(embed)

            if not is_from_context or len(embeds) != 1:
                msg = await interaction.followup.send(embed=embeds[0])
                pages = Paginator(msg, embeds, interaction.user, interaction.client, timeout=60, footerpage=False,
                                  footerdatetime=False,
                                  footerboticon=False)
                await pages.start()
            else:
                await interaction.followup.send(embed=embeds[0])

    @osu.subcommand(description="Check osu! profile of a member")
    async def check_member(self, interaction: nextcord.Interaction,
                           member: nextcord.Member = SlashOption(description="Target member"),
                           request: str = SlashOption(description="Request data",
                                                      choices={
                                                          "profile": "profile",
                                                          "firsts": "firsts",
                                                          "recents": "recents",
                                                          "bests": "bests"
                                                      },
                                                      default="profile"),
                           mode: str = SlashOption(description="Request mode",
                                                   choices={
                                                       **osu_modes,
                                                       "default": "default"
                                                   },
                                                   default="default")):
        await interaction.response.defer()
        dbu, _ = globals.postgres_database.get_or_create_user_record(member)

        if dbu.osu_username == "":
            await interaction.edit_original_message(content="This user did not linked to me")
            return

        await self.__generic_check(interaction, request, dbu.osu_username,
                                   dbu.osu_mode if mode == "default" else mode)

    @osu.subcommand(description="Check osu! profile of a custom osu profile")
    async def check_custom(self, interaction: nextcord.Interaction,
                           username: str = SlashOption(description="osu! username"),
                           request: str = SlashOption(description="Request data",
                                                      choices={
                                                          "profile": "profile",
                                                          "firsts": "firsts",
                                                          "recents": "recents",
                                                          "bests": "bests"
                                                      },
                                                      default="profile"),
                           mode: str = SlashOption(description="Request mode",
                                                   choices={
                                                       **osu_modes,
                                                       "default": "default"
                                                   },
                                                   default="default")):
        await interaction.response.defer()
        await self.__generic_check(interaction, request, username, mode)

    @nextcord.user_command(name="osu! - View profile", guild_ids=Config.GUILD_IDs)
    async def user_context_menu_view_profile(self, interaction: nextcord.Interaction,
                                             member: nextcord.Member):
        await interaction.response.defer()
        dbu, _ = globals.postgres_database.get_or_create_user_record(member)

        if dbu.osu_username == "":
            await interaction.edit_original_message(content="This user did not linked to me")
            return

        await self.__generic_check(interaction, "profile", dbu.osu_username, "default", True)

    @nextcord.user_command(name="osu! - View latest score", guild_ids=Config.GUILD_IDs)
    async def user_context_menu_view_latest_score(self, interaction: nextcord.Interaction,
                                                  member: nextcord.Member):
        await interaction.response.defer()
        dbu, _ = globals.postgres_database.get_or_create_user_record(member)

        if dbu.osu_username == "":
            await interaction.edit_original_message(content="This user did not linked to me")
            return

        await self.__generic_check(interaction, "recents", dbu.osu_username, "default", True)

    @nextcord.user_command(name="osu! - View best score", guild_ids=Config.GUILD_IDs)
    async def user_context_menu_view_best_score(self, interaction: nextcord.Interaction,
                                                member: nextcord.Member):
        await interaction.response.defer()
        dbu, _ = globals.postgres_database.get_or_create_user_record(member)

        if dbu.osu_username == "":
            await interaction.edit_original_message(content="This user did not linked to me")
            return

        await self.__generic_check(interaction, "bests", dbu.osu_username, "default", True)
