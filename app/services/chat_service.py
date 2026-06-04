"""
Chat Service
Conversation management, message handling, AI integration
"""

from datetime import datetime
from typing import Optional, List, AsyncGenerator
from sqlalchemy.orm import Session
import logging
import time
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from app.models import Conversation, Message, User
from app.db import DatabaseSession


# ─── Import JARVIS Core (from existing project) ───

def import_jarvis_modules():
    """Dynamically import JARVIS core modules from existing project"""
    try:
        # Add JARVIS project to path
        jarvis_path = Path("C:/Users/SneeKy/Desktop/Digital Marketing Assistant")
        if jarvis_path.exists():
            sys.path.insert(0, str(jarvis_path))

            import jarvis_core
            import jarvis_language
            import jarvis_research

            logger.info("JARVIS core modules imported successfully")
            return {
                "jarvis_core": jarvis_core,
                "jarvis_language": jarvis_language,
                "jarvis_research": jarvis_research,
            }
        else:
            logger.warning("JARVIS project path not found")
            return None
    except Exception as e:
        logger.warning(f"Could not import JARVIS modules: {str(e)}")
        return None


# Try to import JARVIS modules
JARVIS_MODULES = import_jarvis_modules()


class ChatService:
    """Chat conversation and message management"""

    @staticmethod
    def create_conversation(user_id: str, language: str = "en", db: Session = None) -> Conversation:
        """
        Create new conversation

        Args:
            user_id: User ID
            language: Initial language (e.g., 'en', 'ro')
            db: Database session

        Returns:
            Conversation object
        """
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            conversation = Conversation(
                user_id=user_id,
                language=language,
                title=None,  # Will be auto-generated from first message
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
    def list_user_conversations(user_id: str, limit: int = 20, offset: int = 0, db: Session = None) -> List[Conversation]:
        """List user's conversations"""
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            conversations = db.query(Conversation).filter(
                Conversation.user_id == user_id,
            ).order_by(
                Conversation.updated_at.desc(),
            ).limit(limit).offset(offset).all()

            return conversations

        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def delete_conversation(conversation_id: str, user_id: str, db: Session = None) -> bool:
        """Delete conversation (cascade deletes messages)"""
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            ).first()

            if not conversation:
                return False

            db.delete(conversation)
            db.commit()
            logger.info(f"Conversation deleted: {conversation_id[:8]}")
            return True

        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def add_message(
        conversation_id: str,
        role: str,
        content: str,
        tokens_used: Optional[int] = None,
        response_time_ms: Optional[float] = None,
        db: Session = None,
    ) -> Message:
        """
        Add message to conversation

        Args:
            conversation_id: Conversation ID
            role: "user" or "assistant"
            content: Message text
            tokens_used: Number of tokens used
            response_time_ms: Response time in milliseconds
            db: Database session

        Returns:
            Message object
        """
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms,
            )

            db.add(message)

            # Update conversation
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
            ).first()

            if conversation:
                conversation.message_count += 1
                conversation.updated_at = datetime.utcnow()

                # Auto-generate title from first message
                if conversation.message_count == 1 and role == "user":
                    title = content[:50] if len(content) > 50 else content
                    conversation.title = title

            db.commit()
            db.refresh(message)

            return message

        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def get_conversation_history(conversation_id: str, limit: int = 100, db: Session = None) -> List[Message]:
        """Get message history for conversation"""
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            messages = db.query(Message).filter(
                Message.conversation_id == conversation_id,
            ).order_by(
                Message.created_at.asc(),
            ).limit(limit).all()

            return messages

        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    async def get_ai_response(
        message: str,
        conversation_id: str,
        user_id: str,
        language: Optional[str] = None,
        db: Session = None,
    ) -> str:
        """
        Get AI response to user message using JARVIS core

        Integrates with JARVIS core modules for:
        - Multi-model AI (Claude 3.5 Sonnet primary, GPT-4o fallback)
        - Language detection (7 languages)
        - Web research context
        - Personalization

        Args:
            message: User message
            conversation_id: Conversation ID
            user_id: User ID
            language: Force specific language
            db: Database session

        Returns:
            AI response text
        """
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            import sys
            from pathlib import Path
            start_time = time.time()

            # Get conversation
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            ).first()

            if not conversation:
                return "Conversation not found"

            # Get message history for context
            message_history = db.query(Message).filter(
                Message.conversation_id == conversation_id,
            ).order_by(Message.created_at.asc()).limit(20).all()

            # Build conversation context
            context_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in message_history
            ]

            # Detect language from message
            detected_lang = language or conversation.language
            try:
                from jarvis_language import detect_language_from_text, get_system_prompt_for_language
                detected_lang, confidence = detect_language_from_text(message)
                if confidence < 0.7:
                    detected_lang = conversation.language
                logger.info(f"Detected language: {detected_lang} (confidence: {confidence:.2f})")
            except Exception as e:
                logger.warning(f"Language detection failed: {e}, using {detected_lang}")
                detected_lang = conversation.language

            # Get system prompt for language
            system_prompt = None
            try:
                from jarvis_language import get_system_prompt_for_language
                system_prompt = get_system_prompt_for_language(detected_lang)
            except Exception as e:
                logger.warning(f"Could not load language-specific prompt: {e}")
                system_prompt = f"You are JARVIS, a universal AI assistant. Respond in {detected_lang}."

            # Get AI response
            try:
                from jarvis_core import get_ai_client
                ai_client, ai_model_type = get_ai_client()
                logger.info(f"Using AI model: {ai_model_type}")

                if ai_model_type == "claude":
                    # Use Anthropic Claude API
                    response = ai_client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=2048,
                        system=system_prompt,
                        messages=context_messages + [{"role": "user", "content": message}],
                        temperature=0.7,
                    )
                    ai_response = response.content[0].text
                    tokens_used = response.usage.input_tokens + response.usage.output_tokens if hasattr(response, 'usage') else None
                else:
                    # Use OpenAI API
                    response = ai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": system_prompt}
                        ] + context_messages + [{"role": "user", "content": message}],
                        temperature=0.7,
                        max_tokens=2048,
                    )
                    ai_response = response.choices[0].message.content
                    tokens_used = response.usage.total_tokens if hasattr(response, 'usage') else None

                logger.info(f"AI response generated ({tokens_used} tokens)")

            except Exception as e:
                logger.error(f"AI API error: {str(e)}")
                ai_response = f"[Error contacting AI service: {str(e)[:100]}]"
                tokens_used = None

            response_time_ms = (time.time() - start_time) * 1000

            # Update conversation language if detected
            if detected_lang != conversation.language:
                conversation.language = detected_lang
                db.commit()

            # Save message to database
            ChatService.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms,
                db=db,
            )

            return ai_response

        except Exception as e:
            logger.error(f"Chat service error: {str(e)}", exc_info=True)
            return f"[Error: {str(e)[:100]}]"

        finally:
            if db_session:
                db_session.__exit__(None, None, None)
