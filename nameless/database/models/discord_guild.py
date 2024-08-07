from sqlalchemy import BigInteger, UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

from nameless.database.models.discord_snowflake import DiscordObject

__all__ = ["DbGuild"]


class DbGuild(DiscordObject):
    __tablename__ = "Guilds"

    is_welcome_enabled: Mapped[bool] = mapped_column("IsWelcomeEnabled", default=True)
    is_goodbye_enabled: Mapped[bool] = mapped_column("IsGoodbyeEnabled", default=True)
    is_bot_greeting_enabled: Mapped[bool] = mapped_column("IsBotGreetingEnabled", default=True)
    is_dm_preferred: Mapped[bool] = mapped_column("IsDmPreferred", default=False)
    welcome_channel_id: Mapped[int] = mapped_column("WelcomeChannelId", BigInteger, default=0)
    goodbye_channel_id: Mapped[int] = mapped_column("GoodbyeChannelId", BigInteger, default=0)
    welcome_message: Mapped[str] = mapped_column("WelcomeMessage", UnicodeText, default="")
    goodbye_message: Mapped[str] = mapped_column("GoodbyeMessage", UnicodeText, default="")
    audio_role_id: Mapped[int] = mapped_column("AudioRoleId", BigInteger, default=0)
    voice_room_channel_id: Mapped[int] = mapped_column("VoiceRoomChannelId", BigInteger, default=0)
