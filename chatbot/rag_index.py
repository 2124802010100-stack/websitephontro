

from __future__ import annotations
import json
import os
import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import logging
from django.utils import timezone

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)
INDEX_PATH = os.path.join(os.path.dirname(__file__), 'rag_index.json')


def _normalize(text: str) -> str:
    if not text:
        return ''
    s = text.lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # unify whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokenize(text: str) -> List[str]:
    s = _normalize(text)
    # split on non-word; keep Vietnamese words after normalization
    toks = re.split(r"[^a-z0-9_]+", s)
    return [t for t in toks if t]


@dataclass
class Doc:
    id: str
    kind: str  # 'md' | 'post' | 'vip'
    title: str
    url: str
    text: str
    tokens: List[str]
    # Rich metadata for better ranking
    metadata: Dict[str, Any] = None  # category, price, area, province, created_at, etc.
    created_at: str = None  # ISO timestamp for freshness scoring

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def _gather_markdown_docs() -> List[Doc]:
    """
    Collect user-facing Markdown docs only.
    - Source restricted to "FILE MD/" to avoid indexing internal dev docs.
    - Exclude dynamic pricing documents; pricing comes from database.
    - Exclude internal setup/AI docs not meant for end users.
    """
    root = os.path.join(settings.BASE_DIR, 'FILE MD')

    # Exclude files with dynamic VIP pricing info (will use database instead)
    EXCLUDED_FILES = {
        'PAYMENT_FLOW.md',   # contains VIP prices; use DB
        'FREE_VS_VIP.md',    # contains VIP prices; use DB
    }

    # Exclude entire subfolders that are developer/internal docs
    EXCLUDED_SUBDIR_NAMES = {
        'chatbot',   # internal chatbot docs
        'goiy_ai',   # internal AI docs
        'setup',     # environment/setup guides
        '.git',
        '__pycache__',
    }

    docs: List[Doc] = []
    if not os.path.isdir(root):
        return docs

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip excluded subfolders by mutating dirnames in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_SUBDIR_NAMES]

        for fn in filenames:
            if not fn.lower().endswith(('.md', '.markdown')):
                continue

            if fn in EXCLUDED_FILES:
                logger.info(f"⏭️  Skipping {fn} (VIP data from database instead)")
                continue

            path = os.path.join(dirpath, fn)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                rel = os.path.relpath(path, settings.BASE_DIR).replace('\\', '/')
                title = os.path.splitext(os.path.basename(path))[0]

                # Split FAQ.md into sections (each H3 question = 1 doc)
                if 'FAQ' in title.upper():
                    sections = _split_faq_sections(content, rel)
                    docs.extend(sections)
                else:
                    # Regular MD file: index as single document
                    toks = _tokenize(content)
                    if not toks:
                        continue
                    docs.append(Doc(
                        id=f"md:{rel}",
                        kind='md',
                        title=title,
                        url=f"/docs/{rel}",
                        text=content[:2000],  # cap text to 2k chars
                        tokens=toks,
                    ))
            except Exception:
                continue
    return docs


