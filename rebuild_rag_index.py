"""
Rebuild RAG index for chatbot after updating FAQ.md or other knowledge base files.
Run this script whenever you add/edit Markdown docs in FILE MD/ folder.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PhongTro.settings')
django.setup()

from chatbot.rag_index import build_index

if __name__ == "__main__":
    print("🔄 Rebuilding RAG index...")
    print("📂 Scanning FILE MD/ for Markdown docs...")

    result = build_index(use_embeddings=True)

    n_docs = result.get('n_docs', 0)
    print(f"✅ RAG index rebuilt successfully!")
    print(f"📊 Total documents indexed: {n_docs}")
    print(f"📝 Includes: FAQ.md, CHUC_NANG_CHINH.md, AI_RECOMMENDATION_README.md + RentalPost DB")
    print(f"💾 Saved to: chatbot/rag_index.json")
    print("\n🎉 Chatbot is now ready to answer questions from updated knowledge base!")

    # --- Verify FAQ.md exists and display summary ---
    try:
        base_dir = os.path.dirname(__file__)
        faq_path = os.path.join(base_dir, 'FILE MD', 'FAQ.md')
        if os.path.exists(faq_path):
            with open(faq_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                # Count questions (lines starting with "###")
                question_count = sum(1 for line in lines if line.strip().startswith('### '))
                print(f"📝 FAQ.md verified: {question_count} questions with detailed answers")
                print(f"📍 Location: {faq_path}")
        else:
            print(f"⚠️ Warning: FAQ.md not found at {faq_path}")
    except Exception as e:
        print(f"⚠️ Error checking FAQ.md: {e}")
