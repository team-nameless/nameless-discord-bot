import re
import logging
from typing import AsyncGenerator, Optional, List
from bs4 import BeautifulSoup
import aiohttp

import discord
from discord import app_commands

# from discord.app_commands import Choice
from discord.ext import commands

# from DiscordUtils import Pagination

from nameless import Nameless, shared_vars

# from nameless.customs.DiscordWaiter import DiscordWaiter
# from NamelessConfig import NamelessConfig


__all__ = ["MoimoiCog"]


class Non200Code(Exception):
    pass


class FailInclusionConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.is_confirmed = False

    @discord.ui.button(label="Yep!", style=discord.ButtonStyle.green)  # pyright: ignore
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.is_confirmed = True
        self.stop()

    @discord.ui.button(label="Nope!", style=discord.ButtonStyle.red)  # pyright: ignore
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        return await super().interaction_check(interaction)


class HTMLParser:
    @staticmethod
    async def try_parse(r: str, list_class_element: List[str], tag="div", is_regex: bool = False) -> AsyncGenerator:
        try:
            for class_element in list_class_element:
                soup = BeautifulSoup(r, "html.parser")
                regex = re.compile(class_element)
                yield soup.find_all(tag, {"class": regex}) if is_regex else soup.find_all(tag, {"class": class_element})
        except Exception as e:
            logging.error("%s raise an error: [%s] %s", __name__, e.__class__.__name__, str(e))
            return

    @staticmethod
    async def try_parse_unpack(data: str, attrs: List[str], tag="div", is_regex: bool = False) -> str:
        return "".join([v.text async for v in __class__.try_parse(data, attrs, tag, is_regex)])


class UserContainer(HTMLParser):

    __slots__ = (
        "name",
        "title",
        "rating",
        "avatar_url",
        "big_avatar_url",
        "playcount",
        "dan_rating_img_url",
        "season_rating_url",
        "stars_count",
    )

    def __init__(self, **data):
        self.name = data.get("name", "GUEST")
        self.title = data.get("title", "でびゅー")
        self.rating = data.get("rating", 0)
        self.playcount = data.get("playcount", 0)
        self.dan_rating_img_url = data.get("dan_rating_img_url", "")
        self.season_rating_url = data.get("season_rating_url", "")
        self.stars_count = data.get("stars_count", 0)
        self.user_avatar_url = data.get(
            "avatar_url", "https://maimaidx-eng.com/maimai-mobile/img/Icon/34f0363f4ce86d07.png"
        )
        self.tour_leader_avatar_url = data.get("tour_leader_avatar_url", "")

    @classmethod
    async def parse(cls, data):
        name = await cls.try_parse_unpack(data, ["name_block f_l f_16"])
        title = await cls.try_parse_unpack(data, ["trophy_inner_block f_13"])
        rating = await cls.try_parse_unpack(data, ["rating_block"])
        user_avatar_url = await cls.try_parse_unpack(data, ["w_112 f_l"])
        tour_leader_avatar_url = await cls.try_parse_unpack(data, ["w_120 m_t_10 f_r"])
        dan_rating_img_url = await cls.try_parse_unpack(data, ["h_35 f_l"])
        season_rating_url = await cls.try_parse_unpack(data, ["w_120 m_t_10 f_r"])
        stars_count = await cls.try_parse_unpack(data, ["playlog_chara_star_block f_12"], tag="img")

        # TODO: Install NVIDIA proprietary driver to write this code
        return cls(
            name=name,
            title=title,
            rating=rating,
            user_avatar_url=user_avatar_url,
            tour_leader_avatar_url=tour_leader_avatar_url,
            dan_rating_img_url=dan_rating_img_url,
            season_rating_url=season_rating_url,
            stars_count=stars_count,
        )


class TourmemberContainer(HTMLParser):

    __slots__ = ("level", "stars_count", "image_url")

    def __init__(self, **data) -> None:
        self.level = data.get("level", 0)
        self.stars_count = data.get("stars_count", 0)
        self.image_url = data.get("image_url", "")

    @staticmethod
    async def _internal_parse(data: str, attrs: List[str], tag="div", is_regex: bool = False):
        return [v.text async for v in __class__.try_parse(data, attrs, tag, is_regex)]

    @classmethod
    async def parse(cls, data) -> AsyncGenerator:
        level_ls = await cls._internal_parse(data, ["playlog_chara_lv_block f_13"])
        stars_count_ls = await cls._internal_parse(data, ["playlog_chara_star_block f_12"], tag="img")
        image_url_ls = await cls._internal_parse(data, ["chara_cycle_img"])

        for (level, stars_count, image_url) in zip(level_ls, stars_count_ls, image_url_ls):
            yield cls(level=level, stars_count=stars_count, image_url=image_url)


