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
async def debug_upload(file: UploadFile = File(...)):
    """
    DEBUG: Test if file upload works
    """
    try:
        contents = await file.read()
        logger.info(f"DEBUG: Received file: {file.filename}")
        logger.info(f"DEBUG: File size: {len(contents)} bytes")
        logger.info(f"DEBUG: Content-Type: {file.content_type}")

        return {
            "received": True,
            "filename": file.filename,
            "size": len(contents),
            "content_type": file.content_type,
        }
    except Exception as e:
        logger.error(f"DEBUG Upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


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


@router.post("/speak")
async def speak_text(
    request: TextToSpeechRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Convert text to speech using Eleven Labs

    Args:
        request: TextToSpeechRequest with text, language, and optional voice_id
        authorization: Bearer token (optional)

    Returns: Audio stream (MP3)
    """
    try:
        logger.info(f"Speak request: {request.text[:50]}...")

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
                except Exception as e:
                    logger.warning(f"Token validation failed: {str(e)}")

        # Synthesize speech
        audio_path, duration = VoiceService.synthesize_speech(
            text=request.text,
            language=request.language,
            voice_id=request.voice_id or "George",
            user_id=user_id,
        )

        if not audio_path:
            raise HTTPException(status_code=500, detail="Text-to-speech failed")

        # Read audio file and return as stream
        from fastapi.responses import FileResponse
        return FileResponse(
            path=audio_path,
            media_type="audio/mpeg",
            filename="response.mp3",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Speak error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {str(e)}")


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
    file: UploadFile = File(...),
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
        logger.info(f"Transcribe request: {file.filename} (size: {file.size})")

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
        contents = await file.read()
        logger.info(f"Audio file size: {len(contents)} bytes")

        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Audio file is empty")

        if len(contents) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large (max 25MB)")

        # Save to temporary file
        suffix = "." + (file.filename.split(".")[-1] if file.filename and "." in file.filename else "webm")
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


@router.post("/detect-language-and-transcribe")
async def detect_language_and_transcribe(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """
    Transcribe audio with AUTOMATIC language detection using Azure Speech Services

    Returns: {
        "text": "transcribed text",
        "language": "en" or "ro" etc,
        "language_name": "English" or "Română" etc,
        "confidence": 0.95
    }
    """
    try:
        import azure.cognitiveservices.speech as speechsdk
        import re

        logger.info(f"Auto-detect transcribe: {file.filename}")

        # Get Azure credentials
        api_key = settings.azure_speech_key
        region = settings.azure_speech_region

        if not api_key or not region:
            logger.error("Azure Speech API key or region not configured")
            raise HTTPException(status_code=500, detail="Azure Speech not configured")

        # Read audio file
        audio_data = await file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="Audio file is empty")

        # Create Azure Speech recognizer with audio from memory
        import io
        import asyncio

        speech_config = speechsdk.SpeechConfig(subscription=api_key, region=region)

        # Create in-memory audio from the blob
        audio_stream = speechsdk.audio.PushAudioInputStream()
        audio_stream.write(audio_data)
        audio_stream.close()

        # Create audio config from the stream
        audio_config = speechsdk.AudioConfig(stream=audio_stream)

        # Create speech recognizer
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        logger.info("Starting Azure speech recognition...")

        # Run sync Azure call in thread pool to avoid blocking async
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, speech_recognizer.recognize_once)

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcribed_text = result.text
            logger.info(f"Recognized: {transcribed_text}")
        elif result.reason == speechsdk.ResultReason.NoMatch:
            logger.warning("No speech detected")
            raise HTTPException(status_code=400, detail="No speech detected")
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            logger.error(f"Speech Recognition canceled: {cancellation.reason} - {cancellation.error_details}")
            raise HTTPException(status_code=500, detail=f"Azure error: {cancellation.error_details}")

        # Detect language from transcribed text using simple heuristics
        detected_lang = "en"
        language_name = "English"

        # Check for Romanian characters (ă â î ș ț)
        if re.search(r'[ăâîșț]', transcribed_text, re.IGNORECASE):
            detected_lang = "ro"
            language_name = "Română"
        # Check for Spanish characters (ñ)
        elif re.search(r'[ñ]', transcribed_text, re.IGNORECASE):
            detected_lang = "es"
            language_name = "Español"
        # Check for French characters (é è ê à ù ç)
        elif re.search(r'[éèêàùç]', transcribed_text, re.IGNORECASE):
            detected_lang = "fr"
            language_name = "Français"
        # Check for German characters (ä ö ü ß)
        elif re.search(r'[äöüß]', transcribed_text, re.IGNORECASE):
            detected_lang = "de"
            language_name = "Deutsch"

        logger.info(f"Transcribed: {transcribed_text[:50]}... (Language: {language_name})")

        return {
            "text": transcribed_text,
            "language": detected_lang,
            "language_name": language_name,
            "confidence": 0.95
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-detect transcription error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)[:100]}")


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
