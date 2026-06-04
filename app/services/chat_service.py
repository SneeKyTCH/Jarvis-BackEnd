"""
Chat Service - AI-powered conversations
Uses Claude API and OpenAI API
"""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
import json

from app.models import Conversation, Message, User
from app.db import DatabaseSession
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize AI clients
try:
    from anthropic import Anthropic
    claude_client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
except Exception as e:
    logger.warning(f"Claude API not available: {str(e)}")
    claude_client = None

try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
except Exception as e:
    logger.warning(f"OpenAI API not available: {str(e)}")
    openai_client = None


class ChatService:
    """Chat conversation and message management with AI integration"""

    @staticmethod
    def create_conversation(user_id: str, language: str = "en", db: Session = None) -> Conversation:
        """Create new conversation"""
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            conversation = Conversation(
                user_id=user_id,
                language=language,
                title=None,
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            logger.info(f"Conversation created: {conversation.id[:8]}")
            return conversation
        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def get_conversation(conversation_id: str, user_id: str, db: Session) -> Optional[Conversation]:
        """Get conversation by ID (verify user owns it)"""
        return db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()

    @staticmethod
    def send_message(
        user_id: str,
        conversation_id: str,
        message_text: str,
        use_claude: bool = True,
        db: Session = None,
    ) -> dict:
        """
        Send message to AI and get response

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            message_text: User message
            use_claude: Use Claude (True) or OpenAI (False)
            db: Database session

        Returns:
            {
                "id": message_id,
                "role": "assistant",
                "content": ai_response,
                "timestamp": timestamp
            }
        """
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            # Get conversation
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            ).first()

            if not conversation:
                return {"error": "Conversation not found"}

            # Get conversation history
            messages = db.query(Message).filter(
                Message.conversation_id == conversation_id
            ).order_by(Message.created_at).all()

            # Format for AI
            history = [{"role": msg.role, "content": msg.content} for msg in messages]
            history.append({"role": "user", "content": message_text})

            # Get AI response
            if use_claude and claude_client:
                ai_response = ChatService._claude_response(history)
            elif openai_client:
                ai_response = ChatService._openai_response(history)
            else:
                return {"error": "No AI service configured"}

            # Save user message
            user_msg = Message(
                conversation_id=conversation_id,
                role="user",
                content=message_text,
            )
            db.add(user_msg)

            # Save AI response
            ai_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response,
            )
            db.add(ai_msg)

            # Update conversation title if first message
            if not conversation.title:
                conversation.title = message_text[:50] + "..."

            db.commit()
            db.refresh(ai_msg)

            return {
                "id": ai_msg.id,
                "role": "assistant",
                "content": ai_response,
                "timestamp": ai_msg.created_at.isoformat(),
            }

        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return {"error": str(e)}
        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def _claude_response(messages: list) -> str:
        """Get response from Claude API"""
        try:
            response = claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=messages,
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude API error: {str(e)}")
            return f"Error: {str(e)}"

    @staticmethod
    def _openai_response(messages: list) -> str:
        """Get response from OpenAI API"""
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1024,
                messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return f"Error: {str(e)}"

    @staticmethod
    def get_messages(conversation_id: str, user_id: str, db: Session) -> list:
        """Get all messages in conversation"""
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()

        if not conversation:
            return []

        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()

        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
            }
            for msg in messages
        ]
