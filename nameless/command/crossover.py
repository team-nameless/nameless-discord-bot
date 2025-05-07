import contextlib
import logging

import discord
import discord.ui
from discord.ext import commands
from prisma.models import CrossChatConnection, CrossChatMessage, CrossChatRoom

from nameless import Nameless
from nameless.custom.cache import nameless_cache
from nameless.custom.prisma import NamelessPrisma
from nameless.custom.types import NamelessTextable
from nameless.utils import create_cache_key

__all__ = ["CrossOverCommand"]


class CrossOverCommand(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot: Nameless = bot

    def _create_guild_channel_cache_key(
        self, this_guild: discord.Guild, this_channel: NamelessTextable
    ) -> str:
        """Create (guild,channel) cache key."""
        return create_cache_key("crossover", str(this_guild.id), str(this_channel.id))

    async def _get_subscribed_channels(
        self, this_guild: discord.Guild, this_channel: NamelessTextable
    ) -> list[tuple[CrossChatConnection, NamelessTextable]]:
        """Get list of subscribed guild channels."""
        connections = await CrossChatConnection.prisma().find_many(
            where={"SourceGuildId": this_guild.id, "SourceChannelId": this_channel.id}
        )

        result: list[tuple[CrossChatConnection, NamelessTextable]] = []

        for conn in connections:
            guild = self.bot.get_guild(conn.TargetGuildId)

            if guild is None:
                continue

            channel = guild.get_channel(conn.TargetChannelId)

            if channel is None:
                continue

            if isinstance(channel, NamelessTextable):
                result.append((conn, channel))

        return result

    async def _get_subscribed_messages(
        self,
        this_guild: discord.Guild,
        this_channel: NamelessTextable,
        this_message: discord.Message,
    ) -> list[tuple[CrossChatConnection, discord.Message]]:
        """Get subscribed messages."""
        connections = await CrossChatConnection.prisma().find_many(
            where={
                "SourceGuildId": this_guild.id,
                "SourceChannelId": this_channel.id,
                "Messages": {"some": {"OriginMessageId": this_message.id}},
            },
            include={"Messages": True},
        )

        result: list[tuple[CrossChatConnection, discord.Message]] = []

        for conn in connections:
            guild = self.bot.get_guild(conn.TargetGuildId)

            if guild is None:
                continue

            channel = guild.get_channel(conn.TargetChannelId)

            if channel is None:
                continue

            if not isinstance(channel, NamelessTextable):
                continue

            assert conn.Messages is not None

            the_true_id: int = [
                x.ClonedMessageId
                for x in conn.Messages
                if x.OriginMessageId == this_message.id
            ][0]

            the_true_message = await channel.fetch_message(the_true_id)

            result.append((conn, the_true_message))

        return result

    async def _is_connected_to_each_other(
        self,
        this_guild: discord.Guild,
        this_channel: NamelessTextable,
        that_guild: discord.Guild,
        that_channel: NamelessTextable,
    ) -> bool:
        """
        Return if the 2 rooms are connected.

        A room consisting of (guild, channel) can be used interchangably,
        as long as the "room" is still valid.
        """
        conn1 = await CrossChatConnection.prisma().find_first(
            where={
                "SourceGuildId": this_guild.id,
                "SourceChannelId": this_channel.id,
                "TargetGuildId": that_guild.id,
                "TargetChannelId": that_channel.id,
            }
        )

        conn2 = await CrossChatConnection.prisma().find_first(
            where={
                "SourceGuildId": that_guild.id,
                "SourceChannelId": that_channel.id,
                "TargetGuildId": this_guild.id,
                "TargetChannelId": this_channel.id,
            }
        )

        return conn1 is not None and conn2 is not None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        assert message.guild is not None
        assert message.channel is not None
        assert self.bot.user is not None

        if not isinstance(message.channel, NamelessTextable):
            return

        cache_key = self._create_guild_channel_cache_key(message.guild, message.channel)
        prefix_list: list[str] = self.bot.get_prefix_list()

        # We ignore:
        # - Message from nameless* itself.
        # - Message without a content.
        # - Actual commands.
        # - (Guild, Channel) not in cache.
        if (
            message.author.id == self.bot.user.id
            or len(message.content) == 0
            or any(message.content.startswith(prefix) for prefix in prefix_list)
            or not nameless_cache.get_key(cache_key)
        ):
            return

        for conn, channel in await self._get_subscribed_channels(
            message.guild, message.channel
        ):
            # Fail-safe
            nameless_cache.set_key(cache_key)

            embed = discord.Embed(
                description=message.content, color=discord.Colour.orange()
            )

            avatar_url = message.author.avatar.url if message.author.avatar else ""
            guild_icon = message.guild.icon.url if message.guild.icon else ""

            embed.set_author(
                name=f"@{message.author.global_name} wrote:", icon_url=avatar_url
            )
            embed.set_footer(
                text=f"{message.guild.name} at #{message.channel.name}",
                icon_url=guild_icon,
            )

            sent_message = await channel.send(
                embed=embed,
                stickers=message.stickers,
                files=[await x.to_file() for x in message.attachments],
            )

            await CrossChatMessage.prisma().create(
                data={
                    "Connection": {"connect": {"Id": conn.Id}},
                    "OriginMessageId": message.id,
                    "ClonedMessageId": sent_message.id,
                }
            )

    @commands.Cog.listener()
    async def on_message_edit(self, _: discord.Message, message: discord.Message):
        assert message.guild is not None
        assert message.channel is not None
        assert self.bot.user is not None

        if message.author.id == self.bot.user.id:
            return

        if not isinstance(message.channel, NamelessTextable):
            return

        for _conn, the_message in await self._get_subscribed_messages(
            message.guild, message.channel, message
        ):
            the_embed = the_message.embeds[0]
            the_embed.description = message.content

            await the_message.edit(embed=the_embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        assert message.guild is not None
        assert message.channel is not None
        assert self.bot.user is not None

        if message.author.id == self.bot.user.id:
            return

        if not isinstance(message.channel, NamelessTextable):
            return

        for _conn, the_message in await self._get_subscribed_messages(
            message.guild, message.channel, message
        ):
            with contextlib.suppress(discord.NotFound):
                await the_message.delete()

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        for message in messages:
            await self.on_message_delete(message)

    @commands.hybrid_group(fallback="code")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def crossover(self, ctx: commands.Context[Nameless]):
        """Establish this channel to the public."""
        await ctx.defer()

        assert ctx.guild is not None
        assert ctx.channel is not None

        if not isinstance(ctx.channel, NamelessTextable):
            await ctx.send(
                "You are not inside our accepted channel type (Text/Thread)."
            )
            return

        await NamelessPrisma.get_guild_entry(ctx.guild)

        room_data: CrossChatRoom | None = await CrossChatRoom.prisma().find_first(
            where={"ChannelId": ctx.channel.id, "GuildId": ctx.guild.id},
        )

        if room_data is None:
            room_data = await CrossChatRoom.prisma().create(
                data={"GuildId": ctx.guild.id, "ChannelId": ctx.channel.id}
            )

        await ctx.send(f"Your cross-chat room code is: `{room_data.Id}`")

    @crossover.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def connect(
        self,
        ctx: commands.Context[Nameless],
        room_code: str,
    ):
        """
        Connect to other room.

        Parameters
        ----------
        room_code: str
            Room code to connect to.
        """
        await ctx.defer()

        room_data: CrossChatRoom | None = await CrossChatRoom.prisma().find_first(
            where={"Id": room_code}
        )

        if room_data is None:
            await ctx.send("Room code does not exist!")
            return

        this_guild = ctx.guild
        that_guild = await ctx.bot.fetch_guild(room_data.GuildId)

        assert this_guild is not None
        assert that_guild is not None

        this_channel = ctx.channel
        that_channel = await ctx.bot.fetch_channel(room_data.ChannelId)

        assert this_channel is not None
        assert that_channel is not None

        if not isinstance(this_channel, NamelessTextable):
            await ctx.send(
                "You are not inside our accepted channel type (Text/Thread)."
            )
            return

        assert isinstance(this_channel, NamelessTextable)
        assert isinstance(that_channel, NamelessTextable)

        if await self._is_connected_to_each_other(
            this_guild, this_channel, that_guild, that_channel
        ):
            await ctx.send("Already connected!")
            return

        if room_data.GuildId == this_guild.id and room_data.ChannelId == ctx.channel.id:
            await ctx.send("Don't connect to yourself!")
            return

        await NamelessPrisma.get_guild_entry(this_guild)
        await NamelessPrisma.get_guild_entry(that_guild)

        await CrossChatConnection.prisma().create(
            data={
                "RoomId": room_code,
                "SourceGuildId": this_guild.id,
                "SourceChannelId": this_channel.id,
                "TargetGuildId": that_guild.id,
                "TargetChannelId": that_channel.id,
            }
        )

        await ctx.send("Linking success!")

        await CrossChatConnection.prisma().create(
            data={
                "RoomId": room_code,
                "SourceGuildId": that_guild.id,
                "SourceChannelId": that_channel.id,
                "TargetGuildId": this_guild.id,
                "TargetChannelId": this_channel.id,
            }
        )

        assert isinstance(this_channel.name, str)

        await that_channel.send(
            f"New connection comes from `#{this_channel.name}` at `{this_guild.name}`!"
        )

        this_cache_key = self._create_guild_channel_cache_key(this_guild, this_channel)
        that_cache_key = self._create_guild_channel_cache_key(that_guild, that_channel)

        nameless_cache.set_key(this_cache_key)
        nameless_cache.set_key(that_cache_key)

    @crossover.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def disconnect(
        self,
        ctx: commands.Context[Nameless],
        room_code: str,
    ):
        """
        Disconnect from other room.

        Parameters
        ----------
        room_code: str
            Room code to disconnect from.
        """
        await ctx.defer()

        assert ctx.guild is not None
        assert ctx.channel is not None

        conn_data: (
            CrossChatConnection | None
        ) = await CrossChatConnection.prisma().find_first(
            where={
                "RoomId": room_code,
                "SourceGuildId": ctx.guild.id,
                "SourceChannelId": ctx.channel.id,
            }
        )

        if conn_data is None:
            await ctx.send("Room code does not exist!")
            return

        this_guild = ctx.guild
        that_guild = await ctx.bot.fetch_guild(conn_data.TargetGuildId)

        assert this_guild is not None
        assert that_guild is not None

        this_channel = ctx.channel
        that_channel = await ctx.bot.fetch_channel(conn_data.TargetChannelId)

        assert this_channel is not None
        assert that_channel is not None

        if not isinstance(this_channel, NamelessTextable):
            await ctx.send(
                "You are not inside our accepted channel type (Text/Thread)."
            )
            return

        assert isinstance(this_channel, NamelessTextable)
        assert isinstance(that_channel, NamelessTextable)

        if not await self._is_connected_to_each_other(
            this_guild, this_channel, that_guild, that_channel
        ):
            await ctx.send("You are not connected to this room!")
            return

        await NamelessPrisma.get_guild_entry(this_guild)
        await NamelessPrisma.get_guild_entry(that_guild)

        await CrossChatConnection.prisma().delete_many(
            where={
                "RoomId": room_code,
            }
        )

        await ctx.send("Disconnection success!")

        assert isinstance(this_channel.name, str)

        await that_channel.send(
            f"Disconnected from `#{this_channel.name}` at `{this_guild.name}`!"
        )

        this_cache_key = self._create_guild_channel_cache_key(this_guild, this_channel)
        that_cache_key = self._create_guild_channel_cache_key(that_guild, that_channel)

        nameless_cache.invalidate_key(this_cache_key)
        nameless_cache.invalidate_key(that_cache_key)

    @crossover.command()
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def list(self, ctx: commands.Context[Nameless]):
        """List connected rooms."""
        await ctx.defer()

        assert ctx.guild is not None
        assert ctx.channel is not None

        connections = await CrossChatConnection.prisma().find_many(
            where={"SourceGuildId": ctx.guild.id, "SourceChannelId": ctx.channel.id},
            distinct=["RoomId"],
        )

        rooms: list[str] = []

        for conn in connections:
            that_guild = await ctx.bot.fetch_guild(conn.TargetGuildId)
            that_channel = await that_guild.fetch_channel(conn.TargetChannelId)

            rooms.append(
                f"`{conn.RoomId}` : `#{that_channel.name}` @ `{that_guild.name}`"
            )

        embed = discord.Embed(
            description="All available connections, both in/outbound!",
            color=discord.Colour.orange(),
            title="Connection list",
        )

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else "")
        embed.add_field(name="All connected rooms", value="\n".join(rooms))

        await ctx.send(
            embed=embed,
        )


async def setup(bot: Nameless):
    await bot.add_cog(CrossOverCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(CrossOverCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
