import discord
import wavelink


class NamelessPlayer(wavelink.Player):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable, **kwargs):
        super().__init__(client, channel, **kwargs)

        self.trigger_channel_id: int = 0
        self.play_now_allowed: int = 0
