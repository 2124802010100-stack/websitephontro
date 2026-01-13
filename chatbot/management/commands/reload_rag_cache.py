"""
Management command to reload RAG index cache without restarting server.
Usage: python manage.py reload_rag_cache
"""

from django.core.management.base import BaseCommand
from chatbot.performance_optimizer import LazyRAGLoader
import chatbot.performance_optimizer as perf_opt
import importlib
import sys


class Command(BaseCommand):
    help = 'Reload RAG index cache from updated JSON file'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Reloading RAG index cache...")

        try:
            # Step 1: Reset global flag
            perf_opt._RAG_INDEX_LOADED = False
            self.stdout.write(self.style.SUCCESS("✅ Reset global flag"))

            # Step 2: Clear instance cache
            loader = LazyRAGLoader.get_instance()
            loader._rag_index = None
            self.stdout.write(self.style.SUCCESS("✅ Cleared instance cache"))

            # Step 3: Reload rag_index module
            if 'chatbot.rag_index' in sys.modules:
                importlib.reload(sys.modules['chatbot.rag_index'])
                self.stdout.write(self.style.SUCCESS("✅ Reloaded rag_index module"))

            # Step 4: Force load new index
            loader.load_rag_index()
            self.stdout.write(self.style.SUCCESS("✅ Loaded new RAG index"))

            # Step 5: Test query
            test_results = loader.query("gói VIP", k=3)
            self.stdout.write(f"✅ Test query returned {len(test_results)} results")

            if test_results:
                self.stdout.write("\n📋 Sample result:")
                first = test_results[0]
                self.stdout.write(f"  - Title: {first.get('title', 'N/A')}")
                self.stdout.write(f"  - Snippet: {first.get('snippet', 'N/A')[:100]}...")

            self.stdout.write(self.style.SUCCESS("\n🎉 RAG cache reloaded successfully!"))
            self.stdout.write(self.style.WARNING("\n⚠️  Note: Chatbot views may still cache responses. Test with a new question."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Reload failed: {e}"))
            import traceback
            traceback.print_exc()
