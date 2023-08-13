from typing import Optional

import discord
from typing_extensions import LiteralString


__all__ = ["NamelessConfig"]


class NamelessMetadata:
    # Any source control link, official repo by default.
    SOURCE_CODE_URL: LiteralString = "https://github.com/nameless-on-discord/nameless"

    # A link leading to the RAW version.txt file, used for upstream version checking
    UPSTREAM_VERSION_FILE: LiteralString = (
        "https://raw.githubusercontent.com/nameless-on-discord/nameless/main/version.txt"
    )

    # A link to the bot support server.
    SUPPORT_SERVER_URL: LiteralString = ""


class NamelessStatusFromDiscordActivity:
    # Activity type
    TYPE: discord.ActivityType = discord.ActivityType.playing

    # Name of the activity
    NAME: LiteralString = "something"

    # URL to the stream, only available for streaming activitiy
    URL: Optional[LiteralString] = None


class NamelessStatusFromCustomActivity:
    # Custom status line.
    CONTENT: LiteralString = ""

    # Emoji to be used in the custom status
    EMOJI: LiteralString = ""


class NamelessStatus:
    # Discord status
    STATUS: discord.Status = discord.Status.online

    # Discord activity
    DISCORD_ACTIVITY: NamelessStatusFromDiscordActivity = NamelessStatusFromDiscordActivity()

    # Custom activity, priortized over Discord activity.
    CUSTOM_ACTIVITY: NamelessStatusFromCustomActivity = NamelessStatusFromCustomActivity()


class NamelessDatabase:
    # Nameless' database connection string components.
    # Read more: https://docs.sqlalchemy.org/en/14/core/engines.html#database-urls
    DIALECT: LiteralString = "sqlite"
    DRIVER: LiteralString = ""
    USERNAME: LiteralString = ""
    PASSWORD: LiteralString = ""
    HOST: LiteralString = ""
    PORT: Optional[int] = None
    NAME: LiteralString = "nameless.db"


class NamelessMusicNode:
    def __init__(self, *, host: str, port: int, password: str, secure: bool = False) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.secure = secure


class NamelessMusicSpotifyClient:
    # Get it here: https://developer.spotify.com/dashboard/
    CLIENT_ID: LiteralString = ""
    CLIENT_SECRET: LiteralString = ""


class NamelessMusicSoundcloudClient:
    # Get it here: https://developers.soundcloud.com/
    USER_ID: LiteralString = ""
    CLIENT_ID: LiteralString = ""


class NamelessMusic:
    NODES: list[NamelessMusicNode] = [
        NamelessMusicNode(host="0.0.0.0", port=2333, password="youshallnotpass"),
    ]

    SPOTIFY: NamelessMusicSpotifyClient = NamelessMusicSpotifyClient()

    SOUNDCLOUD: NamelessMusicSoundcloudClient = NamelessMusicSoundcloudClient()


class NamelessIntent:
    # Choose when to receive texts
    # This will potentially slow down the bot if your bot is in many (large) guilds
    # This will decide whether the bot should:
    # - Receive text commands
    # - Receive response from prompts (will use default values)
    # (Requires "MESSAGE CONTENT" intent to be enabled on bot dashboard if this sets to True)
    # (Might require verification if the bot is over 100 guilds)
    # NOTE: MENTION PREFIX IS ENABLED BY DEFAULT!!!!!
    MESSAGE: bool = False

    # Choose when to receive member events
    # This will potentially slow down the bot if your bot is in many (large) guilds
    # This will decide whether the bot should:
    # - Receive guild member event (for welcome/goodbye notifications)
    # (Requires "GUILD MEMBERS" intent to be enabled on bot dashboard if this sets to True)
    # (Might require verification if the bot is over 100 guilds)
    MEMBER: bool = True


class NamelessOsu:
    # Get it here: https://osu.ppy.sh/docs/index.html#client-credentials-grant
    CLIENT_ID: int = 0
    CLIENT_SECRET: LiteralString = ""


class NamelessConfig:
    # Current version of nameless.
    # I ill advise you to NOT change this line
    __version__ = open("version.txt", "r").read().strip()

    # Bot description string
    __description__ = "Just a bot"

    # Add owners to Nameless
    # The bot creator is added by default
    # Bot team members are added by default
    # If you have nothing other than "the bot creator" and "team members", leave this as []
    # Otherwise, leave their IDs here: Right-click on a user -> Copy ID
    OWNERS: list[int] = []

    # Enable stuffs for developers
    # Set to True if you know what you are doing
    DEV: bool = False
    
    INTENT: NamelessIntent = NamelessIntent()

    # Bot token
    # Go to here: https://discord.com/developers/applications/
    # Then pick your client, then go to Bot->Copy Token
    TOKEN: LiteralString = ""

    # Metadata of the bot
    META: NamelessMetadata = NamelessMetadata()

    # Guild IDs to register commands
    # Leave empty array for global (slash commands takes one hour to mitigate, text takes immediately)
    GUILDS: list[int] = []

    # Choose which cog(s) to load
    # Available options:    Config,
    #                       Moderator,
    #                       MusicV1 (requires `LAVALINK` to be properly provided),
    #                       MusicV2 (MusicV1 must not be loaded)
    #                       Osu (requires `OSU` to be properly provided),
    #                       Owner
    COGS: list[LiteralString] = [
        "MusicLavalink",
        "Owner",
        "General",
        "Config",
        "Moderator",
        "Osu",
    ]

    # Guild prefixes for text commands
    PREFIXES: list[LiteralString] = ["nameless."]

    # Bot status
    STATUS: NamelessStatus = NamelessStatus()

    # Database configuration
    DATABASE: NamelessDatabase = NamelessDatabase()

    # Music configuration
    # Has both Lavalink & Native configuration fields
    MUSIC: NamelessMusic = NamelessMusic()

    # Configurations for osu! commands
    OSU: NamelessOsu = NamelessOsu()
