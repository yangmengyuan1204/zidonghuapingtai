from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import secrets
from typing import Optional
import warnings

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


BASE_DIR = Path(__file__).resolve().parent.parent


def load_secret_key() -> str:
    configured = os.getenv("SECRET_KEY")
    if configured:
        return configured
    secret_file = BASE_DIR / ".secret_key"
    try:
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        secret_file.write_text(value + "\n", encoding="utf-8")
        warnings.warn(
            "SECRET_KEY is not set. Generated local .secret_key; set SECRET_KEY in production.",
            RuntimeWarning,
            stacklevel=2,
        )
        return value
    except OSError:
        warnings.warn(
            "SECRET_KEY is not set and local .secret_key could not be written; using a process-local secret.",
            RuntimeWarning,
            stacklevel=2,
        )
        return secrets.token_urlsafe(48)


SECRET_KEY = load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    stored = str(hashed_password or "")
    try:
        return pwd_context.verify(password, stored)
    except Exception:
        pass
    if not stored:
        return False
    if stored == password:
        return True
    normalized = stored.lower()
    raw = str(password or "").encode("utf-8")
    legacy_hashes = {
        hashlib.md5(raw).hexdigest(),
        hashlib.sha1(raw).hexdigest(),
        hashlib.sha256(raw).hexdigest(),
    }
    return normalized in legacy_hashes


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise credentials_error
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 admin 账号可操作")
    return current_user
