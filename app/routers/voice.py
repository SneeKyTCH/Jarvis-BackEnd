"""
Voice endpoints
Speech recognition, text-to-speech, voice processing
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Header
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

@router.post("/debug-upload")
async def debug_upload(
    audio_file: UploadFile = File(...),
):
    """
    DEBUG: Test if file upload works
    """
    contents = await audio_file.read()
    logger.info(f"DEBUG: Received file: {audio_file.filename}")
    logger.info(f"DEBUG: File size: {len(contents)} bytes")
    logger.info(f"DEBUG: Content-Type: {audio_file.content_type}")

    return {
        "received": True,
        "filename": audio_file.filename,
        "size": len(contents),
        "content_type": audio_file.content_type,
    }


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
    authorization: Optional[str] = Header(None),
):
    """
    Convert speech to text WITH automatic language detection

    Args:
        audio_file: Audio file (WebM, WAV, MP3, OGG, FLAC)
        authorization: Bearer token in Authorization header (optional)

    Returns: Transcribed text with detected language and confidence
    """
    try:
        logger.info(f"Transcribe request: {audio_file.filename} (size: {audio_file.size})")

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
                try:
                    user_id, _ = AuthService.validate_token(token)
                    logger.info(f"Token valid for user: {user_id}")
                except Exception as e:
                    logger.warning(f"Token validation failed: {str(e)}")

        # Validate file size
        contents = await audio_file.read()
        logger.info(f"Audio file size: {len(contents)} bytes")

        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Audio file is empty")

        if len(contents) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 25MB)")

        # Save to temporary file
        suffix = "." + (audio_file.filename.split(".")[-1] if audio_file.filename and "." in audio_file.filename else "webm")
        logger.info(f"Using file suffix: {suffix}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
            logger.info(f"Saved to temp file: {tmp_path}")

        # Transcribe with auto language detection
        logger.info(f"Starting transcription with OpenAI Whisper...")
        text, confidence = VoiceService.recognize_speech(
            audio_file_path=tmp_path,
            language="en",
            user_id=user_id,
        )

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        if not text:
            raise HTTPException(status_code=400, detail="Speech not recognized")

        logger.info(f"Transcription complete: {text[:50]}...")
        return {
            "text": text,
            "language": "auto",
            "confidence": confidence,
            "duration_seconds": len(contents) / 32000,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


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
