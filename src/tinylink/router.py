import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import insert, delete, update, text
from datetime import datetime
from typing import List, Optional
from src.auth.users import current_active_user
from src.database import get_async_session
from src.tinylink.schemas import LinkResponse, LinkCreate, LinkUpdate
from src.tinylink.models import linkdata
from src.auth.db import User
from urllib.parse import unquote
from fastapi import Query
from datetime import timedelta
from src.config import  DEACTIVATION_DAYS
from sqlalchemy import func


# Настройка Redis
redis_client = redis.StrictRedis(host='redis_app', port=6379, db=0, decode_responses=True)

router = APIRouter(
    prefix="/tinylink",
    tags=["tinylink"]
)

@router.post("/links/shorten", response_model=LinkResponse)
async def shorten_link(
    link: LinkCreate,
    session: AsyncSession = Depends(get_async_session),
    user: Optional[User] = Depends(current_active_user)
):
    user_id = user.id if user else None
    code_length = 10 if user_id is None else 6

    # Check if custom_alias is provided and not already taken
    if link.custom_alias:
        if redis_client.exists(f"link:{link.custom_alias}"):
            raise HTTPException(status_code=400, detail="Custom alias already taken")

    # Check if the original URL already exists in the database
    result = await session.execute(
        select(linkdata).where(linkdata.c.original_url == link.original_url, linkdata.c.is_active == True)
    )
    existing_link = result.fetchone()

    if existing_link:
        return LinkResponse(
            short_code=existing_link.short_code,
            original_url=existing_link.original_url,
            user_id=existing_link.user_id
        )

    # Generate a unique short code using the PostgreSQL function
    if link.custom_alias:
        short_code = link.custom_alias
    else:
        result = await session.execute(
            text("SELECT generate_unique_short_code(:length)").bindparams(length=code_length)
        )
        short_code = result.scalar()

    # Устанавливаем expires_at, если пользователь не залогинен (по умолчанию 1 неделя)
    if user_id is None:
        expires_at = datetime.utcnow() + timedelta(weeks=1)
    else:
        expires_at = link.expires_at

    if isinstance(expires_at, str):
        expires_at = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S.%f')

    # Проверяем, что expires_at не истек
    if expires_at is not None and expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Expiration date cannot be in the past")

    insert_data = {
        "original_url": link.original_url,
        "short_code": short_code,
        "user_id": user_id,
        "expires_at": expires_at  # Записываем срок действия в БД
    }

    stmt = insert(linkdata).values(insert_data)
    await session.execute(stmt)
    await session.commit()

    # Cache the link in Redis
    redis_client.setex(f"link:{short_code}", 3600, link.original_url)
    redis_client.zadd("usage_count", {short_code: 0})

    return LinkResponse(short_code=short_code, original_url=link.original_url, user_id=user_id, expires_at=expires_at)


@router.get("/link/{short_code}")
async def redirect_to_original(short_code: str, session: AsyncSession = Depends(get_async_session)):
    cached_url = redis_client.get(f"link:{short_code}")
    if cached_url:
        # Retrieve usage_count from Redis and increment it
        usage_count = redis_client.zscore("usage_count", short_code)
        if usage_count is None:
            # Fetch from DB if not in Redis
            result = await session.execute(
                select(linkdata.c.usage_count).where(func.lower(linkdata.c.short_code) == func.lower(short_code), linkdata.c.is_active == True)
            )
            db_usage_count = result.scalar() or 0
            redis_client.zadd("usage_count", {short_code: db_usage_count})

        redis_client.zincrby("usage_count", 1, short_code)

        # Update `last_used_at` in Redis
        redis_client.set(f"last_used_at:{short_code}", datetime.utcnow().isoformat())

        return RedirectResponse(url=cached_url)

    # Fetch link from the database
    result = await session.execute(
        select(linkdata).where(func.lower(linkdata.c.short_code) == func.lower(short_code), linkdata.c.is_active == True)
    )
    link = result.fetchone()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Link has expired")
    if not link.is_active:
        raise HTTPException(status_code=403, detail="Link is deactivated due to inactivity")

    new_usage_count = link.usage_count + 1
    last_used_at = datetime.utcnow()

    stmt = (
        update(linkdata)
        .where(linkdata.c.short_code == short_code, linkdata.c.is_active == True)
        .values(
            usage_count=new_usage_count,  # Increment usage_count
            last_used_at=last_used_at,  # Update last_used_at
        )
    )
    await session.execute(stmt)
    await session.commit()

    redis_client.setex(f"link:{short_code}", 3600, link.original_url)  # Cache URL for 1 hour
    redis_client.zadd("usage_count", {short_code: new_usage_count})  # Store updated count in Redis
    redis_client.set(f"last_used_at:{short_code}", last_used_at.isoformat())  # Store last_used_at in Redis

    return RedirectResponse(url=link.original_url)


