import datetime
from typing import Optional, List

import discord
from DiscordUtils import Pagination
from discord import Color, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from ossapi import *

import globals
from config import Config
from customs import Utility

osu_modes = {"osu": "Osu", "taiko": "Taiko", "fruits": "Fruits", "mania": "Mania"}
request_types = {
    "profile": "profile",
    "firsts": "firsts",
    "recents": "recents",
    "bests": "bests",
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


class FailInclusionConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.is_confirmed = False

    @discord.ui.button(label="Yep!", style=discord.ButtonStyle.green)
    async def confirm(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.is_confirmed = True
        self.stop()

    @discord.ui.button(label="Nope!", style=discord.ButtonStyle.red)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.stop()


class OsuCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.api = OssapiV2(Config.OSU["client_id"], Config.OSU["client_secret"])

        # Workaround for logging dupe
        self.api.log.propagate = False
        self.api.log.parent.propagate = False
        self.api.log.handlers[:] = [globals.handler]
        self.api.log.parent.handlers[:] = [globals.handler]

    @commands.hybrid_group(fallback="me")
    @app_commands.guilds(*Config.GUILD_IDs)
    async def osu(self, ctx: commands.Context):
        """View your osu! *linked* profile"""
        await ctx.defer()
        dbu, _ = globals.crud_database.get_or_create_user_record(ctx.author)
        embed = (
            discord.Embed(
                description="Your linked osu! auto search with me",
                timestamp=datetime.datetime.now(),
                colour=Color.brand_red(),
            )
            .set_image(url=ctx.author.display_avatar.url)
            .add_field(name="Username", value=dbu.osu_username, inline=True)
            .add_field(name="Mode", value=dbu.osu_mode, inline=True)
        )
        await ctx.send(embeds=[embed])

    @osu.command()
    @app_commands.describe(username="Your osu! username", mode="Your osu! mode")
    @app_commands.choices(mode=[Choice(name=k, value=v) for k, v in osu_modes.items()])
    async def update(self, ctx: commands.Context, username: str, mode: str = "Osu"):
        """Update your auto search"""
        await ctx.defer()
        dbu, _ = globals.crud_database.get_or_create_user_record(ctx.author)
        dbu.osu_username, dbu.osu_mode = username, mode
        globals.crud_database.save_changes(user_record=dbu)
        await ctx.send("Updated")

    @osu.command()
    @app_commands.describe(
        member="Target member", username="osu! username", mode="osu! mode"
    )
    @app_commands.choices(mode=[Choice(name=k, value=v) for k, v in osu_modes.items()])
    async def force_update(
        self,
        ctx: commands.Context,
        member: discord.Member,
        username: str,
        mode: str = "Osu",
    ):
        """Force database to update a member's auto search"""
        await ctx.defer()
        dbu, _ = globals.crud_database.get_or_create_user_record(member)
        dbu.osu_username, dbu.osu_mode = username, mode
        globals.crud_database.save_changes(user_record=dbu)
        await ctx.send("Updated")

    async def __generic_check(
        self,
        ctx: commands.Context,
        request: str,
        username: str,
        mode: str,
        is_from_context: bool = False,
    ):
        m = await ctx.send("Processing")

        osu_user: Optional[User]
        the_mode = None if mode == "default" else convert_to_game_mode(mode)

        osu_user: User = self.api.user(username, the_mode, key=UserLookupKey.USERNAME)
        user_stats = osu_user.statistics

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
                .set_footer(
                    text=f"Requested by {ctx.author.display_name}#{ctx.author.discriminator}"
                )
                .add_field(name="Join date", value=osu_user.join_date)
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

            await m.edit(embeds=[eb])
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
            msg: discord.Message

            # limit count
            if not is_from_context:
                pr = await m.edit(content="How many records do you want to get?")

                try:
                    msg: discord.Message = await self.bot.wait_for(
                        "message", check=Utility.message_waiter(ctx), timeout=30
                    )
                    prompt = msg.content
                    await msg.delete(delay=1.0)
                except TimeoutError:
                    await pr.edit(content="Timed out")
                    return
            else:
                prompt = "1"

            try:
                limit = int(prompt)
            except ValueError:
                await ctx.send(
                    "Invalid number provided. Please correct then run again."
                )
                return

            # fail inclusion prompt
            if not is_from_context and request == "recents":
                view = FailInclusionConfirmationView()
                fail_pr = await ctx.send(
                    "Do you want to include fail scores?", view=view
                )
                await view.wait()

                if not view.is_confirmed:
                    await fail_pr.edit(content="Timed out", view=None)
                    return
                else:
                    include_fails = view.is_confirmed
            else:
                include_fails = True

            scores: List[Score] = self.api.user_scores(
                osu_user.id, request_type, include_fails, the_mode, limit
            )

            if len(scores) == 0:
                await ctx.send("No suitable scores found")
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
                        name=f"{beatmap_set.artist} - {beatmap_set.title} [{beatmap.version}] "
                        f"+{score.mods.long_name().replace(' ', '')}",
                        url=beatmap.url,
                        icon_url=sender.avatar_url,
                    )
                    .set_thumbnail(url=beatmap_set.covers.cover_2x)
                    .add_field(
                        name="Score",
                        value=f"{sender.country_code} #{score.rank_country} - GLB #{score.rank_global}",
                        inline=False,
                    )
                    .add_field(name="Ranking", value=score.rank.name)
                    .add_field(
                        name="Accuracy", value=f"{round(score.accuracy * 100, 2)}%"
                    )
                    .add_field(
                        name="Max combo",
                        value=f"{score.max_combo}x/{beatmap.max_combo}",
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
                    .add_field(name="Submission time", value=score.created_at)
                )

                embeds.append(embed)

            if not is_from_context or len(embeds) != 1:
                paginator = Pagination.AutoEmbedPaginator(ctx)
                await paginator.run(embeds)
            else:
                # Since we are in context menu command
                # Or either the embed list is so small
                await ctx.send(embed=embeds[0])

    @osu.command()
    @app_commands.describe(
        member="Target member", request="Request type", mode="osu! mode"
    )
    @app_commands.choices(
        mode=[
            Choice(name=k, value=v)
            for k, v in {**osu_modes, "default": "default"}.items()
        ],
        request=[Choice(name=k, value=v) for k, v in request_types.items()],
    )
    async def check_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        request: str = "profile",
        mode: str = "default",
    ):
        """Check osu! profile of a member"""
        await ctx.defer()
        dbu, _ = globals.crud_database.get_or_create_user_record(member)

        if dbu.osu_username == "":
            await ctx.send(content="This user did not linked to me")
            return

        await self.__generic_check(
            ctx,
            request,
            dbu.osu_username,
            dbu.osu_mode if mode == "default" else mode,
        )

    @osu.command()
    @app_commands.describe(
        username="osu! username", request="Request type", mode="osu! mode"
    )
    @app_commands.choices(
        mode=[
            Choice(name=k, value=v)
            for k, v in {**osu_modes, "default": "default"}.items()
        ],
        request=[Choice(name=k, value=v) for k, v in request_types.items()],
    )
    async def check_custom(
        self,
        ctx: commands.Context,
        username: str,
        request: str = "profile",
        mode: str = "defaiult",
    ):
        """Check a custom osu! profile"""
        await ctx.defer()
        await self.__generic_check(ctx, request, username, mode)
