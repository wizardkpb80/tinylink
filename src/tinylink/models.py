from sqlalchemy import Table, Column, Integer, DateTime, MetaData, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid


metadata = MetaData()

linkdata = Table(
    "linkdata",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("user_id", UUID, nullable=True),
    Column("original_url", String),
    Column("short_code", String),
    Column("created", DateTime, default=func.now(), nullable=False),
    Column("expires_at", DateTime, default=func.now(), nullable=False),
    Column("usage_count", Integer, default=0, nullable=False),
    Column("last_used_at", DateTime, nullable=True),
    Column("is_active", Boolean, default=True)
)
