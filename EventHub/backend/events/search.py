"""
Semantic search for events using sentence-transformers + pgvector.

Model: all-MiniLM-L6-v2 (22 MB, 384 dims, fast, free)
Embeddings are stored on Event.embedding and updated on save.
"""

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _get_model():
    """Load model once, cache forever (lazy — only on first search)."""
    from sentence_transformers import SentenceTransformer
    logger.info('[Search] Loading embedding model %s', EMBEDDING_MODEL)
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    """Embed a string into a 384-dim vector."""
    model = _get_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def event_text(event) -> str:
    """Build the corpus text for an event."""
    parts = [event.title, event.description or '', event.location or '']
    if event.category:
        parts.append(event.category.name)
    return ' '.join(filter(None, parts))


def index_event(event) -> None:
    """Generate and save embedding for a single event."""
    try:
        text = event_text(event)
        event.embedding = embed_text(text)
        event.save(update_fields=['embedding'])
        logger.debug('[Search] Indexed event %s', event.id)
    except Exception as exc:
        logger.warning('[Search] Failed to index event %s: %s', event.id, exc)


def semantic_search(query: str, limit: int = 20, extra_qs=None, max_distance: float = 0.79):
    """
    Return events ordered by cosine similarity to query.
    Falls back to keyword search if no embeddings exist yet.

    The result is an UNSLICED queryset (top-N picked via id__in) so DRF
    pagination and OrderingFilter can keep working on it — re-ordering a
    sliced queryset raises TypeError.
    """
    from .models import Event
    from pgvector.django import CosineDistance

    qs = extra_qs if extra_qs is not None else Event.objects.filter(
        status='published', embedding__isnull=False
    )

    if not qs.filter(embedding__isnull=False).exists():
        # Fallback: plain title/description keyword search
        return (extra_qs or Event.objects.filter(status='published')).filter(
            title__icontains=query
        )

    query_vec = embed_text(query)
    top_ids = list(
        qs.filter(embedding__isnull=False)
        .annotate(distance=CosineDistance('embedding', query_vec))
        .filter(distance__lte=max_distance)  # drop unrelated matches/gibberish
        .order_by('distance')
        .values_list('id', flat=True)[:limit]
    )
    if not top_ids:
        # Nothing semantically close (e.g. non-English query against an
        # English model) — try plain keyword matching before giving up.
        from django.db.models import Q
        return qs.filter(Q(title__icontains=query) | Q(description__icontains=query))
    return (
        qs.filter(id__in=top_ids)
        .annotate(distance=CosineDistance('embedding', query_vec))
        .order_by('distance')
    )
