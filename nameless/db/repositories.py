# pyright: reportMissingParameterType=false, reportUnknownParameterType=false

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import col, func, select

from .crud import create, delete, get_by_pk, update
from .models import BaseModel, CrossChatConnection, CrossChatMessage, CrossChatRoom, Guild, User

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


__all__ = [
    "BaseRepository",
    "CrossChatConnectionRepository",
    "CrossChatMessageRepository",
    "CrossChatRoomRepository",
    "GuildRepository",
    "UserRepository",
]


class BaseRepository[T: BaseModel]:
    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self.session = session
        self.model = model

    async def create(
        self,
        instance: T,
        *,
        commit: bool = True,
        refresh: bool = True,
    ) -> T:
        """Create a new record."""
        await create(self.session, instance, commit=commit, refresh=refresh)
        return instance

    async def get_by_id(self, pk_id: int) -> T | None:
        obj = await get_by_pk(self.session, self.model, pk_id, pk_field="Id")
        return obj if obj is not None else None

    async def get_or_create(
        self,
        pk_id: int,
        *,
        commit: bool = True,
        refresh: bool = True,
    ) -> T:
        obj = await self.get_by_id(pk_id)
        if obj is not None:
            return obj

        instance = self.model(Id=pk_id)
        await create(self.session, instance, commit=commit, refresh=refresh)
        return instance

    async def update(
        self,
        pk_id: int,
        data: dict[str, Any],
        *,
        commit: bool = True,
        refresh: bool = True,
    ) -> T | None:
        obj = await update(
            self.session,
            self.model,
            pk_id,
            data,
            pk_field="Id",
            commit=commit,
            refresh=refresh,
        )
        return obj

    async def delete(
        self,
        pk_id: int,
        *,
        commit: bool = True,
    ) -> bool:
        return await delete(self.session, self.model, pk_id, pk_field="Id", commit=commit)

    async def exists(self, pk_id: int) -> bool:
        obj = await self.get_by_id(pk_id)
        return obj is not None

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_all(self, *, limit: int | None = None, offset: int = 0) -> list[T]:
        stmt = select(self.model).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_many_by_ids(self, pk_ids: list[int]) -> list[T]:
        if not pk_ids:
            return []
        stmt = select(self.model).where(col(self.model.Id).in_(pk_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def refresh(self, instance: T) -> T:
        await self.session.refresh(instance)
        return instance

    async def __aenter__(self) -> BaseRepository[T]:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:  # noqa
        return


class GuildRepository(BaseRepository[Guild]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Guild)

    async def has_honeypot(self, guild_id: int) -> bool:
        guild = await self.get_by_id(guild_id)
        return guild is not None and guild.HoneypotChannelId != 0

    async def get_guilds_with_honeypot(self) -> list[Guild]:
        stmt = select(Guild).where(Guild.HoneypotChannelId != 0)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def has_maimai_linked(self, user_id: int) -> bool:
        user = await self.get_by_id(user_id)
        return user is not None and user.MaimaiFriendCode != 0

    async def get_by_friend_code(self, friend_code: int) -> User | None:
        stmt = select(User).where(User.MaimaiFriendCode == friend_code)
        stmt = select(User).where(User.MaimaiFriendCode == friend_code)
        result = await self.session.execute(stmt)
        return result.scalars().first()


class CrossChatRoomRepository(BaseRepository[CrossChatRoom]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CrossChatRoom)

    async def get_by_channel(self, guild_id: int, channel_id: int) -> CrossChatRoom | None:
        stmt = select(CrossChatRoom).where(
            CrossChatRoom.GuildId == guild_id,
            CrossChatRoom.ChannelId == channel_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_uuid(self, uuid: str) -> CrossChatRoom | None:
        stmt = select(CrossChatRoom).where(uuid == CrossChatRoom.UUID)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_public_rooms(self) -> list[CrossChatRoom]:
        stmt = select(CrossChatRoom).where(CrossChatRoom.IsPublic == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class CrossChatConnectionRepository(BaseRepository[CrossChatConnection]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CrossChatConnection)

    async def get_by_source(self, guild_id: int, channel_id: int) -> list[CrossChatConnection]:
        stmt = select(CrossChatConnection).where(
            CrossChatConnection.SourceGuildId == guild_id,
            CrossChatConnection.SourceChannelId == channel_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_source_and_target(
        self, source_guild_id: int, source_channel_id: int, target_guild_id: int, target_channel_id: int
    ) -> CrossChatConnection | None:
        stmt = select(CrossChatConnection).where(
            CrossChatConnection.SourceGuildId == source_guild_id,
            CrossChatConnection.SourceChannelId == source_channel_id,
            CrossChatConnection.TargetGuildId == target_guild_id,
            CrossChatConnection.TargetChannelId == target_channel_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_room(self, room_id: str) -> list[CrossChatConnection]:
        stmt = select(CrossChatConnection).where(CrossChatConnection.RoomId == room_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_room_and_source(self, room_id: str, guild_id: int, channel_id: int) -> CrossChatConnection | None:
        stmt = select(CrossChatConnection).where(
            CrossChatConnection.RoomId == room_id,
            CrossChatConnection.SourceGuildId == guild_id,
            CrossChatConnection.SourceChannelId == channel_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def delete_by_room(self, room_id: str, *, commit: bool = True) -> int:
        connections = await self.get_by_room(room_id)
        count = 0
        for conn in connections:
            deleted = await self.delete(conn.Id, commit=False)
            if deleted:
                count += 1
        if commit:
            await self.session.commit()
        return count


class CrossChatMessageRepository(BaseRepository[CrossChatMessage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CrossChatMessage)

    async def get_by_origin_message(self, connection_id: str, origin_message_id: int) -> CrossChatMessage | None:
        stmt = select(CrossChatMessage).where(
            CrossChatMessage.ConnectionId == connection_id,
            CrossChatMessage.OriginMessageId == origin_message_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_connection(self, connection_id: str) -> list[CrossChatMessage]:
        stmt = select(CrossChatMessage).where(CrossChatMessage.ConnectionId == connection_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
