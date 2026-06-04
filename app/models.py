"""
SQLAlchemy Database Models for JARVIS Backend
User, Conversation, Message, VoiceCache
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


class User(Base):
    """User account model"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    voice_cache = relationship("VoiceCache", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"


class Conversation(Base):
    """Chat conversation model"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    language = Column(String(10), default="en", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    message_count = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_created", "user_id", "created_at"),
    )

    def __repr__(self):
        return f"<Conversation {self.id[:8]}>"


class Message(Base):
    """Chat message model"""
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(10), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    tokens_used = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("idx_conversation_created", "conversation_id", "created_at"),
    )

    def __repr__(self):
        return f"<Message {self.id[:8]} ({self.role})>"


class VoiceCache(Base):
    """Cached voice synthesis results"""
    __tablename__ = "voice_cache"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    text_hash = Column(String(64), nullable=False, index=True)  # SHA256 of input text
    text = Column(Text, nullable=False)
    language = Column(String(10), default="en", nullable=False)
    voice_id = Column(String(50), default="George", nullable=False)
    audio_file_path = Column(String(255), nullable=False)  # S3 path or local path
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # 45-day TTL
    hit_count = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="voice_cache")

    __table_args__ = (
        Index("idx_user_hash", "user_id", "text_hash"),
    )

    def __repr__(self):
        return f"<VoiceCache {self.id[:8]}>"


class APIToken(Base):
    """Refresh token storage for JWT"""
    __tablename__ = "api_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<APIToken {self.id[:8]}>"