def _split_faq_sections(content: str, rel_path: str) -> List[Doc]:
    """Split FAQ.md into sections by H2/H3 headings with smart chunking.

    Strategy:
    - H2 (##) = Major categories (e.g., "Câu hỏi về hệ thống")
    - H3 (###) = Individual Q&A pairs
    - Each H3 = 1 searchable chunk (better than full file)
    - Keep parent H2 context for better understanding
    """
    import re
    sections = []

    # First, split by H2 to get categories
    h2_parts = re.split(r'\n## ', content)

    for h2_idx, h2_part in enumerate(h2_parts):
        if not h2_part.strip():
            continue

        # Extract H2 title (category)
        h2_lines = h2_part.strip().split('\n', 1)
        h2_title = h2_lines[0].strip() if h2_lines else ""
        h2_content = h2_lines[1] if len(h2_lines) > 1 else ""

        # Skip intro/title section
        if h2_idx == 0 and not h2_title.startswith('🔷'):
            continue

        # Now split H2 content by H3 (individual questions)
        h3_parts = re.split(r'\n### ', h2_content)

        for h3_idx, h3_part in enumerate(h3_parts):
            if not h3_part.strip() or len(h3_part) < 30:
                continue

            # Extract question from first line
            h3_lines = h3_part.strip().split('\n', 1)
            question = h3_lines[0].strip() if h3_lines else ""
            answer = h3_lines[1].strip() if len(h3_lines) > 1 else ""

            # Skip if no real content
            if not question or not answer:
                continue

            # Build rich context: question + answer + category context
            full_text = f"{h2_title}\n\nCâu hỏi: {question}\n\nTrả lời: {answer}"

            # Tokenize
            toks = _tokenize(full_text)
            if not toks or len(toks) < 5:
                continue

            # Create document with metadata
            doc_id = f"md:{rel_path}#h2{h2_idx}h3{h3_idx}"
            sections.append(Doc(
                id=doc_id,
                kind='md',
                title=f"FAQ: {question[:80]}",  # Truncate long questions
                url=f"/docs/{rel_path}#{_slugify(question)}",
                text=full_text[:2000],  # Keep generous context
                tokens=toks,
                metadata={
                    'category': h2_title,
                    'question': question,
                    'answer': answer[:500],  # Preview
                    'doc_type': 'faq',
                },
            ))

    logger.info(f"📚 Split FAQ into {len(sections)} Q&A chunks")
    return sections


def _slugify(text: str) -> str:
    """Simple slugify for anchor links."""
    import re
    s = _normalize(text)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:50]


def _gather_posts() -> List[Doc]:
    """Gather active rental posts with RICH METADATA for better ranking."""
    from website.models import RentalPost
    from django.utils import timezone
    from django.db.models import Q
    now = timezone.now()
    posts = (RentalPost.objects
             .filter(is_approved=True, is_deleted=False, is_rented=False)
             .filter(Q(expired_at__isnull=True) | Q(expired_at__gt=now))
             .select_related('province', 'district')
             .only('id', 'title', 'description', 'address', 'province__name', 'district__name',
                   'category', 'price', 'area', 'created_at', 'features'))
    docs: List[Doc] = []
    for p in posts:
        title = p.title or 'Phòng trọ'
        prov = getattr(p.province, 'name', '') or ''
        dist = getattr(p.district, 'name', '') or ''
        addr = ', '.join([a for a in [p.address, dist, prov] if a])

        # Rich text with structured info for better matching
        cat_label = ''
        if hasattr(p, 'category') and p.category:
            # Import here to avoid circular dependency
            try:
                from website.models import RentalPost as RP
                cat_label = dict(RP.CATEGORY_CHOICES).get(p.category, p.category)
            except Exception:
                cat_label = p.category

        text_parts = [
            title,
            f"Loại: {cat_label}" if cat_label else "",
            f"Giá: {p.price} triệu/tháng" if p.price else "",
            f"Diện tích: {p.area}m²" if p.area else "",
            f"Địa chỉ: {addr}",
            p.description or '',
        ]
        text = '\n'.join([t for t in text_parts if t])

        toks = _tokenize(text)
        if not toks:
            continue

        # Build metadata for intelligent ranking
        docs.append(Doc(
            id=f"post:{p.id}",
            kind='post',
            title=title,
            url=f"/post/{p.id}/",
            text=text[:1500],  # Increased context
            tokens=toks,
            metadata={
                'category': p.category if hasattr(p, 'category') else None,
                'price': float(p.price) if p.price else None,
                'area': float(p.area) if p.area else None,
                'province': prov,
                'district': dist,
                'features': list(p.features) if hasattr(p, 'features') and p.features else [],
            },
            created_at=p.created_at.isoformat() if hasattr(p, 'created_at') and p.created_at else None,
        ))
    logger.info(f"📦 Gathered {len(docs)} rental posts with rich metadata")
    return docs