@router.delete("/links/{short_code}", response_model=LinkResponse)
async def delete_link(
        short_code: str,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    result = await session.execute(
        select(linkdata).where(linkdata.c.short_code == short_code)
    )
    link = result.fetchone()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if link.user_id != user.id:
        raise HTTPException(status_code=403, detail="You are not the owner of this link")

    await session.execute(delete(linkdata).where(linkdata.c.short_code == short_code, linkdata.c.is_active == True))
    await session.commit()

    redis_client.delete(f"link:{short_code}")
    redis_client.zrem("usage_count", short_code)

    return LinkResponse(short_code=link.short_code, original_url=link.original_url, user_id=link.user_id)


@router.put("/links/{short_code}", response_model=LinkResponse)
async def update_link(
        short_code: str,
        link_update: LinkUpdate,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    result = await session.execute(
        select(linkdata).where(linkdata.c.short_code == short_code, linkdata.c.is_active == True)
    )
    link = result.fetchone()

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if link.user_id != user.id:
        raise HTTPException(status_code=403, detail="You are not the owner of this link")

    update_values = {}
    if link_update.original_url:
        update_values["original_url"] = link_update.original_url

    if link_update.expires_at:
        if isinstance(link_update.expires_at, str):
            link_update.expires_at = datetime.strptime(link_update.expires_at, '%Y-%m-%d %H:%M:%S.%f')
        update_values["expires_at"] = link_update.expires_at

    stmt = update(linkdata).where(linkdata.c.short_code == short_code, linkdata.c.is_active == True).values(update_values)
    await session.execute(stmt)
    await session.commit()

    redis_client.delete(f"link:{short_code}")
    redis_client.zrem("usage_count", short_code)

    if hasattr(link_update, 'original_url'):
        original_url = link_update.original_url
    else:
        original_url = None

    if hasattr(link_update, 'expires_at'):
        expires_at = link_update.expires_at
    else:
        expires_at = None

    return LinkResponse(short_code=short_code, original_url=original_url, expires_at=expires_at, user_id=user.id)


@router.get("/links/{short_code}/stats")
async def link_stats(
        short_code: str,
        session: AsyncSession = Depends(get_async_session)
):
    clicks = redis_client.zscore("usage_count", short_code)
    last_used_at = redis_client.get(f"last_used_at:{short_code}")
    if clicks is None:
        result = await session.execute(
            select(linkdata).where(linkdata.c.short_code == short_code, linkdata.c.is_active == True)
        )
        link = result.fetchone()
        clicks = link.usage_count
        last_used_at = link.last_used_at

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

    stats = {
        "original_url": link.original_url,
        "created_at": link.created,
        "clicks": clicks,
        "last_used_at": last_used_at
    }

    return stats

@router.get("/links/search", response_model=List[LinkResponse])
async def search_links_by_original_url(
    original_url: str = Query(..., title="Original URL", description="URL to search for"),
    session: AsyncSession = Depends(get_async_session)
):
    # Декодируем URL, если он закодирован
    decoded_url = unquote(original_url)

    # Ищем ссылки в базе
    result = await session.execute(
        select(linkdata).where(linkdata.c.original_url == decoded_url, linkdata.c.is_active == True)
    )
    links = result.fetchall()

    if not links:
        raise HTTPException(status_code=404, detail="No links found")

    # Преобразуем результат в список словарей
    return [
        LinkResponse(
            short_code=link.short_code,
            original_url=link.original_url,
            user_id=link.user_id
        ) for link in links
    ]

@router.get("/links/expired", response_model=list[LinkResponse])
async def get_expired_links(session: AsyncSession = Depends(get_async_session)):
    # Получаем текущую дату и время
    now = datetime.now()

    # Запрос всех ссылок, срок действия которых истек
    result = await session.execute(
        select(linkdata).where(linkdata.c.expires_at < now, linkdata.c.is_active == True)
    )
    expired_links = result.fetchall()

    if not expired_links:
        raise HTTPException(status_code=404, detail="No expired links found")

    return [
        LinkResponse(
            short_code=link.short_code,
            original_url=link.original_url,
            user_id=link.user_id
        )
        for link in expired_links
    ]

@router.post("/links/deactivate_unused")
async def deactivate_unused_links(
    session: AsyncSession = Depends(get_async_session),
    user: Optional[User] = Depends(current_active_user),
):
    # Check if the user is authenticated
    if user is None:
        raise HTTPException(
            status_code=403, detail="Only registered users can use this endpoint"
        )

    # Check if the user is a superuser
    if not user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Only superusers can deactivate links"
        )

    threshold_date = datetime.now() - timedelta(days=int(DEACTIVATION_DAYS))
    # Find links that haven't been used for N days and are still active
    result = await session.execute(
        select(linkdata.c.short_code, linkdata.c.original_url).where(
            linkdata.c.last_used_at < threshold_date, linkdata.c.is_active == False
        )
    )
    unused_links = result.fetchall()

    if not unused_links:
        return {"message": "No links to deactivate"}

    # Extract short_code and original_url for the response
    deactivated_links = [
        {"short_code": link.short_code, "original_url": link.original_url}
        for link in unused_links
    ]

    # Update the status of the links to inactive
    stmt = (
        update(linkdata)
        .where(linkdata.c.last_used_at < threshold_date, linkdata.c.is_active == False)
        .values(is_active=False)
    )
    await session.execute(stmt)
    await session.commit()

    return {
        "message": f"Deactivated {len(deactivated_links)} links",
        "deactivated_links": deactivated_links,
    }