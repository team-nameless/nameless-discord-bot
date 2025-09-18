from discord.ext import commands


class MusicError(commands.CommandError):
    pass


class NoPlayerError(MusicError):
    def __init__(self):
        super().__init__("I'm not connected to a voice channel. Use `/music connect` first!")


class NotInVoiceError(MusicError):
    def __init__(self):
        super().__init__("You need to be in a voice channel to use this command!")


class EmptyQueueError(MusicError):
    def __init__(self):
        super().__init__("The queue is empty! Add some tracks with `/music play`.")
