"""
Research & Web Search endpoints
Real-time information retrieval with multiple providers
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
import logging

from app.db import get_db
from app.services import AuthService

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request/Response Models ───

class SearchResult(BaseModel):
    """Single search result"""
    title: str
    url: str
    snippet: str
    source: str  # "duckduckgo", "google", "tavily"


class ResearchRequest(BaseModel):
    """Research/search request"""
    query: str
    max_results: int = 5

    class Config:
        example = {
            "query": "latest AI trends 2026",
            "max_results": 5,
        }


class ResearchResponse(BaseModel):
    """Research response with search results"""
    query: str
    results: List[SearchResult]
    provider: str  # Which provider was used
    cached: bool  # Whether results were from cache


# ─── Helper: Import Research Service ───

def get_research_service():
    """Dynamic import of research service"""
    try:
        from app.services import ResearchService
        return ResearchService
    except ImportError:
        logger.warning("ResearchService not available")
        return None


# ─── Endpoints ───

@router.post("/search", response_model=ResearchResponse)
async def search(
    request: ResearchRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Perform web search for real-time information

    This endpoint searches the web using multiple providers:
    1. Tavily (AI-optimized, requires API key)
    2. Google Custom Search (comprehensive, requires API key)
    3. DuckDuckGo (free, always available)

    Automatically falls back to next provider if one fails.
    Results are cached for 24 hours.

    Args:
        request: ResearchRequest with search query
        authorization: Optional Bearer token for user identification
        db: Database session

    Returns: ResearchResponse with search results
    """
    logger.info(f"Research query: {request.query}")

    # Validate token if provided (optional)
    user_id = None
    if authorization:
        token = None
        if " " in authorization:
            parts = authorization.split(" ", 1)
            if parts[0].lower() == "bearer" and len(parts) > 1:
                token = parts[1]
        else:
            token = authorization

        if token:
            user_id, _ = AuthService.validate_token(token)

    # Get research service
    ResearchService = get_research_service()
    if not ResearchService:
        raise HTTPException(status_code=503, detail="Research service unavailable")

    try:
        # Perform search
        results, provider, cached = await ResearchService.smart_search(
            query=request.query,
            max_results=request.max_results,
            user_id=user_id,
        )

        if not results:
            raise HTTPException(status_code=404, detail="No results found")

        return {
            "query": request.query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                    "source": r.get("source", "unknown"),
                }
                for r in results
            ],
            "provider": provider,
            "cached": cached,
        }

    except Exception as e:
        logger.error(f"Research error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)[:100]}")


@router.get("/providers")
async def get_available_providers():
    """
    List available research providers and their status

    Returns information about configured search providers:
    - Tavily (AI-optimized)
    - Google (comprehensive)
    - DuckDuckGo (free)

    Each shows if it's enabled and configured.
    """
    logger.info("Get available research providers")

    from app.config import settings

    providers = {
        "tavily": {
            "name": "Tavily AI Search",
            "enabled": bool(settings.tavily_api_key),
            "description": "AI-optimized search, fastest",
            "priority": 1,
        },
        "google": {
            "name": "Google Custom Search",
            "enabled": bool(settings.google_search_api_key),
            "description": "Most comprehensive results",
            "priority": 2,
        },
        "duckduckgo": {
            "name": "DuckDuckGo",
            "enabled": settings.duckduckgo_search_enabled,
            "description": "Free search, no API key needed",
            "priority": 3,
        },
    }

    return {
        "providers": providers,
        "fallback_chain": "Tavily → Google → DuckDuckGo",
        "cache_ttl_hours": 24,
    }


@router.post("/search-in-conversation/{conversation_id}")
async def search_in_conversation(
    conversation_id: str,
    request: ResearchRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Search and add results to conversation context

    Performs a search and automatically adds the results
    to the conversation for AI to reference.

    Args:
        conversation_id: ID of conversation to add search to
        request: ResearchRequest with search query
        authorization: Bearer token

    Returns: ResearchResponse with results added to conversation
    """
    logger.info(f"Search in conversation {conversation_id}")

    # Validate token
    token = None
    if authorization:
        if " " in authorization:
            parts = authorization.split(" ", 1)
            if parts[0].lower() == "bearer" and len(parts) > 1:
                token = parts[1]
        else:
            token = authorization

    if not token:
        raise HTTPException(status_code=401, detail="Token required for this endpoint")

    user_id, message = AuthService.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail=message)

    # Verify user owns conversation
    from app.services import ChatService
    conversation = ChatService.get_conversation(conversation_id, user_id, db)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Perform search
    ResearchService = get_research_service()
    if not ResearchService:
        raise HTTPException(status_code=503, detail="Research service unavailable")

    try:
        results, provider, cached = await ResearchService.smart_search(
            query=request.query,
            max_results=request.max_results,
            user_id=user_id,
        )

        if not results:
            raise HTTPException(status_code=404, detail="No results found")

        # Add research summary to conversation
        research_summary = f"[Research Results for: {request.query}]\n\n"
        for i, result in enumerate(results, 1):
            research_summary += f"{i}. {result.get('title', '')}\n"
            research_summary += f"   {result.get('snippet', '')}\n"
            research_summary += f"   Source: {result.get('url', '')}\n\n"

        # Add to conversation history
        ChatService.add_message(
            conversation_id=conversation_id,
            role="system",
            content=research_summary,
            db=db,
        )

        return {
            "query": request.query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", ""),
                    "source": r.get("source", "unknown"),
                }
                for r in results
            ],
            "provider": provider,
            "cached": cached,
        }

    except Exception as e:
        logger.error(f"Research error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)[:100]}")
