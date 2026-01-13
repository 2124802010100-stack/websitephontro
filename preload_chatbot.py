"""
Preload chatbot models to speed up first request
Run this after Django server starts
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PhongTro.settings')
django.setup()

import logging
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def preload_models():
    """Preload all heavy models"""
    print("\n" + "="*60)
    print("🚀 PRELOADING CHATBOT MODELS")
    print("="*60 + "\n")

    # 1. Preload Grop chatbot
    try:
        print("1. Loading Grop chatbot...")
        from chatbot.grop_service import get_grop_chatbot
        bot = get_grop_chatbot()
        print("✅ Grop chatbot loaded\n")
    except Exception as e:
        print(f"❌ Failed to load Grop chatbot: {e}\n")

    # 2. Preload RAG index (lazy loader will cache it)
    try:
        print("2. Loading RAG index...")
        from chatbot.performance_optimizer import lazy_rag_loader
        rag = lazy_rag_loader.load_rag_index()
        if rag:
            print("✅ RAG index loaded\n")
        else:
            print("⚠️ RAG index not available\n")
    except Exception as e:
        print(f"❌ Failed to load RAG: {e}\n")

    # 3. Warm up with a test query (DISABLED to save quota)
    # KHÔNG chạy test query để tránh tiêu tốn quota không cần thiết
    # Nếu cần test, hãy test thủ công qua chatbot UI
    print("3. Test query SKIPPED (to save API quota)\n")
    print("💡 Test chatbot manually via UI instead\n")

    print("="*60)
    print("✅ PRELOAD COMPLETED")
    print("="*60 + "\n")


if __name__ == "__main__":
    preload_models()
