"""
Voice Service
Speech recognition, text-to-speech, voice caching
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
import logging
import hashlib
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

from app.models import VoiceCache, User
from app.config import settings
from app.db import DatabaseSession


class VoiceService:
    """Speech recognition and text-to-speech management"""

    @staticmethod
    def recognize_speech(
        audio_file_path: str,
        language: str = "ro",
        user_id: Optional[str] = None,
        db: Session = None,
    ) -> Tuple[Optional[str], float]:
        """
        Convert speech audio to text

        Args:
            audio_file_path: Path to audio file
            language: Language code (e.g., 'ro', 'en')
            user_id: User ID for logging
            db: Database session

        Returns:
            (transcribed_text, confidence_score)
        """
        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()

            # Load audio file
            with sr.AudioFile(audio_file_path) as source:
                audio = recognizer.record(source)

            # Transcribe with specified language
            try:
                text = recognizer.recognize_google(audio, language=language)
                confidence = 0.95  # Google doesn't return confidence, estimate high

                logger.info(f"Speech recognized: {text[:50]}... (language: {language})")
                return text, confidence

            except sr.UnknownValueError:
                logger.warning("Speech not recognized")
                return None, 0.0

            except sr.RequestError as e:
                logger.error(f"Speech recognition API error: {str(e)}")
                return None, 0.0

        except Exception as e:
            logger.error(f"Speech recognition error: {str(e)}")
            return None, 0.0

    @staticmethod
    def synthesize_speech(
        text: str,
        language: str = "en",
        voice_id: str = "George",
        user_id: Optional[str] = None,
        db: Session = None,
    ) -> Tuple[Optional[str], float]:
        """
        Convert text to speech audio

        Args:
            text: Text to synthesize
            language: Language code (e.g., 'ro', 'en')
            voice_id: Eleven Labs voice ID
            user_id: User ID for caching
            db: Database session

        Returns:
            (audio_file_path, duration_seconds) or (None, 0) on error
        """
        # Check cache first
        if user_id:
            cached = VoiceService.get_cached_audio(
                text=text,
                language=language,
                voice_id=voice_id,
                user_id=user_id,
                db=db,
            )
            if cached:
                logger.info(f"Returning cached audio for: {text[:30]}...")
                return cached["audio_file_path"], cached["duration_seconds"] or 0.0

        try:
            import requests
            from io import BytesIO

            api_key = settings.elevenlabs_api_key
            if not api_key:
                logger.error("Eleven Labs API key not configured")
                return None, 0.0

            # Call Eleven Labs API
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            }
            data = {
                "text": text,
                "model_id": "eleven_turbo_v2_5",
            }

            response = requests.post(url, json=data, headers=headers, timeout=30)

            if response.status_code != 200:
                logger.error(f"Eleven Labs API error: {response.status_code}")
                return None, 0.0

            # Save audio to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp.write(response.content)
                audio_file_path = tmp.name

            # Calculate duration (rough estimate)
            duration_seconds = len(text) / 150.0  # ~150 chars per second

            # Cache the result
            if user_id and db:
                VoiceService.cache_audio(
                    text=text,
                    language=language,
                    voice_id=voice_id,
                    user_id=user_id,
                    audio_file_path=audio_file_path,
                    duration_seconds=duration_seconds,
                    db=db,
                )

            logger.info(f"Speech synthesized: {text[:30]}... ({duration_seconds:.1f}s)")
            return audio_file_path, duration_seconds

        except Exception as e:
            logger.error(f"Text-to-speech error: {str(e)}")
            return None, 0.0

    @staticmethod
    def get_cached_audio(
        text: str,
        language: str,
        voice_id: str,
        user_id: str,
        db: Session = None,
    ) -> Optional[dict]:
        """
        Get cached audio for text

        Returns:
            {"audio_file_path": str, "duration_seconds": float} or None
        """
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            # Hash the text for lookup
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            cache = db.query(VoiceCache).filter(
                VoiceCache.user_id == user_id,
                VoiceCache.text_hash == text_hash,
                VoiceCache.language == language,
                VoiceCache.voice_id == voice_id,
                VoiceCache.expires_at > datetime.utcnow(),
            ).first()

            if cache:
                # Increment hit count
                cache.hit_count += 1
                db.commit()

                return {
                    "audio_file_path": cache.audio_file_path,
                    "duration_seconds": cache.duration_seconds,
                }

            return None

        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def cache_audio(
        text: str,
        language: str,
        voice_id: str,
        user_id: str,
        audio_file_path: str,
        duration_seconds: float,
        db: Session = None,
    ) -> VoiceCache:
        """Cache audio synthesis result"""
        if db is None:
            db_session = DatabaseSession()
            db = db_session.__enter__()
        else:
            db_session = None

        try:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            expires_at = datetime.utcnow() + timedelta(days=settings.voice_cache_ttl_days)

            cache = VoiceCache(
                user_id=user_id,
                text_hash=text_hash,
                text=text,
                language=language,
                voice_id=voice_id,
                audio_file_path=audio_file_path,
                duration_seconds=duration_seconds,
                expires_at=expires_at,
            )

            db.add(cache)
            db.commit()
            db.refresh(cache)

            logger.info(f"Audio cached: {text[:30]}...")
            return cache

        finally:
            if db_session:
                db_session.__exit__(None, None, None)

    @staticmethod
    def get_available_voices() -> list:
        """Get available voices from Eleven Labs"""
        try:
            import requests

            api_key = settings.elevenlabs_api_key
            if not api_key:
                logger.warning("Eleven Labs API key not configured")
                return []

            url = "https://api.elevenlabs.io/v1/voices"
            headers = {"xi-api-key": api_key}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Eleven Labs API error: {response.status_code}")
                return []

            voices_data = response.json().get("voices", [])
            voices = [
                {
                    "voice_id": v["voice_id"],
                    "name": v["name"],
                    "language": "en",  # Simplified for now
                    "preview_url": v.get("preview_url"),
                }
                for v in voices_data
            ]

            logger.info(f"Retrieved {len(voices)} voices from Eleven Labs")
            return voices

        except Exception as e:
            logger.error(f"Error fetching voices: {str(e)}")
            return []
