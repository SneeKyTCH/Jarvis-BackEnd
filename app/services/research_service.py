"""
Research Service
Web search integration with multiple providers and caching
"""

import asyncio
import logging
import json
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


class ResearchService:
    """Web search and research integration"""

    # Cache file for search results
    CACHE_FILE = Path("search_cache.json")
    CACHE_TTL_HOURS = 24

    @staticmethod
    def _load_cache() -> dict:
        """Load search cache from disk"""
        if ResearchService.CACHE_FILE.exists():
            try:
                with open(ResearchService.CACHE_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load cache: {e}")
        return {}

    @staticmethod
    def _save_cache(cache: dict):
        """Save search cache to disk"""
        try:
            with open(ResearchService.CACHE_FILE, "w") as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    @staticmethod
    def _get_cache_key(query: str) -> str:
        """Generate cache key from query"""
        return hashlib.md5(query.lower().encode()).hexdigest()

    @staticmethod
    def _is_cache_valid(timestamp: str) -> bool:
        """Check if cache entry is still valid"""
        try:
            cached_time = datetime.fromisoformat(timestamp)
            expiry = cached_time + timedelta(hours=ResearchService.CACHE_TTL_HOURS)
            return datetime.now() < expiry
        except:
            return False

    @staticmethod
    async def search_duckduckgo(
        query: str,
        max_results: int = 5,
    ) -> Tuple[Optional[List[dict]], Optional[str]]:
        """
        Search using DuckDuckGo (free, always available)

        Returns: (results, source) or (None, None) on error
        """
        try:
            from duckduckgo_search import DDGS

            logger.info(f"Searching DuckDuckGo for: {query}")

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            # Format results
            formatted = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "source": "duckduckgo",
                }
                for r in results
            ]

            logger.info(f"DuckDuckGo returned {len(formatted)} results")
            return formatted, "duckduckgo"

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {str(e)}")
            return None, None

    @staticmethod
    async def search_google(
        query: str,
        max_results: int = 5,
    ) -> Tuple[Optional[List[dict]], Optional[str]]:
        """
        Search using Google Custom Search (requires API key)

        Returns: (results, source) or (None, None) on error
        """
        try:
            from app.config import settings

            if not settings.google_search_api_key:
                logger.warning("Google Search API key not configured")
                return None, None

            # TODO: Implement Google Custom Search API integration
            # For now, return None to fall back to DuckDuckGo
            logger.warning("Google Search not yet implemented")
            return None, None

        except Exception as e:
            logger.error(f"Google search failed: {str(e)}")
            return None, None

    @staticmethod
    async def search_tavily(
        query: str,
        max_results: int = 5,
    ) -> Tuple[Optional[List[dict]], Optional[str]]:
        """
        Search using Tavily AI Search (requires API key)

        Returns: (results, source) or (None, None) on error
        """
        try:
            from app.config import settings

            if not settings.tavily_api_key:
                logger.warning("Tavily API key not configured")
                return None, None

            # TODO: Implement Tavily API integration
            # For now, return None to fall back to DuckDuckGo
            logger.warning("Tavily Search not yet implemented")
            return None, None

        except Exception as e:
            logger.error(f"Tavily search failed: {str(e)}")
            return None, None

    @staticmethod
    async def smart_search(
        query: str,
        max_results: int = 5,
        user_id: Optional[str] = None,
    ) -> Tuple[List[dict], str, bool]:
        """
        Perform intelligent web search with fallback chain and caching

        Tries providers in order:
        1. Tavily (fastest, AI-optimized)
        2. Google (comprehensive)
        3. DuckDuckGo (free, always available)

        Results are cached for 24 hours.

        Args:
            query: Search query
            max_results: Max results to return
            user_id: User ID for logging (optional)

        Returns: (results, provider_used, was_cached)
        """
        logger.info(f"Smart search: {query} (user: {user_id})")

        # Check cache first
        cache = ResearchService._load_cache()
        cache_key = ResearchService._get_cache_key(query)

        if cache_key in cache:
            cached_entry = cache[cache_key]
            if ResearchService._is_cache_valid(cached_entry.get("timestamp", "")):
                logger.info(f"Cache hit for query: {query}")
                return cached_entry["results"], cached_entry["provider"], True

        # Try providers in order
        providers = [
            ("tavily", ResearchService.search_tavily),
            ("google", ResearchService.search_google),
            ("duckduckgo", ResearchService.search_duckduckgo),
        ]

        for provider_name, provider_func in providers:
            logger.info(f"Trying {provider_name} search...")

            results, source = await provider_func(query, max_results)

            if results and source:
                logger.info(f"Search succeeded with {source}")

                # Cache the results
                cache[cache_key] = {
                    "query": query,
                    "results": results,
                    "provider": source,
                    "timestamp": datetime.now().isoformat(),
                }
                ResearchService._save_cache(cache)

                return results, source, False

        # All providers failed
        logger.error(f"All search providers failed for: {query}")
        return [], "none", False
