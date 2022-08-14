from typing import Callable

import discord
from discord.ext import commands

__all__ = ["DiscordWaiter"]


class DiscordWaiter:
    @staticmethod
    def message_waiter(ctx: commands.Context) -> Callable[[discord.Message], bool]:
        """
        Message waiter to use with Client.wait_for("message", ...).

        Usages:
            message: discord.Message = await bot.wait_for("message", check=wait_for)

        :param ctx: Current context.
        :return: The waiter function.
        """

        def message_checker(message: discord.Message) -> bool:
            return message.author.id == ctx.author.id and ctx.channel.id == message.channel.id

        return message_checker