def _gather_vip_configs() -> List[Doc]:
    """Gather VIP package configurations from database"""
    from website.models import VIPPackageConfig
    from django.utils import timezone

    docs: List[Doc] = []
    vip_packages = VIPPackageConfig.objects.filter(is_active=True)

    if not vip_packages.exists():
        return docs

    # Create a comprehensive VIP pricing document
    now = timezone.now()
    vip_lines = [
        "# Bảng giá gói VIP - PhongTro.NMA",
        f"📅 Áp dụng từ: {now.strftime('%d/%m/%Y')}",
        "",
    ]

    for vip in vip_packages:
        color_display = vip.get_title_color_display()
        plan_display = vip.get_plan_display()

        vip_lines.append(f"• {plan_display}: {vip.posts_per_day} tin/ngày • Hạn {vip.expire_days} ngày • {color_display.upper()} • Giá: {vip.price:,.0f}đ")

    vip_lines.append("")
    vip_lines.append("💡 Lưu ý: Thông tin này được lấy trực tiếp từ database, luôn cập nhật mới nhất.")

    text = "\n".join(vip_lines)
    toks = _tokenize(text)

    if toks:
        docs.append(Doc(
            id="vip:pricing",
            kind='vip',
            title="Bảng giá VIP",
            url="/pricing/",
            text=text,
            tokens=toks,
        ))

    # Individual VIP package docs for better matching
    for vip in vip_packages:
        color_display = vip.get_title_color_display()
        plan_display = vip.get_plan_display()

        text = f"""
{plan_display} - Gói VIP cho chủ nhà
Giá: {vip.price:,.0f}đ
Thời hạn: {vip.expire_days} ngày
Số tin đăng: {vip.posts_per_day} tin/ngày
Màu tiêu đề: {color_display}
Độ ưu tiên: {vip.stars} sao

Phù hợp cho: Chủ nhà muốn đăng tin nổi bật với màu {color_display.lower()}.
"""
        toks = _tokenize(text)
        if toks:
            docs.append(Doc(
                id=f"vip:{vip.plan}",
                kind='vip',
                title=f"{plan_display} - {vip.price:,.0f}đ",
                url="/pricing/",
                text=text.strip(),
                tokens=toks,
            ))

    return docs


