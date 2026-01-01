from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, override

import discord
from discord.ext import commands

from nameless.custom.ui.yes_no import NamelessYesNoPrompt

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Self

    from nameless import Nameless


class CommandChain:
    if TYPE_CHECKING:
        ctx: commands.Context[Nameless]
        original_interaction: discord.Interaction | None
        steps: list[
            tuple[str | Callable[..., Any], dict[str, Any], float, bool]
        ]  # (name, kwargs, delay, allow_failure)
        test_name: str
        validate: bool
        strict: bool
        failed_commands: list[tuple[str, str]]  # (command_name, error_message)

    def __init__(
        self,
        ctx: commands.Context[Nameless],
        *,
        test_name: str | None = None,
        validate: bool = True,
        strict: bool = True,
    ):
        self.ctx = ctx
        self.original_interaction = ctx.interaction
        self.steps = []
        self.test_name = test_name or "command chain"
        self.validate = validate
        self.strict = strict
        self.failed_commands = []

    def add(self, command: str, delay: float = 0, *, allow_failure: bool = False, **kwargs: Any) -> Self:
        self.steps.append((command, kwargs, delay, allow_failure))
        return self

    def add_function(
        self,
        func: Callable[..., Any],
        delay: float = 0,
        *,
        allow_failure: bool = False,
        **kwargs: Any,
    ) -> Self:
        self.steps.append((func, kwargs, delay, allow_failure))
        return self

    async def execute(self) -> None:
        if self.original_interaction and not self.original_interaction.response.is_done():
            await self.original_interaction.response.defer()

        for item, kwargs, delay, allow_failure in self.steps:
            if delay > 0:
                await asyncio.sleep(delay)

            if callable(item):
                await self._execute_single_function(item, kwargs, allow_failure)
            else:
                await self._execute_single_command(item, kwargs, allow_failure)

        if not self.strict and self.failed_commands:
            await self._show_failure_summary()

        if self.validate:
            await self._validate_execution()

    async def _execute_single_function(
        self,
        func: Callable[..., Any],
        kwargs: dict[str, Any],
        allow_failure: bool,
    ) -> None:
        func_name = getattr(func, "__name__", str(func))
        logging.info("Executing chained function: %s, %s", func_name, kwargs)

        try:
            result = func(self.ctx, **kwargs)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            error_msg = f"Error executing function '{func_name}': {e}"
            logging.error(error_msg)
            self.failed_commands.append((func_name, str(e)))
            await self._handle_command_failure(func_name, error_msg, allow_failure)

    async def _execute_single_command(
        self,
        cmd_name: str,
        kwargs: dict[str, Any],
        allow_failure: bool,
    ) -> None:
        cmd = self.ctx.bot.get_command(cmd_name)
        if not cmd:
            await self._handle_command_failure(cmd_name, "Command not found", allow_failure)
            return

        logging.info("Executing chained command: %s, %s", cmd_name, kwargs)
        chain_ctx = await self._create_chain_context()

        try:
            await chain_ctx.invoke(cmd, **kwargs)  # type: ignore
        except Exception as e:
            error_msg = f"Error executing chained command '{cmd_name}': {e}"
            logging.error(error_msg)
            self.failed_commands.append((cmd_name, str(e)))
            await self._handle_command_failure(cmd_name, error_msg, allow_failure)

    async def _handle_command_failure(self, cmd_name: str, error_msg: str, allow_failure: bool) -> None:
        should_stop = self.strict and not allow_failure

        if should_stop:
            await self.ctx.send(f"❌ **Strict mode**: Test stopped due to command failure\n```\n{error_msg}\n```")
            raise RuntimeError(f"Command '{cmd_name}' failed in strict mode")

        mode = "bypassed" if allow_failure else "non-strict mode"
        await self.ctx.send(f"⚠️ Command '{cmd_name}' failed ({mode}), continuing: {error_msg}")

    async def _show_failure_summary(self) -> None:
        embed = discord.Embed(
            title="⚠️ Command Chain Completed with Errors",
            description=f"{len(self.failed_commands)} command(s) failed during execution",
            color=discord.Color.orange(),
        )

        failure_text = "\n".join(f"• **{cmd}**: {err}" for cmd, err in self.failed_commands)
        embed.add_field(name="Failed Commands", value=failure_text[:1024], inline=False)

        logging.warning("Command chain '%s' completed with %d failures", self.test_name, len(self.failed_commands))
        await self.ctx.send(embed=embed)

    async def _create_chain_context(self) -> commands.Context[Nameless]:
        chain_ctx = await self.ctx.bot.get_context(self.ctx.message, cls=type(self.ctx))
        chain_ctx.interaction = None
        return chain_ctx

    async def _validate_execution(self) -> None:
        embed = discord.Embed(
            title="Test Execution Complete",
            description=f"Did '{self.test_name}' execute as expected?",
            color=discord.Color.blue(),
        )
        view = NamelessYesNoPrompt(timeout=30)
        prompt_msg = await self.ctx.send(embed=embed, view=view)

        await view.wait()

        if view.is_a_yes:
            logging.info("Test '%s' executed successfully", self.test_name)
            await prompt_msg.edit(
                embed=discord.Embed(
                    title="✅ Test Passed",
                    description="Test execution confirmed successful",
                    color=discord.Color.green(),
                ),
                view=None,
            )
        else:
            error_msg = f"Test '{self.test_name}' failed validation"
            logging.error(error_msg)
            await prompt_msg.edit(
                embed=discord.Embed(
                    title="❌ Test Failed",
                    description="Test execution failed validation",
                    color=discord.Color.red(),
                ),
                view=None,
            )
            raise RuntimeError(error_msg)


