"""
Embedding service for RAG with Vietnamese support.
Uses sentence-transformers with multilingual models.
Gracefully handles missing dependencies.

Environment tweaks:
- Set TRANSFORMERS_NO_TF=1 to avoid importing TensorFlow (heavy, causing NumPy ABI issues).
- Suppress TF logs if accidentally imported.
"""

from typing import List
import logging
import os

# Prevent transformers from attempting to import TensorFlow (optional components)
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")  # silence TF logs if it loads

logger = logging.getLogger(__name__)

_model = None
_model_name = 'paraphrase-multilingual-mpnet-base-v2'  # 768-dim, good for Vietnamese
_fallback_model_name = 'distiluse-base-multilingual-cased-v2'  # lighter fallback


def _load_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        try:
            _model = SentenceTransformer(_model_name)
            logger.info(f"✅ Loaded embedding model: {_model_name}")
        except Exception as primary_err:
            logger.warning(f"⚠️ Primary model failed ({_model_name}): {primary_err}. Trying fallback {_fallback_model_name}.")
            try:
                _model = SentenceTransformer(_fallback_model_name)
                logger.info(f"✅ Loaded fallback embedding model: {_fallback_model_name}")
            except Exception as fallback_err:
                logger.error(f"❌ Failed to load fallback model: {fallback_err}")
                _model = None
        return _model
    except ImportError:
        logger.warning(
            "⚠️ sentence-transformers not installed. Run: pip install sentence-transformers"
        )
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected embedding init error: {e}")
        return None


def encode(texts: List[str]) -> List[List[float]] | None:
    """
    Encode list of texts to embeddings.
    Returns None if model not available.
    """
    model = _load_model()
    if model is None:
        return None
    try:
        # encode returns numpy array, convert to list for JSON serialization
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]
    except Exception as e:
        logger.error(f"❌ Embedding encode error: {e}")
        return None


def encode_single(text: str) -> List[float] | None:
    """Encode single text to embedding vector."""
    result = encode([text])
    return result[0] if result else None


def get_embedding_dim() -> int:
    """Return embedding dimension (768 for mpnet-base)."""
    return 768
