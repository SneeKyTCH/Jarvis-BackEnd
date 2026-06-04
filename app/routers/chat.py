"""
Chat endpoints
Text messages, streaming responses, conversation management
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header, Body, Request
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from uuid import uuid4
import logging
import asyncio

from app.db import get_db
from app.services import ChatService, AuthService
from app.models import Conversation, Message

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Dependencies ───

def get_user_id_from_token(request: Request) -> str:
    """Extract and validate JWT token from Authorization header"""
    logger.info("=== GET_USER_ID_FROM_TOKEN CALLED ===")

    # Get authorization header
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    logger.info(f"Authorization header value: {auth_header}")
    logger.info(f"All headers: {dict(request.headers)}")

    if not auth_header:
        logger.error("No authorization header found!")
        raise HTTPException(status_code=401, detail="No token provided")

    # Extract token
    token = None
    if " " in auth_header:
        parts = auth_header.split(" ", 1)
        if parts[0].lower() == "bearer" and len(parts) > 1:
            token = parts[1]
    else:
        token = auth_header

    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    # Validate token
    user_id, message = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail=message)

    return user_id


# ─── Request/Response Models ───
class MessageResponse(BaseModel):
    """Single message in conversation"""
    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: str


class ChatRequest(BaseModel):
    """Chat request - send message, get response"""
    message: str
    conversation_id: Optional[str] = None
    language: Optional[str] = None  # Auto-detect if not provided

    class Config:
        example = {
            "message": "Hello, can you help me understand AI?",
            "conversation_id": "conv_123",
            "language": "en",
        }


class ChatResponse(BaseModel):
    """Chat response - AI response to message"""
    conversation_id: str
    message_id: str
    response: str
    language: str
    timestamp: str
    tokens_used: Optional[int] = None

    class Config:
        example = {
            "conversation_id": "conv_123",
            "message_id": "msg_456",
            "response": "AI response here...",
            "language": "en",
            "timestamp": "2026-06-04T10:30:00Z",
            "tokens_used": 150,
        }


class ConversationResponse(BaseModel):
    """Conversation metadata and history"""
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    language: str
    messages: List[MessageResponse]


# ─── Endpoints ───

@router.post("/send", response_model=ChatResponse)
async def send_message(
    chat_request: ChatRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Send a message and get AI response

    Args:
        chat_request: ChatRequest with message, optional conversation_id and language
        http_request: Raw HTTP request
        db: Database session

    Returns: ChatResponse with AI response
    """
    # Get authorization header directly from http_request.headers
    # Try both lowercase and standard case
    auth_header = http_request.headers.get("authorization")
    if not auth_header:
        auth_header = http_request.headers.get("Authorization")

    if not auth_header:
        all_headers = dict(http_request.headers)
        logger.error("=" * 60)
        logger.error("NO AUTHORIZATION HEADER FOUND!")
        logger.error(f"Request type: {type(http_request)}")
        logger.error(f"Request URL: {http_request.url}")
        logger.error(f"Total headers count: {len(all_headers)}")
        logger.error(f"Header keys: {list(all_headers.keys())}")
        logger.error(f"All headers: {all_headers}")
        logger.error("=" * 60)
        raise HTTPException(status_code=401, detail="No token provided")

    # Extract token from "Bearer <token>" format
    token = None
    if " " in auth_header:
        parts = auth_header.split(" ", 1)
        if parts[0].lower() == "bearer" and len(parts) > 1:
            token = parts[1]
    else:
        token = auth_header

    if not token:
        raise HTTPException(status_code=401, detail="No token provided")

    # Validate token
    user_id, message_result = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail=message_result)

    logger.info(f"Chat message received: {chat_request.message[:50]}...")
    message = chat_request.message
    conversation_id = chat_request.conversation_id
    language = chat_request.language

    # Validate token and get user_id
    user_id, message = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail=message)

    # Get conversation or create new one
    if request.conversation_id:
        conversation = ChatService.get_conversation(request.conversation_id, user_id, db)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = ChatService.create_conversation(user_id, request.language or "en", db)

    # Save user message
    user_msg = ChatService.add_message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
        db=db,
    )

    # Get AI response
    ai_response = await ChatService.get_ai_response(
        message=request.message,
        conversation_id=conversation.id,
        user_id=user_id,
        language=request.language or conversation.language,
        db=db,
    )

    # Get the saved AI response message (just added by service)
    ai_msg = db.query(Message).filter(
        Message.conversation_id == conversation.id,
        Message.role == "assistant",
    ).order_by(Message.created_at.desc()).first()

    return {
        "conversation_id": conversation.id,
        "message_id": ai_msg.id if ai_msg else str(uuid4().hex[:8]),
        "response": ai_response,
        "language": conversation.language,
        "timestamp": ai_msg.created_at.isoformat() if ai_msg else "",
        "tokens_used": ai_msg.tokens_used if ai_msg else None,
    }


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    WebSocket endpoint for real-time chat with streaming responses

    Sends tokens as they're generated by the LLM.
    """
    await websocket.accept()
    logger.info(f"WebSocket chat connected: {conversation_id}")

    # Validate token
    if not token:
        await websocket.send_json({"type": "error", "error": "No token provided"})
        await websocket.close(code=1008)
        return

    user_id, message = AuthService.validate_token(token)
    if not user_id:
        await websocket.send_json({"type": "error", "error": "Invalid token"})
        await websocket.close(code=1008)
        return

    # Verify user owns conversation
    conversation = ChatService.get_conversation(conversation_id, user_id, db)
    if not conversation:
        await websocket.send_json({"type": "error", "error": "Conversation not found"})
        await websocket.close(code=1008)
        return

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message_text = data.get("message", "")

            if not message_text:
                await websocket.send_json({
                    "type": "error",
                    "error": "Empty message",
                })
                continue

            logger.info(f"WebSocket message: {message_text[:50]}...")

            # Save user message
            ChatService.add_message(
                conversation_id=conversation_id,
                role="user",
                content=message_text,
                db=db,
            )

            # Send start signal
            message_id = str(uuid4().hex[:8])
            await websocket.send_json({
                "type": "start",
                "message_id": message_id,
            })

            # Get AI response (streaming simulation)
            ai_response = await ChatService.get_ai_response(
                message=message_text,
                conversation_id=conversation_id,
                user_id=user_id,
                language=conversation.language,
                db=db,
            )

            # Send response in chunks
            chunk_size = 20
            for i in range(0, len(ai_response), chunk_size):
                chunk = ai_response[i:i+chunk_size]
                await websocket.send_json({
                    "type": "token",
                    "content": chunk,
                })
                await asyncio.sleep(0.05)  # Simulate streaming

            await websocket.send_json({
                "type": "complete",
                "tokens_used": None,
            })

    except WebSocketDisconnect:
        logger.info(f"WebSocket chat disconnected: {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except:
            pass
        await websocket.close(code=1011)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Get conversation history and metadata

    Args:
        conversation_id: ID of conversation to fetch
        http_request: Raw HTTP request (for auth header from middleware)

    Returns: Conversation with all messages
    """
    logger.info(f"Get conversation: {conversation_id}")

    # Get auth from request.state
    auth_header = getattr(http_request.state, "auth_header", None)
    if not auth_header:
        raise HTTPException(status_code=401, detail="No token provided")

    token = auth_header.split(" ", 1)[1] if " " in auth_header else auth_header
    user_id, _ = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get conversation (verify user owns it)
    conversation = ChatService.get_conversation(conversation_id, user_id, db)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get messages
    messages = ChatService.get_conversation_history(conversation_id, limit=100, db=db)

    return {
        "id": conversation.id,
        "title": conversation.title or "Untitled",
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "message_count": conversation.message_count,
        "language": conversation.language,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
    }


