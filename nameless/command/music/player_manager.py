from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, cast, overload

import discord
from discord.ext import commands

from .exceptions import ConnectionFailedError, NotInVoiceError
from .player import CustomPlayer

if TYPE_CHECKING:
    from nameless.nameless import Nameless


class PlayerManager:
    if TYPE_CHECKING:
        bot: Nameless

    def __init__(self, bot: Nameless):
        self.bot = bot

    async def validate_voice_permissions(
        self,
        ctx: commands.Context[Nameless],
        *,
        bypass_checks: bool = False,
    ) -> None:
        if not isinstance(ctx.author, discord.Member):
            raise commands.CommandError("This command can only be used in a server!")

        if bypass_checks:
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise NotInVoiceError()

    @overload
    async def get_player(
        self,
        ctx: commands.Context[Nameless],
        *,
        connect_if_needed: bool = False,
        raise_on_unconnected: Literal[True],
    ) -> CustomPlayer: ...

    @overload
    async def get_player(
        self,
        ctx: commands.Context[Nameless],
        *,
        connect_if_needed: Literal[True],
        raise_on_unconnected: Literal[True],
    ) -> CustomPlayer: ...

    @overload
    async def get_player(
        self,
        ctx: commands.Context[Nameless],
        *,
        connect_if_needed: Literal[True],
        raise_on_unconnected: Literal[False] = False,
    ) -> CustomPlayer | None: ...

    @overload
    async def get_player(
        self,
        ctx: commands.Context[Nameless],
        *,
        connect_if_needed: Literal[False] = False,
        raise_on_unconnected: Literal[False] = False,
    ) -> CustomPlayer | None: ...

    async def get_player(
        self,
        ctx: commands.Context[Nameless],
        *,
        connect_if_needed: bool = False,
        raise_on_unconnected: bool = False,
    ) -> CustomPlayer | None:
        if not ctx.guild:
            raise commands.CommandError("This command can only be used in a server!")

        if ctx.guild.voice_client:
            if not isinstance(ctx.guild.voice_client, self._get_custom_player_class()):
                raise ValueError("Voice client is not a CustomPlayer instance!")
            return ctx.guild.voice_client

        if raise_on_unconnected:
            raise ConnectionFailedError("No active voice connection found.")

        if connect_if_needed:
            return await self.connect_to_voice(ctx)

        return None

    async def get_player_by_guild_id(self, guild_id: int) -> CustomPlayer | None:
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return None

        if not isinstance(guild.voice_client, self._get_custom_player_class()):
            raise ValueError("Voice client is not a CustomPlayer instance!")

        return guild.voice_client

    async def get_or_create_player(self, ctx: commands.Context[Nameless]) -> CustomPlayer:
        player = await self.get_player(ctx, connect_if_needed=True, raise_on_unconnected=False)
        if player is None:
            raise ConnectionFailedError("Could not establish voice connection")
        return player

    async def connect_to_voice(
        self,
        ctx: commands.Context[Nameless],
        channel: discord.VoiceChannel | discord.StageChannel | None = None,
        bypass_checks: bool = False,
    ) -> CustomPlayer | None:
        await self.validate_voice_permissions(ctx, bypass_checks=bypass_checks)

        if channel is None and isinstance(ctx.author, discord.Member):
            if ctx.author.voice and ctx.author.voice.channel:
                channel = ctx.author.voice.channel
            else:
                raise NotInVoiceError()

        if not channel:
            raise NotInVoiceError()

        try:
            await channel.connect(self_deaf=True, cls=CustomPlayer)
            assert ctx.guild is not None  # for type checking
            player = cast("CustomPlayer", ctx.guild.voice_client)
            player.trigger_channel = ctx.channel
            player.start_disconnect_timer()

            if ctx.guild:
                logging.info(f"Connected to voice channel: {channel.name} in {ctx.guild.name}")
            return player

        except discord.ClientException as e:
            if "already connected" in str(e).lower():
                assert ctx.guild is not None  # for type checking
                return cast("CustomPlayer", ctx.guild.voice_client)
            raise ConnectionFailedError(str(e)) from e
        except Exception as e:
            logging.error(f"Failed to connect to voice channel: {e}")
            raise ConnectionFailedError(str(e)) from e

    def _get_custom_player_class(self):
        return CustomPlayer

    async def disconnect_player(self, ctx: commands.Context[Nameless]) -> bool:
        player = await self.get_player(ctx, connect_if_needed=False)
        if not player:
            return False

        await player.destroy()
        if ctx.guild:
            logging.info(f"Disconnected from voice channel in {ctx.guild.name}")
        return True

    async def ensure_same_voice_channel(self, ctx: commands.Context[Nameless], player: CustomPlayer) -> bool:
        if not isinstance(ctx.author, discord.Member):
            return False

        if not ctx.author.voice or not ctx.author.voice.channel:
            return False

        if not player.channel:
            return True

        return ctx.author.voice.channel.id == player.channel.id
