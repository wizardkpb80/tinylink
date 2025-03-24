from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

class LinkCreate(BaseModel):
    original_url: str
    custom_alias: Optional[str] = None  # Добавляем поддержку кастомного alias
    expires_at: Optional[str] = None  # Опционально: можно указать срок жизни ссылки

class LinkResponse(BaseModel):
    short_code: str
    original_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    user_id: Optional[uuid.UUID] = None

class LinkUpdate(BaseModel):
    original_url: Optional[str] = None  # Оригинальный URL, который можно обновить
    expires_at: Optional[datetime] = None  # Время жизни ссылки