@router.get("/conversations")
async def list_conversations(
    http_request: Request,
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """
    List user's conversations

    Args:
        limit: Number of conversations to return
        offset: Pagination offset
        http_request: Raw HTTP request (for auth header from middleware)

    Returns: List of conversations
    """
    logger.info(f"List conversations: limit={limit}, offset={offset}")

    # Get auth from request.state
    auth_header = getattr(http_request.state, "auth_header", None)
    if not auth_header:
        raise HTTPException(status_code=401, detail="No token provided")

    token = auth_header.split(" ", 1)[1] if " " in auth_header else auth_header
    user_id, _ = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get conversations for user
    conversations = ChatService.list_user_conversations(user_id, limit, offset, db)

    return {
        "total": len(conversations),
        "limit": limit,
        "offset": offset,
        "conversations": [
            {
                "id": conv.id,
                "title": conv.title or "Untitled",
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "message_count": conv.message_count,
                "language": conv.language,
            }
            for conv in conversations
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Delete a conversation

    Args:
        conversation_id: ID of conversation to delete
        http_request: Raw HTTP request (for auth header from middleware)

    Returns: Confirmation message
    """
    logger.info(f"Delete conversation: {conversation_id}")

    # Get auth from request.state
    auth_header = getattr(http_request.state, "auth_header", None)
    if not auth_header:
        raise HTTPException(status_code=401, detail="No token provided")

    token = auth_header.split(" ", 1)[1] if " " in auth_header else auth_header
    user_id, _ = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Delete conversation
    success = ChatService.delete_conversation(conversation_id, user_id, db)

    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "status": "success",
        "message": f"Conversation {conversation_id} deleted",
    }
