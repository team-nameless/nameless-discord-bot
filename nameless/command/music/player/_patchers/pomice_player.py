from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pomice

if TYPE_CHECKING:
    from pomice import Player

logger = logging.getLogger(__name__)


async def _patched_destroy(self: Player) -> None:
    try:
        await self.disconnect()
    except AttributeError:
        assert self.channel is None and not self.is_connected

    self._node._players.pop(self.guild.id, None)

    if self.node.is_connected:
        try:
            await self._node.send(
                method="DELETE",
                path=self._player_endpoint_uri,
                guild_id=self._guild.id,
            )
        except Exception as e:
            logger.debug("error destroying player on lavalink node: %s", e, exc_info=True)

    if self._log:
        self._log.debug("player has been destroyed")


def apply_player_destroy_patch() -> None:
    if getattr(pomice.Player, "_unpatched_destroy", False):
        return

    method_name = "destroy"
    original_method = getattr(pomice.Player, method_name, None)
    if original_method is None:
        raise RuntimeError(f"Could not find method '{method_name}' on 'pomice.Player' to patch.")

    setattr(pomice.Player, method_name, _patched_destroy)
    setattr(pomice.Player, "_unpatched_destroy", original_method)  # noqa
