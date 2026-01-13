"""
Performance Optimization for Chatbot
Lazy loading and caching to speed up first response
"""

import logging
from django.core.cache import cache
from functools import lru_cache
import time

logger = logging.getLogger(__name__)

# Global flag to track if heavy models are loaded
_HEAVY_MODELS_LOADED = False
_RAG_INDEX_LOADED = False


class PerformanceMonitor:
    """Monitor and log performance metrics"""

    @staticmethod
    def time_it(func_name: str):
        """Decorator to measure execution time"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = time.time()
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                if elapsed > 0.1:  # Log only if > 100ms
                    logger.info(f"⏱️ {func_name}: {elapsed:.2f}s")
                return result
            return wrapper
        return decorator


class LazyRAGLoader:
    """Lazy load RAG index only when needed"""

    _instance = None
    _rag_index = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @PerformanceMonitor.time_it("RAG Index Load")
    def load_rag_index(self):
        """Load RAG index lazily"""
        global _RAG_INDEX_LOADED

        if self._rag_index is not None:
            return self._rag_index

        if _RAG_INDEX_LOADED:
            # Already loaded in memory by another instance
            try:
                from chatbot import rag_index
                self._rag_index = rag_index
                return self._rag_index
            except:
                pass

        # Load for first time
        try:
            from chatbot import rag_index
            self._rag_index = rag_index
            _RAG_INDEX_LOADED = True
            logger.info("✅ RAG index loaded successfully")
            return self._rag_index
        except Exception as e:
            logger.warning(f"⚠️ RAG index load failed: {e}")
            return None

    def query(self, text: str, k: int = 5):
        """Query RAG index with lazy loading"""
        rag = self.load_rag_index()
        if rag is None:
            return []

        try:
            return rag.query(text, k=k)
        except Exception as e:
            logger.error(f"❌ RAG query error: {e}")
            return []


class EmbeddingCache:
    """Cache for embedding queries to avoid recomputation"""

    CACHE_PREFIX = "embedding:"
    CACHE_TIMEOUT = 3600  # 1 hour

    @classmethod
    def get_cached_embedding(cls, text: str):
        """Get cached embedding for text"""
        cache_key = f"{cls.CACHE_PREFIX}{hash(text)}"
        return cache.get(cache_key)

    @classmethod
    def set_cached_embedding(cls, text: str, embedding):
        """Cache embedding for text"""
        cache_key = f"{cls.CACHE_PREFIX}{hash(text)}"
        cache.set(cache_key, embedding, cls.CACHE_TIMEOUT)


class FastResponseOptimizer:
    """Optimize response generation for speed"""

    @staticmethod
    def should_skip_rag(query: str) -> bool:
        """
        Determine if we can skip RAG for simple queries
        to speed up response time
        """
        # Skip RAG for very simple queries
        simple_patterns = [
            "xin chào",
            "hello",
            "hi",
            "chào",
            "cảm ơn",
            "thanks",
            "ok",
            "được",
        ]

        query_lower = query.lower().strip()

        # Very short queries likely don't need RAG
        if len(query_lower) < 10:
            for pattern in simple_patterns:
                if pattern in query_lower:
                    return True

        return False

    @staticmethod
    def get_quick_response(query: str) -> str | None:
        """
        Get quick response for common queries without hitting AI
        """
        query_lower = query.lower().strip()

        # Greeting - use word boundaries to avoid false positives
        greeting_patterns = [
            r'\bxin chào\b',
            r'\bhello\b',
            r'\bhi\b',
            r'\bchào bạn\b',
            r'^chào$',  # Just "chào" alone
        ]
        import re
        for pattern in greeting_patterns:
            if re.search(pattern, query_lower):
                return (
                    "Xin chào! 👋 Tôi là trợ lý AI của PhongTro.NMA.\n\n"
                    "Tôi có thể giúp bạn:\n"
                    "- 🔍 Tìm phòng trọ phù hợp\n"
                    "- 💰 Tư vấn về giá cả\n"
                    "- 📋 Hướng dẫn đăng tin\n"
                    "- ❓ Trả lời các câu hỏi về website\n\n"
                    "Bạn cần tìm gì ạ?"
                )

        # Thank you - use word boundaries
        thank_patterns = [
            r'\bcảm ơn\b',
            r'\bcám ơn\b',
            r'\bthanks\b',
            r'\bthank you\b',
        ]
        for pattern in thank_patterns:
            if re.search(pattern, query_lower):
                return "Không có gì! 😊 Nếu cần hỗ trợ thêm, cứ hỏi tôi nhé!"

        return None


# Preload critical data at startup (optional)
def preload_critical_data():
    """
    Preload critical data to cache for faster first response
    Call this during Django startup
    """
    try:
        logger.info("🚀 Preloading critical data...")

        # Preload RAG index in background
        loader = LazyRAGLoader.get_instance()
        loader.load_rag_index()

        logger.info("✅ Critical data preloaded")
    except Exception as e:
        logger.warning(f"⚠️ Preload failed: {e}")


# Export singleton instance
lazy_rag_loader = LazyRAGLoader.get_instance()
