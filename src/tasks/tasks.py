from fastapi import APIRouter, Depends, BackgroundTasks
from src.database import get_async_session, get_session
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from sqlalchemy import update
from datetime import datetime, timedelta
from src.tinylink.models import linkdata
from sqlalchemy.future import select

from src.tinylink.router import redis_client

router = APIRouter(prefix="/task")

EXPIRATION_DAYS = 30


@router.post("/cleanup")
async def cleanup_unused_links():
    """Запускает фоновую задачу для удаления неиспользуемых ссылок."""
    #delete_unused_links.delay()  # Отправляем задачу Celery в очередь
    return {"message": "Cleanup task started."}

@router.on_event("startup")
async def start_background_task():
    """
    Starts the background task when the FastAPI server starts.
    """
    session = await get_async_session().__anext__()  # Get DB session
    asyncio.create_task(sync_usage_data(session))  # Run in the background
    asyncio.create_task(periodic_delete_unused_links(session))  # Run daily cleanup

@router.get("/trigger-sync/")
async def trigger_sync_task(background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_async_session)):
    """
    Manually trigger the sync process (optional API).
    """
    background_tasks.add_task(sync_usage_data, session)
    background_tasks.add_task(periodic_delete_unused_links, session)
    return {"message": "Background sync task started"}

async def sync_usage_data(session: AsyncSession):
    """
    Periodically updates usage_count and last_used_at from Redis to the database.
    """
    while True:
        current_time = datetime.utcnow()
        usage_counts = redis_client.zrange("usage_count", 0, -1, withscores=True)
        for short_code, usage_count in usage_counts:
            last_used_at = redis_client.get(f"last_used_at:{short_code}")
            if last_used_at:
                last_used_at = datetime.fromisoformat(last_used_at)
                if current_time - last_used_at <= timedelta(seconds=10):
                    # Update database
                    stmt = (
                        update(linkdata)
                        .where(linkdata.c.short_code == short_code)
                        .values(
                            usage_count=int(usage_count),
                            last_used_at=last_used_at or datetime.utcnow(),
                        )
                    )
                    await session.execute(stmt)
        await session.commit()
        await asyncio.sleep(10)  # Wait 1 minute before the next update


async def periodic_delete_unused_links(session2: AsyncSession):
    """
    Periodically runs the delete_unused_links task once per day.
    """
    while True:
        session = await get_session()
        async with session:
            # Run the cleanup task
            """
            Deletes links that have not been used for more than DEACTIVATION_DAYS.
            """
            threshold_date = datetime.utcnow() - timedelta(days=EXPIRATION_DAYS)
            # Find unused links
            result = await session.execute(
                select(linkdata).where(
                    linkdata.c.last_used_at < threshold_date, linkdata.c.is_active == True
                )
            )
            unused_links = result.fetchall()
            if unused_links:
                # Deactivate unused links
                stmt = (
                    update(linkdata)
                    .where(linkdata.c.last_used_at < threshold_date, linkdata.c.is_active == True)
                    .values(is_active=False)
                )
                await session.execute(stmt)

            # Find unused links
            result = await session.execute(
                select(linkdata).where(
                    linkdata.c.expires_at < datetime.utcnow(), linkdata.c.is_active == True
                )
            )

            unused_links = result.fetchall()
            if unused_links:
                # Deactivate unused links
                stmt = (
                    update(linkdata)
                    .where(linkdata.c.expires_at < datetime.utcnow(), linkdata.c.is_active == True)
                    .values(is_active=False)
                )
                await session.execute(stmt)

            # Find unused links
            result = await session.execute(
                select(linkdata).where(
                    linkdata.c.created < datetime.utcnow(), linkdata.c.is_active == True,
                    linkdata.c.last_used_at == None, linkdata.c.expires_at == None
                )
            )

            unused_links = result.fetchall()
            if unused_links:
                # Deactivate unused links
                stmt = (
                    update(linkdata)
                    .where(linkdata.c.created < threshold_date, linkdata.c.is_active == True,
                    linkdata.c.last_used_at == None, linkdata.c.expires_at == None)
                    .values(is_active=False)
                )
                await session.execute(stmt)

            await session.commit()

            # Wait for 24 hours before running again
            await asyncio.sleep(24 * 60 * 60)  # 24 hours in seconds