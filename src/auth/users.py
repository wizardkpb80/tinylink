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
from src.config import SECRET

ALGORITHM = "HS256"


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        update_dict = {"registered_at": datetime.utcnow()}
        await self.user_db.update(user,update_dict)  # Обновляем пользователя в базе данных
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")


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
current_user = fastapi_users.current_user()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/jwt/login")

def decode_token(token: str = Depends(oauth2_scheme)):
    """Decodes JWT token and extracts user details."""
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        return {
            "email": payload.get("sub"),  # User's email
            "is_superuser": payload.get("is_superuser", False),  # Superuser flag
            "exp": payload.get("exp")  # Expiration timestamp
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET)
        user_email = payload.get("sub")
        if not user_email:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"email": user_email}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    user = verify_token(token)  # Функция для проверки токена
    print(user)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

def check_user(user: User = Depends(current_active_user)):
    return user

def get_current_user_optional() -> User:
    print("123")
    try:
        user = Depends(current_active_user)
        return user  # Попытка получить пользователя
    except HTTPException:
        return User(email="anonym")  # Возвращаем "анонимного" пользователя

def get_current_superuser(token: str = Depends(oauth2_scheme)) -> User:
    """Проверяет токен и возвращает суперпользователя, если он есть."""
    print(token)
    if not token:
        return User(email="anonym")  # Если токена нет, аноним

    try:
        print("123")
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        print(payload)
        user_email = payload.get("sub")
        print(user_email)
        is_superuser = payload.get("is_superuser", False)  # Проверяем флаг суперпользователя

        if not user_email:
            return User(email="anonym")  # Если email отсутствует, аноним
        if not is_superuser:
            return User(email="anonym")  # Не суперпользователь → аноним

        return User(email=user_email)
    except jwt.ExpiredSignatureError:
        return User(email="anonym")  # Токен истёк → аноним
    except jwt.InvalidTokenError:
        return User(email="anonym")  # Некорректный токен → аноним
    except Exception:
        return User(email="anonym")  # Любая другая ошибка → аноним