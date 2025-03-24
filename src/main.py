from fastapi import FastAPI, Depends, HTTPException
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from src.auth.users import auth_backend, current_active_user, fastapi_users
from src.auth.schemas import UserCreate, UserRead #, UserUpdate
from src.auth.db import User, create_db_and_tables
from src.tinylink.router import router as tinylink_router
from src.tasks.tasks import router as tasks_router
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from typing import Optional

import uvicorn


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    redis = aioredis.from_url("redis://redis_app")

    # Очистка кэша Redis при запуске приложения
    await redis.flushdb()
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    # await create_db_and_tables()
    yield

VERSION='1.0.1'
app = FastAPI(lifespan=lifespan, title="TinyLink API", version=VERSION)

app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(tinylink_router)
app.include_router(tasks_router)


@app.get("/protected-route")
def protected_route(user: User = Depends(current_active_user)):
    return f"Hello, {user.email}"


@app.get("/unprotected-route")
def unprotected_route():
    return f"Hello, anonym"

@app.get("/check-route")
def protected_route(user: Optional[User] = Depends(current_active_user)):
    print(f"User object: {user}")  # Debugging output
    if not user:
        return "Hello, anonymous"  # Fallback for unauthorized users
    return f"Hello, {user.email}"

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True, host="localhost", log_level="info")
