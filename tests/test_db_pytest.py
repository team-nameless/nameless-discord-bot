from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from nameless.db import db
from nameless.db.crud import bulk_create, bulk_update, create, delete, get_by_pk, update
from nameless.db.models import CrossChatConnection, CrossChatMessage, CrossChatRoom, Guild, User
from sqlmodel import select

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def db_path() -> Path:
    return Path("test_nameless.db")


@pytest.fixture(scope="session", autouse=True)
async def setup_db(db_path: Path) -> AsyncGenerator[None, None]:
    if db_path.exists():
        db_path.unlink()

    await db.init(f"sqlite+aiosqlite:///{db_path}")

    yield

    await db.dispose()
    if db_path.exists():
        db_path.unlink()
    logger.info("Test database cleaned up")


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with db.get_session_context() as session:
        yield session


@pytest.mark.asyncio
async def test_guild_create(session: AsyncSession) -> None:
    guild = Guild(Id=123456789, HoneypotChannelId=987654321)
    created_guild = await create(session, guild)

    assert created_guild.Id == 123456789
    assert created_guild.HoneypotChannelId == 987654321


@pytest.mark.asyncio
async def test_guild_get_by_pk(session: AsyncSession) -> None:
    guild = Guild(Id=223456789, HoneypotChannelId=987654321)
    await create(session, guild)

    async with db.get_session_context() as new_session:
        fetched_guild = await get_by_pk(new_session, Guild, 223456789)
        assert fetched_guild is not None
        assert fetched_guild.HoneypotChannelId == 987654321


@pytest.mark.asyncio
async def test_guild_update(session: AsyncSession) -> None:
    guild = Guild(Id=323456789, HoneypotChannelId=987654321)
    await create(session, guild)

    async with db.get_session_context() as new_session:
        updated_guild = await update(
            new_session,
            Guild,
            323456789,
            {"HoneypotChannelId": 111111111},
        )
        assert updated_guild.HoneypotChannelId == 111111111

    async with db.get_session_context() as verify_session:
        refetched_guild = await get_by_pk(verify_session, Guild, 323456789)
        assert refetched_guild is not None
        assert refetched_guild.HoneypotChannelId == 111111111


@pytest.mark.asyncio
async def test_guild_delete(session: AsyncSession) -> None:
    guild = Guild(Id=423456789, HoneypotChannelId=987654321)
    await create(session, guild)

    async with db.get_session_context() as new_session:
        deleted = await delete(new_session, Guild, 423456789)
        assert deleted is True

    async with db.get_session_context() as verify_session:
        deleted_guild = await get_by_pk(verify_session, Guild, 423456789)
        assert deleted_guild is None


@pytest.mark.asyncio
async def test_user_crud(session: AsyncSession) -> None:
    user = User(Id=111222333, MaimaiFriendCode=999888777)
    created_user = await create(session, user)
    assert created_user.Id == 111222333

    async with db.get_session_context() as new_session:
        updated_user = await update(
            new_session,
            User,
            111222333,
            {"MaimaiFriendCode": 123456789},
        )
        assert updated_user.MaimaiFriendCode == 123456789

    async with db.get_session_context() as new_session:
        deleted = await delete(new_session, User, 111222333)
        assert deleted is True


@pytest.mark.asyncio
async def test_crosschat_relationships(session: AsyncSession) -> None:
    guild = Guild(Id=999888777)
    await create(session, guild)

    room = CrossChatRoom(GuildId=999888777, ChannelId=111111111, IsPublic=True)
    created_room = await create(session, room)
    room_uuid = created_room.UUID

    connection = CrossChatConnection(
        SourceGuildId=999888777,
        SourceChannelId=222222222,
        TargetGuildId=999888777,
        TargetChannelId=111111111,
        RoomId=room_uuid,
    )
    created_connection = await create(session, connection)
    connection_uuid = created_connection.UUID

    message = CrossChatMessage(
        ConnectionId=connection_uuid,
        OriginMessageId=123456789,
        ClonedMessageId=987654321,
    )
    created_message = await create(session, message)

    async with db.get_session_context() as verify_session:
        stmt = select(CrossChatConnection).where(connection_uuid == CrossChatConnection.UUID)
        result = await verify_session.execute(stmt)
        fetched_connection = result.scalars().one_or_none()
        assert fetched_connection is not None
        assert fetched_connection.RoomId == room_uuid

    async with db.get_session_context() as cleanup_session:
        await delete(cleanup_session, CrossChatMessage, created_message.Id)
        await delete(cleanup_session, CrossChatConnection, created_connection.Id)
        await delete(cleanup_session, CrossChatRoom, created_room.Id)
        await delete(cleanup_session, Guild, 999888777)


@pytest.mark.asyncio
async def test_bulk_create(session: AsyncSession) -> None:
    guild_data = [{"Id": 1000 + i, "HoneypotChannelId": 2000 + i} for i in range(10)]
    created_ids = await bulk_create(session, Guild, guild_data, return_ids=True)

    assert len(created_ids) == 10

    async with db.get_session_context() as verify_session:
        first_guild = await get_by_pk(verify_session, Guild, 1000)
        assert first_guild is not None
        assert first_guild.HoneypotChannelId == 2000

    async with db.get_session_context(commit=False) as cleanup_session:
        for i in range(10):
            await delete(cleanup_session, Guild, 1000 + i, commit=False)
        await cleanup_session.commit()


@pytest.mark.asyncio
async def test_bulk_update(session: AsyncSession) -> None:
    guild_data = [{"Id": 2000 + i, "HoneypotChannelId": 3000 + i} for i in range(10)]
    await bulk_create(session, Guild, guild_data)

    update_data = [{"Id": 2000 + i, "HoneypotChannelId": 4000 + i} for i in range(10)]
    async with db.get_session_context() as update_session:
        await bulk_update(update_session, Guild, update_data)

    async with db.get_session_context() as verify_session:
        updated_guild = await get_by_pk(verify_session, Guild, 2000)
        assert updated_guild is not None
        assert updated_guild.HoneypotChannelId == 4000

    async with db.get_session_context(commit=False) as cleanup_session:
        for i in range(10):
            await delete(cleanup_session, Guild, 2000 + i, commit=False)
        await cleanup_session.commit()


@pytest.mark.asyncio
async def test_update_nonexistent_record_raises_error(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="not found"):
        await update(session, Guild, 999999999, {"HoneypotChannelId": 0})


@pytest.mark.asyncio
async def test_delete_nonexistent_record_returns_false(session: AsyncSession) -> None:
    deleted = await delete(session, Guild, 999999999)
    assert deleted is False


@pytest.mark.asyncio
async def test_bulk_update_missing_pk_raises_error(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="missing primary key"):
        await bulk_update(session, Guild, [{"HoneypotChannelId": 123}])


@pytest.mark.parametrize(
    ("guild_id", "honeypot_id"),
    [
        (1, 100),
        (2, 200),
        (3, 300),
    ],
)
@pytest.mark.asyncio
async def test_guild_create_parametrized(session: AsyncSession, guild_id: int, honeypot_id: int) -> None:
    guild = Guild(Id=guild_id, HoneypotChannelId=honeypot_id)
    created_guild = await create(session, guild)

    assert created_guild.Id == guild_id
    assert created_guild.HoneypotChannelId == honeypot_id

    async with db.get_session_context() as cleanup_session:
        await delete(cleanup_session, Guild, guild_id)
