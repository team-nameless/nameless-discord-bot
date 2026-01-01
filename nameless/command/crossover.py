from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from nameless.config import nameless_config
from nameless.custom.cache import nameless_cache
from nameless.custom.types import NamelessTextable
from nameless.db import db
from nameless.db.models import CrossChatConnection, CrossChatMessage, CrossChatRoom
from nameless.db.repositories import (
    CrossChatConnectionRepository,
    CrossChatMessageRepository,
    CrossChatRoomRepository,
    GuildRepository,
)
from nameless.utils import create_cache_key

if TYPE_CHECKING:
    from nameless import Nameless


__all__ = ["CrossOverCommand"]


class CrossOverCommand(commands.Cog):
    def __init__(self, bot: Nameless):
        self.bot: Nameless = bot

    def _create_guild_channel_cache_key(self, this_guild: discord.Guild, this_channel: NamelessTextable) -> str:
        """Create (guild,channel) cache key."""
        return create_cache_key("crossover", str(this_guild.id), str(this_channel.id))

    async def _get_subscribed_channels(
        self, this_guild: discord.Guild, this_channel: NamelessTextable
    ) -> list[tuple[CrossChatConnection, NamelessTextable]]:
        """Get list of subscribed guild channels."""
        async with db.get_session_context() as session:
            conn_repo = CrossChatConnectionRepository(session)
            connections = await conn_repo.get_by_source(this_guild.id, this_channel.id)

        result_list: list[tuple[CrossChatConnection, NamelessTextable]] = []

        for conn in connections:
            guild = self.bot.get_guild(conn.TargetGuildId)

            if guild is None:
                continue

            channel = guild.get_channel(conn.TargetChannelId)

            if channel is None:
                continue

            if isinstance(channel, NamelessTextable):
                result_list.append((conn, channel))

        return result_list

    async def _get_subscribed_messages(
        self,
        this_guild: discord.Guild,
        this_channel: NamelessTextable,
        this_message: discord.Message,
    ) -> list[tuple[CrossChatConnection, discord.Message]]:
        """Get subscribed messages."""
        async with db.get_session_context() as session:
            conn_repo = CrossChatConnectionRepository(session)
            connections = await conn_repo.get_by_source(this_guild.id, this_channel.id)

            msg_repo = CrossChatMessageRepository(session)
            connection_messages: dict[str, list[CrossChatMessage]] = {}
            for conn in connections:
                messages = await msg_repo.get_by_connection(conn.UUID)

                filtered_messages = [msg for msg in messages if msg.OriginMessageId == this_message.id]
                connection_messages[conn.UUID] = filtered_messages

        result_list: list[tuple[CrossChatConnection, discord.Message]] = []

        for conn in connections:
            guild = self.bot.get_guild(conn.TargetGuildId)

            if guild is None:
                continue

            channel = guild.get_channel(conn.TargetChannelId)

            if channel is None:
                continue

            if not isinstance(channel, NamelessTextable):
                continue

            messages = connection_messages.get(conn.UUID, [])
            if not messages:
                continue

            the_true_id: int = messages[0].ClonedMessageId
            the_true_message = await channel.fetch_message(the_true_id)

            result_list.append((conn, the_true_message))

        return result_list

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
        async with db.get_session_context() as session:
            conn_repo = CrossChatConnectionRepository(session)
            conn1 = await conn_repo.get_by_source_and_target(
                this_guild.id, this_channel.id, that_guild.id, that_channel.id
            )
            conn2 = await conn_repo.get_by_source_and_target(
                that_guild.id, that_channel.id, this_guild.id, this_channel.id
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
        prefix_list: set[str] = nameless_config.command.prefixes

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

        for conn, channel in await self._get_subscribed_channels(message.guild, message.channel):
            # Fail-safe
            nameless_cache.set_key(cache_key)

            embed = discord.Embed(description=message.content, color=discord.Colour.orange())

            avatar_url = message.author.avatar.url if message.author.avatar else ""
            guild_icon = message.guild.icon.url if message.guild.icon else ""

            embed.set_author(name=f"@{message.author.global_name} wrote:", icon_url=avatar_url)
            embed.set_footer(
                text=f"{message.guild.name} at #{message.channel.name}",
                icon_url=guild_icon,
            )

            sent_message = await channel.send(
                embed=embed,
                stickers=message.stickers,
                files=[await x.to_file() for x in message.attachments],
            )

            async with db.get_session_context() as session:
                msg_repo = CrossChatMessageRepository(session)
                chat_message = CrossChatMessage(
                    ConnectionId=conn.UUID,
                    OriginMessageId=message.id,
                    ClonedMessageId=sent_message.id,
                )
                await msg_repo.create(chat_message)

    @commands.Cog.listener()
    async def on_message_edit(self, _: discord.Message, message: discord.Message):
        assert message.guild is not None
        assert message.channel is not None
        assert self.bot.user is not None

        if message.author.id == self.bot.user.id:
            return

        if not isinstance(message.channel, NamelessTextable):
            return

        for _conn, the_message in await self._get_subscribed_messages(message.guild, message.channel, message):
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

        for _conn, the_message in await self._get_subscribed_messages(message.guild, message.channel, message):
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
            await ctx.send("You are not inside our accepted channel type (Text/Thread).")
            return

        async with db.get_session_context() as session:
            guild_repo = GuildRepository(session)
            await guild_repo.get_or_create(ctx.guild.id)

            room_repo = CrossChatRoomRepository(session)
            room_data = await room_repo.get_by_channel(ctx.guild.id, ctx.channel.id)

            if room_data is None:
                room_data = CrossChatRoom(GuildId=ctx.guild.id, ChannelId=ctx.channel.id)
                await room_repo.create(room_data)

        await ctx.send(f"Your cross-chat room code is: `{room_data.UUID}`")

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

        async with db.get_session_context() as session:
            room_repo = CrossChatRoomRepository(session)
            room_data = await room_repo.get_by_uuid(room_code)

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
            await ctx.send("You are not inside our accepted channel type (Text/Thread).")
            return

        assert isinstance(this_channel, NamelessTextable)
        assert isinstance(that_channel, NamelessTextable)

        if await self._is_connected_to_each_other(this_guild, this_channel, that_guild, that_channel):
            await ctx.send("Already connected!")
            return

        if room_data.GuildId == this_guild.id and room_data.ChannelId == ctx.channel.id:
            await ctx.send("Don't connect to yourself!")
            return

        async with db.get_session_context() as session:
            guild_repo = GuildRepository(session)
            await guild_repo.get_or_create(this_guild.id)
            await guild_repo.get_or_create(that_guild.id)

            conn_repo = CrossChatConnectionRepository(session)
            conn1 = CrossChatConnection(
                RoomId=room_code,
                SourceGuildId=this_guild.id,
                SourceChannelId=this_channel.id,
                TargetGuildId=that_guild.id,
                TargetChannelId=that_channel.id,
            )
            await conn_repo.create(conn1)

        await ctx.send("Linking success!")

        async with db.get_session_context() as session:
            conn_repo = CrossChatConnectionRepository(session)
            conn2 = CrossChatConnection(
                RoomId=room_code,
                SourceGuildId=that_guild.id,
                SourceChannelId=that_channel.id,
                TargetGuildId=this_guild.id,
                TargetChannelId=this_channel.id,
            )
            await conn_repo.create(conn2)

        assert isinstance(this_channel.name, str)

        await that_channel.send(f"New connection comes from `#{this_channel.name}` at `{this_guild.name}`!")

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

        async with db.get_session_context() as session:
            conn_repo = CrossChatConnectionRepository(session)
            conn_data = await conn_repo.get_by_room_and_source(room_code, ctx.guild.id, ctx.channel.id)

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
            await ctx.send("You are not inside our accepted channel type (Text/Thread).")
            return

        assert isinstance(this_channel, NamelessTextable)
        assert isinstance(that_channel, NamelessTextable)

        if not await self._is_connected_to_each_other(this_guild, this_channel, that_guild, that_channel):
            await ctx.send("You are not connected to this room!")
            return

        async with db.get_session_context() as session:
            guild_repo = GuildRepository(session)
            await guild_repo.get_or_create(this_guild.id)
            await guild_repo.get_or_create(that_guild.id)

            # Delete all connections with this room code
            conn_repo = CrossChatConnectionRepository(session)
            await conn_repo.delete_by_room(room_code)

        await ctx.send("Disconnection success!")

        assert isinstance(this_channel.name, str)

        await that_channel.send(f"Disconnected from `#{this_channel.name}` at `{this_guild.name}`!")

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

        async with db.get_session_context() as session:
            conn_repo = CrossChatConnectionRepository(session)
            connections = await conn_repo.get_by_source(ctx.guild.id, ctx.channel.id)

            seen_rooms: set[str] = set()
            unique_connections: list[CrossChatConnection] = []
            for conn in connections:
                if conn.RoomId not in seen_rooms:
                    seen_rooms.add(conn.RoomId)
                    unique_connections.append(conn)

        rooms: list[str] = []

        for conn in unique_connections:
            that_guild = await ctx.bot.fetch_guild(conn.TargetGuildId)
            that_channel = await that_guild.fetch_channel(conn.TargetChannelId)

            rooms.append(f"`{conn.RoomId}` : `#{that_channel.name}` @ `{that_guild.name}`")

        embed = discord.Embed(
            description="All available connections, both in/outbound!",
            color=discord.Colour.orange(),
            title="Connection list",
        )

        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else "")
        embed.add_field(name="All connected rooms", value="\n".join(rooms) if rooms else "No connections")

        await ctx.send(
            embed=embed,
        )


async def setup(bot: Nameless):
    await bot.add_cog(CrossOverCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(CrossOverCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
