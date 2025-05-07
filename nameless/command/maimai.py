import logging

import discord
import discord.ui
from discord.ext import commands
from prisma.models import User

from nameless import Nameless
from nameless.custom.cache import nameless_cache
from nameless.custom.maimai.maimai import MaimaiClient
from nameless.custom.maimai.models import MaimaiUser
from nameless.custom.prisma import NamelessPrisma
from nameless.utils import create_cache_key

__all__ = ["MaimaiCommand"]


class MaimaiCommand(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot: Nameless = bot
        self.moimoi_api: MaimaiClient = MaimaiClient()

    def _create_maimai_cache_key(self, user: discord.User | discord.Member) -> str:
        return create_cache_key("maimai", str(user.id))

    @commands.hybrid_group(fallback="profile")
    async def maimai(self, ctx: commands.Context[Nameless]):
        """View your linked maimai profile."""
        await ctx.defer()

        cache_key = self._create_maimai_cache_key(ctx.author)

        if not nameless_cache.get_key(cache_key):
            await ctx.send("You have not linked with me, *yet*.")
            return

        db_user = await NamelessPrisma.get_user_entry(ctx.author)

        moi_user: MaimaiUser = self.moimoi_api.find_by_friend_code(
            db_user.MaimaiFriendCode
        )

        embed = (
            discord.Embed(
                color=discord.Color.teal(),
                title="maimai profile",
                description="Yes, simple, I know.",
            )
            .set_thumbnail(url=moi_user.avatar_img)
            .add_field(name="IGN", value=moi_user.name)
            .add_field(name="Rating", value=moi_user.rating)
            .set_footer(text=f"Friend code: {moi_user.friend_code}")
        )

        await ctx.send(embed=embed)

    @maimai.command()
    async def link(self, ctx: commands.Context[Nameless], friend_code: int):
        """View your linked maimai profile."""
        await ctx.defer()

        try:
            self.moimoi_api.find_by_friend_code(friend_code)
            await NamelessPrisma.get_user_entry(ctx.author)

            await User.prisma().update_many(
                where={"Id": ctx.author.id}, data={"MaimaiFriendCode": friend_code}
            )

            await ctx.send("Linkage complete!")

            nameless_cache.set_key(self._create_maimai_cache_key(ctx.author))
        except Exception:
            await ctx.send("Invalid friend code, or I have been hitting with 429s.")
            return


async def setup(bot: Nameless):
    await bot.add_cog(MaimaiCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(MaimaiCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
