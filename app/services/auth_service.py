"""
Authentication Service
User registration, login, JWT token management
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import logging

from app.config import settings
from app.models import User, APIToken
from app.db import DatabaseSession

logger = logging.getLogger(__name__)

# ─── Password Hashing ───

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


# ─── JWT Token Management ───

def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return encoded_jwt


def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT refresh token"""
    if expires_delta is None:
        expires_delta = timedelta(days=settings.refresh_token_expire_days)

    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> Optional[str]:
    """
    Verify JWT token and return user_id

    Args:
        token: JWT token string
        token_type: "access" or "refresh"

    Returns:
        user_id if valid, None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )

        user_id: str = payload.get("sub")
        token_type_claim: str = payload.get("type")

        if user_id is None or token_type_claim != token_type:
            return None

        return user_id

    except JWTError as e:
        logger.debug(f"Invalid token: {str(e)}")
        return None


# ─── User Authentication Service ───

class AuthService:
    """Authentication and user management"""

    @staticmethod
    def register_user(email: str, username: str, password: str, db: Session) -> Tuple[Optional[User], str]:
        """
        Register a new user

        Returns:
            (User, message) - User object if successful, error message otherwise
        """
        # Check if email already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            return None, f"Email {email} already registered"

        # Check if username already exists
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            return None, f"Username {username} already taken"

        # Create new user
        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info(f"User registered: {email}")
        return user, "Registration successful"

    @staticmethod
    def login_user(email: str, password: str, db: Session) -> Tuple[Optional[User], str]:
        """
        Login user and verify credentials

        Returns:
            (User, message) - User object if successful, error message otherwise
        """
        user = db.query(User).filter(User.email == email).first()

        if not user:
            return None, f"User {email} not found"

        if not user.is_active:
            return None, "User account is inactive"

        if not verify_password(password, user.password_hash):
            logger.warning(f"Failed login attempt for {email}")
            return None, "Invalid password"

        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)

        logger.info(f"User logged in: {email}")
        return user, "Login successful"

    @staticmethod
    def get_user_by_id(user_id: str, db: Session) -> Optional[User]:
        """Get user by ID"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create_tokens(user_id: str, db: Session = None) -> dict:
        """
        Create access and refresh tokens for user

        Returns:
            {
                "access_token": str,
                "refresh_token": str,
                "token_type": "bearer",
                "expires_in": seconds
            }
        """
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Tuple[Optional[str], str]:
        """
        Generate new access token from refresh token

        Returns:
            (new_access_token, message)
        """
        user_id = verify_token(refresh_token, token_type="refresh")

        if not user_id:
            return None, "Invalid or expired refresh token"

        new_access_token = create_access_token(user_id)
        return new_access_token, "Token refreshed successfully"

    @staticmethod
    def validate_token(token: str) -> Tuple[Optional[str], str]:
        """
        Validate access token and return user_id

        Returns:
            (user_id, message)
        """
        user_id = verify_token(token, token_type="access")

        if not user_id:
            return None, "Invalid or expired token"

        return user_id, "Token valid"
