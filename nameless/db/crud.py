from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import sqlalchemy as sa
from sqlmodel import SQLModel, select

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Session as OrmSession


__all__ = [
    "bulk_create",
    "bulk_update",
    "create",
    "delete",
    "get_by_pk",
    "update",
]


async def get_by_pk[T: SQLModel](
    session: AsyncSession,
    model: type[T],
    pk_value: int | str,
    pk_field: str = "Id",
) -> T | None:
    stmt = select(model).where(getattr(model, pk_field) == pk_value)
    result = await session.execute(stmt)
    return result.scalars().one_or_none()


async def create[T: SQLModel](
    session: AsyncSession,
    instance: T,
    *,
    commit: bool = True,
    refresh: bool = True,
) -> T:
    session.add(instance)
    try:
        if commit:
            await session.commit()
        else:
            # ensure DB-side defaults / PKs are populated
            await session.flush()

        if refresh:
            await session.refresh(instance)

        return instance
    except Exception:
        await session.rollback()
        logger.exception("failed to create instance %s", instance)
        raise


async def update[T: SQLModel](
    session: AsyncSession,
    model: type[T],
    pk_value: int | str,
    update_kwargs: dict[str, Any],
    pk_field: str = "Id",
    *,
    commit: bool = True,
    refresh: bool = True,
) -> T:
    obj = await get_by_pk(session, model, pk_value, pk_field=pk_field)
    if obj is None:
        raise ValueError(f"{model.__name__} with id {pk_value} not found")

    try:
        obj.sqlmodel_update(update_kwargs)
    except ValueError:
        logger.debug("sqlmodel_update failed; falling back to setattr for %s id=%s", model.__name__, pk_value)
        for k, v in update_kwargs.items():
            if not hasattr(obj, k):
                logger.warning("attribute %s not found on %s; skipping update", k, model.__name__)
                continue
            setattr(obj, k, v)

    session.add(obj)
    try:
        if commit:
            await session.commit()
        else:
            await session.flush()

        if refresh:
            await session.refresh(obj)

        return obj
    except Exception:
        await session.rollback()
        logger.exception("failed to update %s id=%s", model.__name__, pk_value)
        raise


async def delete[T: SQLModel](
    session: AsyncSession,
    model: type[T],
    pk_value: int | str,
    pk_field: str = "Id",
    *,
    commit: bool = True,
) -> bool:
    try:
        stmt = sa.delete(model).where(getattr(model, pk_field) == pk_value)
        result = await session.execute(stmt)

        if commit:
            await session.commit()
        else:
            await session.flush()

        return cast("sa.CursorResult[Any]", result).rowcount > 0
    except Exception:
        await session.rollback()
        logger.exception("failed to delete %s id=%s", model.__name__, pk_value)
        raise


async def bulk_create(
    session: AsyncSession,
    model: type[SQLModel],
    rows: Iterable[dict[str, Any]],
    *,
    commit: bool = True,
    chunk_size: int = 500,
    return_ids: bool = True,
) -> list[int | str]:
    ids: list[int | str] = []
    rows_list = list(rows)
    if not rows_list:
        return ids

    pk_attr = getattr(model, "Id", None)
    try:
        for i in range(0, len(rows_list), chunk_size):
            chunk = rows_list[i : i + chunk_size]
            stmt = sa.insert(model).values(chunk)
            if return_ids and pk_attr is not None:
                stmt = stmt.returning(pk_attr)
                res = await session.execute(stmt)
                ids.extend(res.scalars().all())
            else:
                await session.execute(stmt)

        if commit:
            await session.commit()
        else:
            await session.flush()

        return ids
    except Exception:
        await session.rollback()
        logger.exception("failed to bulk create for %s", getattr(model, "__name__", str(model)))
        raise


async def bulk_update(
    session: AsyncSession,
    model: type[SQLModel],
    mappings: Iterable[dict[str, Any]],
    *,
    pk_field: str = "Id",
    commit: bool = True,
    chunk_size: int = 200,
) -> None:
    maps = list(mappings)
    if not maps:
        return None

    try:
        # for i in range(0, len(maps), chunk_size):
        #     chunk = maps[i : i + chunk_size]
        #     for mapping in chunk:
        #         if pk_field not in mapping:
        #             raise ValueError(f"mapping missing primary key field {pk_field}: {mapping}")
        #         pk_value = mapping[pk_field]
        #         # copy values without pk
        #         values = {k: v for k, v in mapping.items() if k != pk_field}
        #         if not values:
        #             continue
        #         stmt = sa.update(model).where(getattr(model, pk_field) == pk_value).values(**values)
        #         await session.execute(stmt)
        for mapping in maps:
            if pk_field not in mapping:
                raise ValueError(f"mapping missing primary key field {pk_field}: {mapping}")

        mapper = sa.inspect(model).mapper

        def _do_bulk_update(sync_session: OrmSession, data: list[dict[str, Any]]) -> None:
            sync_session.bulk_update_mappings(mapper, data)

        for i in range(0, len(maps), chunk_size):
            chunk = maps[i : i + chunk_size]
            await session.run_sync(_do_bulk_update, chunk)

        if commit:
            await session.commit()
        else:
            await session.flush()
    except Exception:
        await session.rollback()
        logger.exception("failed to bulk update for %s", getattr(model, "__name__", str(model)))
        raise