class TestCommand(commands.Cog):
    def __init__(self, bot: Nameless) -> None:
        self.bot = bot

    @override
    def cog_check(self, ctx: commands.Context[Nameless]) -> bool:  # type: ignore
        return ctx.author.id == 315309646179074048

    @commands.hybrid_command()
    async def test_player(
        self,
        ctx: commands.Context[Nameless],
        query: str,
    ) -> None:
        from nameless.command.music import MusicCommands  # noqa: PLC0415

        guild = ctx.guild
        if not guild:
            raise ValueError("This command must be used in a guild.")

        vcs = guild.voice_channels
        if not vcs:
            raise ValueError("No voice channels found in this guild.")
        channel = vcs[0]

        chain = CommandChain(ctx, test_name="test_player", validate=True, strict=False)
        await (
            chain.add(MusicCommands.connect.qualified_name, channel=channel)
            .add(
                MusicCommands.play.qualified_name,
                query=query,
            )
            .add(MusicCommands.queue.qualified_name, delay=1)
            .add(MusicCommands.skip.qualified_name, delay=1)
            .add(MusicCommands.disconnect.qualified_name, delay=5)
            .execute()
        )

    @commands.hybrid_command()
    @commands.guild_only()
    async def test_eq(self, ctx: commands.Context[Nameless]) -> None:
        from nameless.command.music import MusicCommands  # noqa: PLC0415

        guild = ctx.guild
        if not guild:
            raise ValueError("This command must be used in a guild.")

        vcs = guild.voice_channels
        if not vcs:
            raise ValueError("No voice channels found in this guild.")
        channel = vcs[0]

        await (
            CommandChain(ctx, test_name="test_player", validate=False, strict=True)
            .add(
                MusicCommands.connect.qualified_name,
                channel=channel,
                bypass_checks=True,
            )
            .add(
                MusicCommands.play.qualified_name,
                query="https://www.youtube.com/watch?v=U2i_IuAB6wo",
            )
            .add(MusicCommands.equalizer.qualified_name, delay=2)
            .execute()
        )

    @commands.hybrid_command()
    async def test_chain(
        self,
        ctx: commands.Context[Nameless],
    ) -> None:
        chain = CommandChain(ctx, test_name="test_chain", validate=True, strict=True)
        await (
            chain.add("nonexistent_command", allow_failure=True)
            .add("ping")
            .add("nonexistent_command_2", allow_failure=False)
            .add("ping")
            .execute()
        )


async def setup(bot: Nameless):
    await bot.add_cog(TestCommand(bot))
    logging.info("%s added!", __name__)


async def teardown(bot: Nameless):
    await bot.remove_cog(TestCommand.__cog_name__)
    logging.warning("%s removed!", __name__)
