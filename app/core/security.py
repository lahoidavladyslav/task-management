from datetime import timedelta

import jwt
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.exceptions import AuthenticationError

_password_hash = PasswordHash.recommended()
# Verified against when the e-mail is unknown, so that response time
# does not reveal whether an account exists.
_DUMMY_HASH = _password_hash.hash("timing-attack-mitigation")


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_password_hash.hash, password)


async def verify_password(password: str, hashed_password: str | None) -> bool:
    return await run_in_threadpool(_password_hash.verify, password, hashed_password or _DUMMY_HASH)


def create_access_token(user_id: int, settings: Settings) -> tuple[str, int]:
    now = utcnow()
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": now + lifetime}
    token = jwt.encode(
        payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired token", code="invalid_token") from exc