class TrackContainer(HTMLParser):

    __slots__ = ("title", "difficulty", "cover_url")

    def __init__(self, **data) -> None:
        self.title = data.get("title", "")
        self.difficulty = data.get("difficulty", "")
        self.cover_url = data.get("cover_url", "")

    @staticmethod
    async def parse_diff(diff_url):
        regex = re.compile(r"(?<=diff_)[a-z]+(?=\.png)")
        return next(regex.finditer(diff_url))

    @classmethod
    async def parse(cls, data):
        title = await cls.try_parse_unpack(data, ["basic_block m_5 p_5 p_l_10 f_13 break"])
        difficulty = cls.parse_diff(await cls.try_parse_unpack(data, ["playlog_diff v_b"]))
        cover_url = cls.try_parse_unpack(
            data, [""], tag="img"
        )  # TODO: wait for daily maimai maintained done and i will fix this

        return cls(title=title, difficulty=difficulty, cover_url=cover_url)


class PlaylogContainer(HTMLParser):

    __slots__ = ("track", "rating", "achievement", "tour_member")

    def __init__(self, **data):
        self.track = data.get("track", TrackContainer())
        self.rating = data.get("rating", "")
        self.achievement = data.get("achievement", 0.0)
        self.tour_member = data.get("tour_member", TourmemberContainer())

    @classmethod
    async def parse(cls, data):
        rating = await cls.try_parse_unpack(data, ["rating_block"])
        achievement = await cls.try_parse_unpack(data, ["playlog_achievement_txt t_r", "f_20"])
        track = await TrackContainer.parse(data)
        tour_member = [v async for v in TourmemberContainer.parse(data)]

        return cls(track=track, rating=rating, achievement=achievement, tour_member=tour_member)


class MoimoiCog(commands.Cog):
    MOI_INDEX_URL = "https://maimaidx-eng.com/maimai-mobile"
    MOI_LOGIN_URL = "https://lng-tgk-aime-gw.am-all.net/common_auth/login"
    HEADER = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Nameless",
        "Connection": "keep-alive",
    }

    def __init__(self, bot: Nameless):
        self.__session: aiohttp.ClientSession = None  # pyright: ignore

        self.bot = bot
        self.cookies = None

    @staticmethod
    async def __try_parse(r: str, list_class_element) -> AsyncGenerator:
        try:
            for class_element in list_class_element:
                soup = BeautifulSoup(r, "html.parser")
                yield [*soup.find_all("div", {"class": class_element})][0].text
                # name = [*soup.find_all("div", {"class": re.compile("playlog_*_container")})][0].text
                # return name, rating

        except Exception as e:
            logging.error("%s raise an error: [%s] %s", __name__, e.__class__.__name__, str(e))
            return

    async def __get_cookies(self):
        if self.__session is None:
            self.__session = aiohttp.ClientSession()

        async with self.__session.get(self.MOI_INDEX_URL) as resp:
            self.cookies = resp.cookies

    async def _fetch(self, method, url, *args, **kwargs):
        if self.cookies is None:
            await self.__get_cookies()

        resp = await self.__session.request(method=method, url=url, *args, **kwargs)
        if resp.status == 200:
            return resp

        raise Non200Code(
            f"Oops, trying to do a {method} {resp.url} but return {resp.status} with message: {await resp.text()}"
        )

    async def _login_pass(self, segay_id, password):
        # doan nay nen lay history khong
        body = {
            "retention": 1,
            "sid": segay_id,
            "password": password,
        }

        return await self._fetch("POST", f"{self.MOI_LOGIN_URL}/sid", data=body)

    async def _login_token(self, segay_token):
        cookies = {"_t": segay_token}
        return await self._fetch("POST", f"{self.MOI_LOGIN_URL}/sid", cookies=cookies)

    async def login(self, segay, password=None):
        return await self._login_pass(segay, password) if password else await self._login_token(segay)

    @commands.hybrid_group(fallback="get")
    @app_commands.guilds(*getattr(shared_vars.config_cls, "GUILD_IDs", []))
    async def moimoi(self, ctx: commands.Context, segay_id: str, password: Optional[str]):
        """test moimoi"""
        await ctx.defer()

        r_login = await self.login(segay_id, password)
        await ctx.send(f"```\nDEBUG\nCOOKIES {r_login.cookies}```")
        await r_login.release()

        r_home = await self._fetch(method="GET", url=f"{self.MOI_INDEX_URL}/home")
        data = [value async for value in self.__try_parse(await r_home.text(), ["name_block f_l f_16", "rating_block"])]
        await r_home.release()

        await ctx.send(f"```\nDEBUG\nDATA {data}```")
        await ctx.send(f"Oh hey I found your name is: {data[0]} and rating is {data[1]}")

    @moimoi.command()
    @app_commands.guilds(*getattr(shared_vars.config_cls, "GUILD_IDs", []))
    async def force_logout(self, ctx: commands.Context):
        await self.__session.close()

        self.__session = None  # pyright: ignore
        self.cookies = None


async def setup(bot: Nameless):
    await bot.add_cog(MoimoiCog(bot))
    logging.info("Cog of %s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog("OsuCog")
    logging.warning("Cog of %s removed!", __name__)
