from django.core.management.base import BaseCommand
import os
import sys
import importlib

class Command(BaseCommand):
    help = "Build RAG index: TF-IDF + vector embeddings (if sentence-transformers installed)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-embeddings',
            action='store_true',
            help='Skip vector embeddings (build only TF-IDF index)',
        )
        parser.add_argument(
            '--no-reload',
            action='store_true',
            help='Skip cache reload after building',
        )

    def handle(self, *args, **options):
        # Tự động dùng CPU để tránh CUDA out of memory
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

        from chatbot.rag_index import build_index, INDEX_PATH

        use_embeddings = not options.get('no_embeddings', False)
        auto_reload = not options.get('no_reload', False)

        self.stdout.write("🔨 Building RAG index...")
        if use_embeddings:
            self.stdout.write("   - TF-IDF index (JSON)")
            self.stdout.write("   - Vector embeddings (requires sentence-transformers)")
        else:
            self.stdout.write("   - TF-IDF index only (--no-embeddings flag)")

        idx = build_index(use_embeddings=use_embeddings)
        n = idx.get('n_docs', 0)

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Built RAG index with {n} documents"
        ))
        self.stdout.write(f"   TF-IDF index: {INDEX_PATH}")

        if use_embeddings:
            try:
                from chatbot.models import VectorDocument
                vec_count = VectorDocument.objects.count()
                self.stdout.write(f"   Vector docs: {vec_count} embeddings in DB")
            except Exception:
                self.stdout.write(self.style.WARNING(
                    "   ⚠️ Vector embeddings skipped (sentence-transformers not installed?)"
                ))

        # Auto-reload cache if server is running
        if auto_reload:
            self.stdout.write("\n🔄 Reloading cache...")
            try:
                from chatbot.performance_optimizer import LazyRAGLoader
                import chatbot.performance_optimizer as perf_opt

                # Reset global flag
                perf_opt._RAG_INDEX_LOADED = False

                # Clear instance cache
                loader = LazyRAGLoader.get_instance()
                loader._rag_index = None

                # Reload module
                if 'chatbot.rag_index' in sys.modules:
                    importlib.reload(sys.modules['chatbot.rag_index'])

                # Force load new index
                loader.load_rag_index()

                self.stdout.write(self.style.SUCCESS("✅ Cache reloaded successfully"))
                self.stdout.write(self.style.WARNING(
                    "⚠️  If chatbot still shows old data, restart the server with: python manage.py runserver"
                ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Cache reload failed: {e}\n"
                    f"   Please run: python manage.py reload_rag_cache"
                ))
