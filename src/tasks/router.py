from celery import Celery
from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from src.database import engine
from src.tinylink.models import linkdata

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

celery = Celery('tasks', broker='redis://redis_app:6379')

# Указываем N дней, после которых неиспользуемые ссылки будут удаляться
EXPIRATION_DAYS = 30

# Создаём асинхронную сессию SQLAlchemy
async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

router = APIRouter(prefix="/task")

@celery.task
async def delete_unused_links():
    """Удаляет ссылки, если с последнего использования прошло более N дней."""
    async with async_session() as session:
        threshold_date = datetime.now() - timedelta(days=EXPIRATION_DAYS)

        # Получаем ссылки, у которых last_used_at < threshold_date
        result = await session.execute(
            select(linkdata).where(
                linkdata.c.last_used_at < threshold_date
            )
        )
        old_links = result.fetchall()

        for link in old_links:
            await session.execute(
                linkdata.delete().where(linkdata.c.id == link.id)
            )

        await session.commit()
        print(f"Deleted {len(old_links)} unused links.")
