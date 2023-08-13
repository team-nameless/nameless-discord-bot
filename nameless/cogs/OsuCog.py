import datetime
import logging
from typing import Dict, List, Optional

import discord
from discord import Color, app_commands
from discord.app_commands import Choice, Range
from discord.ext import commands
from ossapi import GameMode, Ossapi, Score, ScoreType, User, UserLookupKey
from reactionmenu import ViewButton, ViewMenu

from nameless import Nameless
from nameless.database import CRUD
from nameless.ui_kit import YesNoButtonPrompt
from NamelessConfig import NamelessConfig


__all__ = ["OsuCog"]

osu_modes = ["osu", "taiko", "fruits", "mania"]
request_types = ["profile", "first_place_scores", "recent_scores", "best_scores"]


def convert_to_game_mode(mode: str) -> GameMode:
    """Get game mode matching with the provided string.

    Args:
        mode (str): Game mode in osu_mode. Look above this `def` code.

    Returns:
        GameMode: GameMode for ossapi
    """
    m: Dict[str, GameMode] = {
        "osu": GameMode.OSU,
        "taiko": GameMode.TAIKO,
        "fruits": GameMode.CATCH,
        "mania": GameMode.MANIA,
    }

    return m[mode.lower()]


class OsuCog(commands.GroupCog, name="osu"):
    def __init__(self, bot: Nameless):
        self.bot = bot
        self.api = Ossapi(
            NamelessConfig.OSU.CLIENT_ID,
            NamelessConfig.OSU.CLIENT_SECRET,
        )

    @app_commands.command()
    @app_commands.describe(member="The member to view, or you by default.")
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member]):
        """View someone's osu! *linked* profile"""
        await interaction.response.defer()
        db_user = CRUD.get_or_create_user_record(member if member else interaction.user)

        if not db_user.osu_username:
            if member is None:
                await interaction.followup.send(
                    "You did not linked with me. "
                    "There is `osu update` command and I would be happy if you linked your "
                    "profile details to me <3. Do not worry, I will not ask for password."
                )
            else:
                await interaction.followup.send(
                    "This user did not linked with me. "
                    "Can you please tell them to do so? It would be very kind of you :3"
                )
            return

        embed = (
            discord.Embed(
                description="Your linked osu! profile details with me",
                timestamp=datetime.datetime.now(),
                colour=Color.brand_red(),
            )
            .add_field(name="Username", value=db_user.osu_username, inline=True)
            .add_field(name="Mode", value=db_user.osu_mode, inline=True)
        )
        await interaction.followup.send(embeds=[embed])

    @app_commands.command()
    @app_commands.describe(username="Your new osu! username", mode="Your new osu! mode")
    @app_commands.choices(mode=[Choice(name=k, value=k) for k in osu_modes])
    async def update(self, interaction: discord.Interaction, username: str, mode: str = "osu"):
        """Update your linked profile with me"""
        await interaction.response.defer()
        db_user = CRUD.get_or_create_user_record(interaction.user)
        db_user.osu_username, db_user.osu_mode = username, mode.title()
        CRUD.save_changes()
        await interaction.followup.send("Successfully updated your profile details with me! Yay!")

    @app_commands.command()
    @app_commands.describe(member="Target member", username="Their osu! username", mode="Their osu! mode")
    @app_commands.choices(mode=[Choice(name=k, value=k) for k in osu_modes])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def force_update(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        username: str,
        mode: str = "osu",
    ):
        """Force database to update a member's auto search. For guild managers."""
        await interaction.response.defer()
        db_user = CRUD.get_or_create_user_record(member)
        db_user.osu_username, db_user.osu_mode = username, mode.title()

        CRUD.save_changes()

        await interaction.followup.send(
            f"Successfully updated the profile details of " f"**{member.display_name}#{member.discriminator}**!"
        )

    async def __generic_check(
        self,
        interaction: discord.Interaction,
        request: str,
        username: str,
        mode: str,
        include_fails: bool,
        count: int,
        is_from_context: bool = False,
    ):
        m: discord.WebhookMessage = await interaction.followup.send("Processing....")  # pyright: ignore

        the_mode = None if mode == "default" else convert_to_game_mode(mode)

        osu_user: User = self.api.user(username, mode=the_mode, key=UserLookupKey.USERNAME)

        user_stats = osu_user.statistics

        if not user_stats:
            await m.edit(content=f"I can not retrieve the statistics of **{username}** in `{the_mode}`!")
            return

        if request == "profile":
            eb = (
                discord.Embed(
                    color=Color.brand_red(),
                    timestamp=datetime.datetime.now(),
                    description=f"This user is now {'online' if osu_user.is_online else 'offline/invisible'}",
                )
                .set_author(
                    name=f"Profile of {osu_user.username} in {osu_user.playmode if mode == 'default' else mode}"
                    f" ( {'🖤' if not osu_user.is_supporter else '❤️'} )",
                    url=f"https://osu.ppy.sh/users/{osu_user.id}",
                    icon_url=f"https://flagcdn.com/h20/{osu_user.country_code.lower()}.jpg",
                )
                .set_thumbnail(url=osu_user.avatar_url)
                .set_footer(text=f"Requested by {interaction.user}")
                .add_field(
                    name="Account creation time",
                    value=f"<t:{int(osu_user.join_date.timestamp())}:F>",
                )
                .add_field(
                    name="Level",
                    value=f"{user_stats.level.current} ({user_stats.level.progress}%)",
                    inline=False,
                )
                .add_field(name="Accuracy", value=f"{user_stats.hit_accuracy}%")
                .add_field(name="PP", value=user_stats.pp)
                .add_field(name="Max combo", value=user_stats.maximum_combo)
                .add_field(
                    name="Play count",
                    value=f"{user_stats.play_count} plays over {user_stats.play_time} minutes",
                )
                .add_field(
                    name="Leaderboard ranking",
                    value=f"#{user_stats.global_rank} - #{user_stats.country_rank} {osu_user.country_code}",
                )
                .add_field(
                    name="Score ranking",
                    value=f"{user_stats.grade_counts.ssh}/"
                    f"{user_stats.grade_counts.ss}/"
                    f"{user_stats.grade_counts.sh}/"
                    f"{user_stats.grade_counts.s}/"
                    f"{user_stats.grade_counts.a}",
                )
            )

            if osu_user.previous_usernames:
                eb.insert_field_at(
                    index=0,
                    name="Formerly known as",
                    value=", ".join(osu_user.previous_usernames),
                )

            await m.edit(content="", embeds=[eb])
        else:
            request_type: ScoreType = ScoreType.BEST

            if request == "first_place_scores":
                request_type = ScoreType.FIRSTS
            elif request == "recent_scores":
                request_type = ScoreType.RECENT

            # fail inclusion prompt
            if not is_from_context and request == "recent_scores":
                fail_prompt = YesNoButtonPrompt()
                fail_prompt.timeout = 30
                m = await m.edit(content="Do you want to include fail scores?", view=fail_prompt)

                if await fail_prompt.wait():
                    await m.edit(content="Timed out", view=None)
                    return

                fail_prompt.stop()
                include_fails = fail_prompt.is_confirmed

            scores: List[Score] = self.api.user_scores(
                osu_user.id, request_type, include_fails=include_fails, mode=the_mode, limit=count
            )

            if len(scores) == 0:
                await m.edit(content="No suitable scores found", view=None)
                return

            embeds = []

            for idx, score in enumerate(scores):
                beatmap_set = score.beatmapset
                beatmap = score.beatmap
                sender = score.user()
                score_stats = score.statistics

                embed = (
                    discord.Embed(
                        description=f"Score position #{idx + 1}",
                        color=Color.brand_red(),
                        timestamp=datetime.datetime.now(),
                    )
                    .set_author(
                        name=f"{beatmap_set.artist} - {beatmap_set.title} [{beatmap.version if beatmap else '???'}] "
                        if beatmap_set
                        else "No map found online!" f"+{score.mods.long_name().replace(' ', '')}",
                        url=beatmap.url if beatmap else "",
                        icon_url=sender.avatar_url,
                    )
                    .set_thumbnail(url=beatmap_set.covers.cover_2x if beatmap_set and beatmap_set.covers else "")
                    .add_field(
                        name="Score",
                        value=f"{sender.country_code} #{score.rank_country} - GLB #{score.rank_global}",
                        inline=False,
                    )
                    .add_field(name="Ranking", value=score.rank.name)
                    .add_field(name="Accuracy", value=f"{round(score.accuracy * 100, 2)}%")
                    .add_field(
                        name="Max combo",
                        value=f"{score.max_combo}x/{beatmap.max_combo if beatmap and beatmap.max_combo else '???'}x",
                    )
                    .add_field(
                        name="Hit count",
                        value=f"{score_stats.count_300}/"
                        f"{score_stats.count_100}/"
                        f"{score_stats.count_50}/"
                        f"{score_stats.count_miss}",
                    )
                    .add_field(
                        name="PP",
                        value=f"{score.pp} * {round(score.weight.percentage, 3)}% = {round(score.weight.pp, 3)}"
                        if score.weight is not None
                        else "0",
                    )
                    .add_field(
                        name="Submission time",
                        value=f"<t:{int(score.created_at.timestamp())}:R>",
                    )
                )

                embeds.append(embed)

            if len(embeds) != 1:
                view_menu = ViewMenu(interaction, menu_type=ViewMenu.TypeEmbed)
                view_menu.add_pages(embeds)

                view_menu.add_button(ViewButton.back())
                view_menu.add_button(ViewButton.end_session())
                view_menu.add_button(ViewButton.next())

                await view_menu.start()
            else:
                await m.edit(embed=embeds[0], view=None)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(
        member="Target member, you by default.",
        request_type="Request type",
        game_mode="osu! game mode",
        include_fail="Whether to include fail records (only in 'recent_scores')",
        count="Records count (when you request for scores)",
    )
    @app_commands.choices(
        game_mode=[Choice(name=k, value=k) for k in [*osu_modes, "default"]],
        request_type=[Choice(name=k, value=k) for k in request_types],
    )
    async def details(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member],
        request_type: str = "profile",
        game_mode: str = "default",
        include_fail: bool = True,
        count: Range[int, 1] = 1,
    ):
        """View osu! specific detail(s) of a member."""
        await interaction.response.defer()

        db_user = CRUD.get_or_create_user_record(member if member else interaction.user)

        if not db_user.osu_username:
            if member is None:
                await interaction.followup.send(
                    "You did not linked with me. "
                    "There is `osu update` command and I would be happy if you linked your "
                    "profile details to me <3. Do not worry, I will not ask for password."
                )
            else:
                await interaction.followup.send(
                    "This user did not linked with me. "
                    "Can you please tell them to do so? It would be very kind of you :3"
                )

            return

        await self.__generic_check(
            interaction,
            request_type,
            db_user.osu_username,
            db_user.osu_mode if game_mode == "default" else game_mode,
            include_fail,
            count,
        )

    @app_commands.command()
    @commands.guild_only()
    @app_commands.describe(
        username="osu! username",
        request_type="Request type",
        game_mode="osu! game mode",
        include_fail="Whether to include fail records (defaults to True, only in 'recent_scores')",
        count="Records count (only in records queries)",
    )
    @app_commands.choices(
        game_mode=[Choice(name=k, value=k) for k in [*osu_modes, "default"]],
        request_type=[Choice(name=k, value=k) for k in request_types],
    )
    async def details_custom(
        self,
        interaction: discord.Interaction,
        username: str,
        request_type: str = "profile",
        game_mode: str = "default",
        include_fail: bool = True,
        count: Range[int, 1] = 1,
    ):
        """View osu! specific detail(s) of a custom osu! profile"""
        await interaction.response.defer()
        await self.__generic_check(interaction, request_type, username, game_mode, include_fail, count)


async def setup(bot: Nameless):
    if NamelessConfig.OSU.CLIENT_ID and NamelessConfig.OSU.CLIENT_SECRET:
        await bot.add_cog(OsuCog(bot))
        logging.info("%s cog added!", __name__)
    else:
        raise commands.ExtensionFailed(__name__, ValueError("osu! configuration values are not properly provided!"))


async def teardown(bot: Nameless):
    await bot.remove_cog("OsuCog")
    logging.warning("%s cog removed!", __name__)
