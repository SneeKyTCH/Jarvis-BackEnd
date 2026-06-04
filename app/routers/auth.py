"""
Authentication endpoints
JWT-based auth with access and refresh tokens
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.orm import Session
import logging

from app.config import settings
from app.db import get_db
from app.models import User
from app.services import AuthService

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request/Response Models ───
class UserRegister(BaseModel):
    """User registration request"""
    email: EmailStr
    username: str
    password: str

    class Config:
        example = {
            "email": "user@example.com",
            "username": "jarvis_user",
            "password": "secure_password_123",
        }


class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr
    password: str

    class Config:
        example = {
            "email": "user@example.com",
            "password": "secure_password_123",
        }


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """User information"""
    id: str
    email: str
    username: str
    created_at: str

    class Config:
        example = {
            "id": "user_123",
            "email": "user@example.com",
            "username": "jarvis_user",
            "created_at": "2026-06-04T10:30:00Z",
        }


class AuthResponse(BaseModel):
    """Authentication response with token and user info"""
    token: Token
    user: UserResponse


# ─── Endpoints ───

@router.post("/register", response_model=AuthResponse)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user

    Returns: JWT tokens and user information
    """
    logger.info(f"User registration attempt: {user_data.email}")

    # Register user using service
    user, message = AuthService.register_user(
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        db=db,
    )

    if not user:
        raise HTTPException(status_code=400, detail=message)

    # Create tokens
    tokens = AuthService.create_tokens(user.id)

    return {
        "token": tokens,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "created_at": user.created_at.isoformat(),
        },
    }


@router.post("/login", response_model=AuthResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """
    Login with email and password

    Returns: JWT tokens and user information
    """
    logger.info(f"User login attempt: {user_data.email}")

    # Login user using service
    user, message = AuthService.login_user(
        email=user_data.email,
        password=user_data.password,
        db=db,
    )

    if not user:
        raise HTTPException(status_code=401, detail=message)

    # Create tokens
    tokens = AuthService.create_tokens(user.id)

    return {
        "token": tokens,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "created_at": user.created_at.isoformat(),
        },
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_token: str):
    """
    Refresh JWT access token using refresh token

    Args:
        refresh_token: Valid refresh token from login/register

    Returns: New access token
    """
    logger.info("Token refresh attempt")

    new_access_token, message = AuthService.refresh_access_token(refresh_token)

    if not new_access_token:
        raise HTTPException(status_code=401, detail=message)

    return {
        "access_token": new_access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post("/logout")
async def logout(access_token: str):
    """
    Logout user by invalidating token

    Args:
        access_token: Valid access token to invalidate

    Returns: Confirmation message
    """
    logger.info("User logout")

    # TODO: Add token blacklist in Redis
    # For now, tokens are validated on each request

    return {
        "status": "success",
        "message": "Logged out successfully",
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """
    Get current user information

    Args:
        authorization: Bearer token in Authorization header

    Returns: Current user information
    """
    logger.info("Get current user")

    # Extract token from authorization header
    token = None
    if authorization:
        if " " in authorization:
            # Format: "Bearer <token>"
            parts = authorization.split(" ", 1)
            if parts[0].lower() == "bearer" and len(parts) > 1:
                token = parts[1]
        else:
            # Direct token
            token = authorization

    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    # Validate token
    user_id, message = AuthService.validate_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail=message)

    # Get user
    user = AuthService.get_user_by_id(user_id, db)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
    }
