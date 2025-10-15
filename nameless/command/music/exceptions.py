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


class InvalidParameterError(MusicError):
    def __init__(self, parameter: str, reason: str):
        super().__init__(f"Invalid parameter '{parameter}': {reason}")


class InvalidVolumeError(InvalidParameterError):
    def __init__(self, volume: int):
        super().__init__("volume", f"{volume}. Volume must be between 0 and 200.")


class InvalidPositionError(InvalidParameterError):
    def __init__(self, position: int, max_position: int):
        super().__init__("position", f"{position}. Must be between 1 and {max_position}.")


class TrackNotSeekableError(MusicError):
    def __init__(self):
        super().__init__("This track cannot be seeked (likely a live stream).")


class NoTracksFoundError(MusicError):
    def __init__(self, query: str):
        super().__init__(f"No tracks found for: **{query}**")


class ConnectionFailedError(MusicError):
    def __init__(self, reason: str = "Unknown reason"):
        super().__init__(f"Failed to connect to voice channel: {reason}")


class AutoplayDisabledError(MusicError):
    def __init__(self):
        super().__init__("Autoplay is currently disabled. Enable it with `/music autoplay enable`.")
