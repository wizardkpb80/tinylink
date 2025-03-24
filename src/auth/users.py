import uuid
from datetime import datetime
from typing import Optional
import jwt
from fastapi import Depends, Request
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordBearer
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from src.auth.db import User, get_user_db
from src.config import SECRET, ALGORITHM


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

async def on_after_register(self, user: User):
    update_dict = {"registered_at": datetime.utcnow()}
    # Обновляем пользователя в базе данных
    await self.user_db.update(user,update_dict)
    print(f"User {user.id} has registered.")

async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(optional=True)
