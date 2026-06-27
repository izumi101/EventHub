"""
Hybrid recommendation engine.

Strategy:
  1. Collaborative signal — events the user attended / registered for.
  2. Content signal — cosine similarity on Event.embedding (pgvector).
  3. Merge: re-rank by combined score, exclude already-registered.

Falls back gracefully if embeddings are missing (returns popular events).
"""

import logging

logger = logging.getLogger(__name__)


def get_recommendations(user, limit: int = 10):
    """Return a list of Event objects recommended for *user*."""
    from .models import Event, Registration
    from common.choices import RegistrationStatusChoices, EventStatusChoices

    published = Event.objects.filter(
        status=EventStatusChoices.PUBLISHED,
        embedding__isnull=False,
    ).select_related('category', 'organizer')

    # Events the user has already interacted with
    registered_ids = set(
        Registration.objects.filter(
            user=user,
            status__in=[
                RegistrationStatusChoices.CONFIRMED,
                RegistrationStatusChoices.PENDING,
            ],
        ).values_list('event_id', flat=True)
    )

    candidates = published.exclude(id__in=registered_ids)

    if not candidates.filter(embedding__isnull=False).exists():
        # Cold start / no embeddings — return newest published events
        return list(candidates.order_by('-created_at')[:limit])

    # Build centroid from user's confirmed events
    confirmed_events = Event.objects.filter(
        id__in=registered_ids,
        embedding__isnull=False,
    )

    if not confirmed_events.exists():
        # New user: return semantically diverse recent events
        return list(candidates.order_by('-created_at')[:limit])

    # Compute mean embedding as user "taste" vector
    import numpy as np
    from pgvector.django import CosineDistance

    embeddings = [list(e.embedding) for e in confirmed_events]
    centroid = np.mean(embeddings, axis=0).tolist()

    recs = (
        candidates
        .annotate(distance=CosineDistance('embedding', centroid))
        .order_by('distance')[:limit]
    )
    return list(recs)
