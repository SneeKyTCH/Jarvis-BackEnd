"""
Voice endpoints
Speech recognition, text-to-speech, voice processing
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from uuid import uuid4
import logging
import tempfile
from pathlib import Path

from app.db import get_db
from app.services import VoiceService, AuthService

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request/Response Models ───
class SpeechRecognitionResponse(BaseModel):
    """Speech recognition result"""
    text: str
    confidence: float
    language: str
    duration_seconds: float

    class Config:
        example = {
            "text": "Hello, can you help me?",
            "confidence": 0.95,
            "language": "en",
            "duration_seconds": 3.5,
        }


class TextToSpeechRequest(BaseModel):
    """Text-to-speech request"""
    text: str
    language: str = "en"
    voice_id: Optional[str] = None  # Eleven Labs voice ID

    class Config:
        example = {
            "text": "Hello! How can I help you today?",
            "language": "en",
            "voice_id": "George",
        }


class TextToSpeechResponse(BaseModel):
    """Text-to-speech result"""
    audio_file_id: str
    duration_seconds: float
    format: str  # "mp3", "wav", etc.
    cached: bool  # Whether response was from cache

    class Config:
        example = {
            "audio_file_id": "audio_123",
            "duration_seconds": 2.5,
            "format": "mp3",
            "cached": False,
        }


class VoiceInfo(BaseModel):
    """Voice metadata"""
    voice_id: str
    name: str
    language: str
    preview_url: Optional[str] = None


# ─── Endpoints ───

@router.post("/recognize", response_model=SpeechRecognitionResponse)
async def recognize_speech(
    audio_file: UploadFile = File(...),
    language: Optional[str] = None,
    authorization: Optional[str] = None,
):
    """
    Convert speech (audio) to text

    Args:
        audio_file: Audio file (WAV, MP3, OGG, FLAC)
        language: Language code (e.g., 'en', 'ro'). Auto-detect if not provided.
        authorization: Bearer token

    Returns: Transcribed text with confidence and language
    """
    logger.info(f"Speech recognition request: {audio_file.filename}")

    # Extract and validate token (optional for this endpoint, but recommended)
    user_id = None
    if authorization:
        token = None
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            token = authorization

        if token:
            user_id, _ = AuthService.validate_token(token)

    # Validate file size (max 25MB)
    contents = await audio_file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")

    # Save to temporary file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Recognize speech
        text, confidence = VoiceService.recognize_speech(
            audio_file_path=tmp_path,
            language=language or "en",
            user_id=user_id,
        )

        if not text:
            raise HTTPException(status_code=400, detail="Speech not recognized")

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        return {
            "text": text,
            "confidence": confidence,
            "language": language or "en",
            "duration_seconds": len(contents) / 32000,  # Rough estimate
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Speech recognition error: {str(e)}")
        raise HTTPException(status_code=500, detail="Speech recognition failed")


@router.post("/synthesize", response_model=TextToSpeechResponse)
async def synthesize_speech(
    request: TextToSpeechRequest,
    authorization: Optional[str] = None,
):
    """
    Convert text to speech (audio)

    Args:
        request: TextToSpeechRequest with text, language, and optional voice_id
        authorization: Bearer token

    Returns: Audio file metadata with file ID for download
    """
    logger.info(f"Text-to-speech request: {request.text[:50]}...")

    # Extract and validate token
    user_id = None
    if authorization:
        token = None
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            token = authorization

        if token:
            user_id, _ = AuthService.validate_token(token)

    # Synthesize speech
    audio_path, duration = VoiceService.synthesize_speech(
        text=request.text,
        language=request.language,
        voice_id=request.voice_id or "George",
        user_id=user_id,
    )

    if not audio_path:
        raise HTTPException(status_code=500, detail="Text-to-speech failed")

    # Generate file ID
    audio_file_id = f"audio_{uuid4().hex[:8]}"

    return {
        "audio_file_id": audio_file_id,
        "duration_seconds": duration,
        "format": "mp3",
        "cached": False,
    }


@router.get("/synthesize/{audio_file_id}")
async def download_audio(audio_file_id: str):
    """
    Download synthesized audio file

    Args:
        audio_file_id: ID of audio file from synthesize endpoint

    Returns: Audio file (MP3)
    """
    logger.info(f"Download audio: {audio_file_id}")

    # TODO: Implement S3 download or local file serving
    # For now, return error
    raise HTTPException(status_code=404, detail="Audio file not found")


@router.post("/transcribe")
async def transcribe_with_language_detection(
    audio_file: UploadFile = File(...),
    authorization: Optional[str] = None,
):
    """
    Convert speech to text WITH automatic language detection

    Like recognize_speech but also detects language from audio.

    Args:
        audio_file: Audio file (WAV, MP3, OGG, FLAC)
        authorization: Bearer token

    Returns: Transcribed text with detected language and confidence
    """
    logger.info(f"Transcribe with language detection: {audio_file.filename}")

    # Extract and validate token (optional)
    user_id = None
    if authorization:
        token = None
        parts = authorization.split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            token = authorization

        if token:
            user_id, _ = AuthService.validate_token(token)

    # Validate file size
    contents = await audio_file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25MB)")

    # Save to temporary file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Try to recognize in multiple languages to detect which one works
        # For now, we'll just try English and Romanian
        languages_to_try = ["en", "ro", "es", "fr"]
        best_result = None
        best_confidence = 0

        for lang in languages_to_try:
            text, confidence = VoiceService.recognize_speech(
                audio_file_path=tmp_path,
                language=lang,
                user_id=user_id,
            )

            if text and confidence > best_confidence:
                best_result = (text, lang, confidence)
                best_confidence = confidence

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        if not best_result:
            raise HTTPException(status_code=400, detail="Speech not recognized")

        text, detected_lang, confidence = best_result

        return {
            "text": text,
            "language": detected_lang,
            "confidence": confidence,
            "duration_seconds": len(contents) / 32000,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail="Transcription failed")


@router.get("/voices", response_model=list[VoiceInfo])
async def list_available_voices(authorization: Optional[str] = None):
    """
    List available voice options for TTS

    Args:
        authorization: Bearer token (optional)

    Returns: List of voice IDs and metadata from Eleven Labs
    """
    logger.info("List available voices")

    # Get voices from Eleven Labs
    voices = VoiceService.get_available_voices()

    if not voices:
        # Return default voices if API unavailable
        return [
            {
                "voice_id": "George",
                "name": "George",
                "language": "en",
                "preview_url": None,
            },
            {
                "voice_id": "Alice",
                "name": "Alice",
                "language": "en",
                "preview_url": None,
            },
        ]

    return voices