def build_index(save_path: str | None = None, use_embeddings: bool = True) -> Dict[str, Any]:
    """
    Build both TF-IDF index and vector embeddings with RICH METADATA.

    Improvements:
    1. Store metadata (category, price, area, created_at) for each doc
    2. Incremental indexing support (TODO: future enhancement)
    3. Better logging and error handling

    Args:
        save_path: custom path for TF-IDF JSON index
        use_embeddings: if True, also build vector embeddings (requires sentence-transformers)
    """
    logger.info("🔨 Building RAG index...")
    docs = _gather_markdown_docs() + _gather_posts() + _gather_vip_configs()
    logger.info(f"📚 Total documents: {len(docs)} (MD={sum(1 for d in docs if d.kind=='md')}, "
                f"Posts={sum(1 for d in docs if d.kind=='post')}, VIP={sum(1 for d in docs if d.kind=='vip')})")

    # 1. Build TF-IDF index (lightweight, always built)
    df: Dict[str, int] = {}
    for d in docs:
        seen = set(d.tokens)
        for t in seen:
            df[t] = df.get(t, 0) + 1
    n_docs = max(1, len(docs))

    stored = []
    for d in docs:
        tf = {}
        for t in d.tokens:
            tf[t] = tf.get(t, 0) + 1

        # Store with RICH METADATA for intelligent ranking
        stored.append({
            'id': d.id,
            'kind': d.kind,
            'title': d.title,
            'url': d.url,
            'text': d.text,
            'len': len(d.tokens),
            'tf': tf,
            'metadata': d.metadata,  # NEW: rich metadata
            'created_at': d.created_at,  # NEW: for freshness scoring
        })

    index = {
        'n_docs': n_docs,
        'df': df,
        'docs': stored,
        'built_at': timezone.now().isoformat() if 'timezone' in dir() else None,
        'version': '2.0',  # Upgraded version with metadata
    }

    dest = save_path or INDEX_PATH
    try:
        with open(dest, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Saved TF-IDF index v2.0: {dest} ({n_docs} docs)")
    except Exception as e:
        logger.error(f"❌ Failed to save TF-IDF index: {e}")

    # 2. Build vector embeddings (optional, requires sentence-transformers)
    if use_embeddings:
        _build_vector_index(docs)

    return index


def _build_vector_index(docs: List[Doc]):
    """Build and store vector embeddings for all documents."""
    try:
        from chatbot import embedding_service
        from chatbot.models import VectorDocument
    except ImportError:
        logger.warning("⚠️ Cannot import embedding_service or VectorDocument")
        return

    # Clear old embeddings
    VectorDocument.objects.all().delete()
    logger.info(f"🗑️ Cleared old vector embeddings")

    # Encode all docs
    texts = [d.text for d in docs]
    embeddings = embedding_service.encode(texts)

    if embeddings is None:
        logger.warning("⚠️ Embeddings not available (sentence-transformers not installed?)")
        return

    # Store in DB
    vector_docs = []
    for doc, emb in zip(docs, embeddings):
        vector_docs.append(VectorDocument(
            doc_id=doc.id,
            kind=doc.kind,
            title=doc.title,
            url=doc.url,
            text_snippet=doc.text[:400],
            embedding_json=json.dumps(emb),  # fallback storage
        ))

    VectorDocument.objects.bulk_create(vector_docs, batch_size=100)
    logger.info(f"✅ Stored {len(vector_docs)} vector embeddings in DB")


def _load_index(path: str | None = None) -> Dict[str, Any] | None:
    src = path or INDEX_PATH
    if not os.path.exists(src):
        return None
    try:
        with open(src, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _idf(df: Dict[str, int], n_docs: int, term: str) -> float:
    import math
    return math.log((n_docs + 1) / (1 + df.get(term, 0))) + 1.0


def _expand_query(text: str) -> str:
    """Mở rộng câu hỏi với synonyms Tiếng Việt để tăng recall.

    Ví dụ: 'giá rẻ' → 'giá rẻ giá thấp bình dân'
    """
    # Synonym groups (each word expands to include all synonyms in its group)
    SYNONYMS = {
        # Price synonyms
        'rẻ': 'rẻ re thấp thap bình dân binh dan phai chăng',
        'đắt': 'đắt dat cao sang trọng tron',
        'giá': 'giá gia tiền tien mức muc phí phi chi phí chip',

        # Size synonyms
        'rộng': 'rộng rong lớn lon to thoáng thoang',
        'hẹp': 'hẹp hep nhỏ nho bé be chật chat',
        'diện tích': 'diện tích dien tich dt m2 mét vuông met vuong',

        # Location synonyms
        'gần': 'gần gan cạnh canh kề ke liền lien',
        'xa': 'xa ngoại ô ngoai o',
        'trung tâm': 'trung tâm trung tam tt trung tam',

        # Room type synonyms
        'phòng': 'phòng phong căn can nhà nha',
        'trọ': 'trọ tro thuê thue rental',
        'căn hộ': 'căn hộ can ho chung cư chung cu apartment',

        # Features
        'máy lạnh': 'máy lạnh may lanh điều hòa dieu hoa aircon air conditioner',
        'thang máy': 'thang máy thang may elevator lift',
        'wifi': 'wifi wi-fi internet mạng mang',
    }

    expanded_terms = [text]  # Always include original
    text_lower = text.lower()

    for key, synonyms in SYNONYMS.items():
        if key in text_lower:
            expanded_terms.extend(synonyms.split())

    # Return unique expanded query (avoid duplicates)
    return ' '.join(dict.fromkeys(expanded_terms))


def query(text: str, k: int = 5, index_path: str | None = None, use_semantic: bool = True) -> List[Dict[str, Any]]:
    """
    Query for relevant documents using ADVANCED HYBRID retrieval.

    Improvements:
    1. Query expansion with Vietnamese synonyms
    2. Hybrid TF-IDF + semantic search
    3. Freshness boost for recent posts
    4. Metadata-aware re-ranking
    5. Smart deduplication

    Args:
        text: query text
        k: number of results
        index_path: custom TF-IDF index path
        use_semantic: if True, use vector similarity (requires embeddings)

    Returns hybrid results from TF-IDF + vector similarity (merged and deduplicated).
    """
    # 0. Expand query with synonyms
    expanded_text = _expand_query(text)
    logger.info(f"🔍 Query expanded: '{text}' → '{expanded_text[:100]}'")
    # 1. TF-IDF search with expanded query (always available)
    tfidf_results = _query_tfidf(expanded_text, k=k*2, index_path=index_path, original_query=text)

    # 2. Vector search (if enabled and available)
    vector_results = []
    if use_semantic:
        vector_results = _query_vectors(expanded_text, k=k*2)

    # 3. Merge and deduplicate by doc_id with INTELLIGENT SCORING
    merged = {}
    for r in tfidf_results + vector_results:
        doc_id = r['id']

        # Boost VIP docs from database (kind='vip') to prioritize over markdown when relevant
        score_multiplier = 3.0 if r.get('kind') == 'vip' else 1.0
        r['score'] = r['score'] * score_multiplier

        if doc_id not in merged:
            merged[doc_id] = r
        else:
            # Hybrid boost: if appears in BOTH TF-IDF and semantic → high confidence
            existing_score = merged[doc_id]['score']
            new_score = r['score']
            # Take max and apply hybrid bonus
            merged[doc_id]['score'] = max(existing_score, new_score) * 1.35  # 35% bonus for hybrid match
            # Merge metadata
            if 'metadata' in r and r['metadata']:
                merged[doc_id]['metadata'].update(r['metadata'])

    # Sort by score and return top k
    results = sorted(merged.values(), key=lambda x: x['score'], reverse=True)
    logger.info(f"📊 RAG found {len(results)} results (returning top {k})")
    return results[:k]


def _query_tfidf(text: str, k: int = 5, index_path: str | None = None, original_query: str = None) -> List[Dict[str, Any]]:
    """ADVANCED TF-IDF retrieval with context-aware scoring.

    Enhancements:
    1. Query intent detection (FAQ vs search vs VIP)
    2. Metadata-based boosting (price, area, location match)
    3. Freshness boost for recent posts
    4. Title matching bonus
    """
    idx = _load_index(index_path)
    if idx is None:
        # Try to build on the fly if DB is accessible
        try:
            with connection.cursor():
                pass
            idx = build_index(index_path, use_embeddings=False)
        except Exception:
            return []

    q_tokens = _tokenize(text)
    if not q_tokens:
        return []

    df = idx['df']
    n_docs = idx['n_docs']
    docs = idx['docs']

    q_tf: Dict[str, int] = {}
    for t in q_tokens:
        q_tf[t] = q_tf.get(t, 0) + 1

    # Detect query type for smart boosting
    query_to_analyze = original_query if original_query else text
    text_lower = query_to_analyze.lower()

    # Intent detection
    is_faq_query = any(kw in text_lower for kw in [
        'làm sao', 'thế nào', 'cách', 'hướng dẫn', 'quên', 'mất',
        'đăng ký', 'đăng nhập', 'liên hệ', 'hỗ trợ', 'help', 'sao', 'tại sao'
    ])
    is_vip_query = any(kw in text_lower for kw in ['vip', 'giá gói', 'phí', 'bảng giá', 'nâng cấp', 'dịch vụ'])
    is_search_query = any(kw in text_lower for kw in ['tìm', 'phòng', 'thuê', 'nhà', 'trọ', 'căn hộ', 'có phòng'])

    # Extract context from query for metadata matching
    import re
    price_mentioned = bool(re.search(r'\d+\s*(triệu|tr|trieu|vnd)', text_lower))
    area_mentioned = bool(re.search(r'\d+\s*(m2|m²|met)', text_lower))

    # Province detection for location boosting
    province_terms = ['hà nội', 'ha noi', 'hcm', 'tp hcm', 'sài gòn', 'sai gon',
                      'đà nẵng', 'da nang', 'cần thơ', 'can tho', 'hải phòng', 'hai phong']
    mentioned_province = None
    for prov in province_terms:
        if prov in text_lower:
            mentioned_province = prov
            break

    scores: List[tuple[float, Dict[str, Any]]] = []
    for d in docs:
        dl = max(1, d['len'])

        # Base TF-IDF score
        score = 0.0
        for t, qf in q_tf.items():
            if t not in d['tf']:
                continue
            idf = _idf(df, n_docs, t)
            score += (d['tf'][t] / dl) * idf

        if score <= 0:
            continue

        # === INTELLIGENT BOOSTING ===

        # 1. Query type boosting
        if d['kind'] == 'md':
            if is_faq_query and 'FAQ' in d['title'].upper():
                score *= 4.0  # Strong boost for FAQ when user asks "how to"
            elif is_faq_query:
                score *= 1.8
        elif d['kind'] == 'vip':
            if is_vip_query and not is_search_query:
                score *= 3.0  # Boost VIP docs when asking about pricing
        elif d['kind'] == 'post':
            if is_search_query:
                score *= 1.3  # Boost posts for search queries

        # 2. Freshness boost (newer posts rank higher)
        try:
            if d.get('created_at'):
                from datetime import datetime, timezone as tz
                created = datetime.fromisoformat(d['created_at'])
                age_days = (datetime.now(tz.utc) - created).days
                if age_days <= 7:
                    score *= 1.5  # Fresh content
                elif age_days <= 30:
                    score *= 1.2
        except Exception:
            pass

        # 3. Metadata matching boost
        metadata = d.get('metadata') or {}
        if metadata:
            # Price relevance
            if price_mentioned and metadata.get('price'):
                score *= 1.15

            # Area relevance
            if area_mentioned and metadata.get('area'):
                score *= 1.15

            # Location match
            if mentioned_province:
                doc_prov = _normalize(metadata.get('province', ''))
                if mentioned_province.replace(' ', '') in doc_prov.replace(' ', ''):
                    score *= 1.4  # Strong boost for location match

        # 4. Title match bonus (exact words in title = more relevant)
        title_lower = _normalize(d.get('title', ''))
        query_words = set(_tokenize(text_lower))
        title_words = set(_tokenize(title_lower))
        overlap = len(query_words & title_words)
        if overlap > 0:
            title_boost = 1.0 + (overlap * 0.15)  # +15% per matching word
            score *= min(title_boost, 2.0)  # Cap at 2x

        scores.append((score, d))

    scores.sort(key=lambda x: x[0], reverse=True)

    results = []
    for s, d in scores[:k]:
        results.append({
            'id': d['id'],
            'kind': d['kind'],
            'title': d['title'],
            'url': d['url'],
            'snippet': d['text'][:400],
            'score': s,
            'metadata': d.get('metadata', {}),
        })
    return results


def _query_vectors(text: str, k: int = 5) -> List[Dict[str, Any]]:
    """Vector similarity search using embeddings."""
    try:
        from chatbot import embedding_service
        from chatbot.models import VectorDocument
    except ImportError:
        return []

    # Encode query
    q_emb = embedding_service.encode_single(text)
    if q_emb is None:
        return []

    # Get all vectors from DB
    vector_docs = VectorDocument.objects.all()
    if not vector_docs.exists():
        return []

    # Compute cosine similarity
    scores: List[tuple[float, VectorDocument]] = []
    for vd in vector_docs:
        try:
            doc_emb = json.loads(vd.embedding_json)
            sim = _cosine_similarity(q_emb, doc_emb)
            scores.append((sim, vd))
        except Exception:
            continue

    scores.sort(key=lambda x: x[0], reverse=True)

    results = []
    for sim, vd in scores[:k]:
        results.append({
            'id': vd.doc_id,
            'kind': vd.kind,
            'title': vd.title,
            'url': vd.url,
            'snippet': vd.text_snippet,
            'score': sim,
        })
    return results


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)
