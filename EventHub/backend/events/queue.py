"""
Virtual waiting queue for high-demand events.

Architecture:
  Redis sorted set  key=queue:{event_id}
    member = user_id
    score  = unix timestamp of join (FIFO order)

  Redis hash  key=queue_session:{event_id}:{user_id}
    token = <uuid>
    expires = unix timestamp

When the event exceeds QUEUE_THRESHOLD fill rate, new visitors are
placed in queue. A background task (or lazy drain on seat-map request)
admits N users at a time by issuing them a short-lived access token.
"""

import time
import uuid
import logging

logger = logging.getLogger(__name__)

QUEUE_THRESHOLD = 0.80      # fill rate above which queue activates
TOKEN_TTL_SECONDS = 600     # 10 minutes to complete purchase
DRAIN_BATCH = 5             # users let through per drain tick


def _redis():
    import redis as redis_lib
    from django.conf import settings
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def queue_key(event_id: int) -> str:
    return f'queue:{event_id}'


def session_key(event_id: int, user_id: int) -> str:
    return f'queue_session:{event_id}:{user_id}'


def is_queue_active(event) -> bool:
    """True if fill rate >= threshold and queue has waiters."""
    if event.max_participants == 0:
        return False
    registered = event.registrations.exclude(status__in=['cancelled', 'rejected']).count()
    fill = registered / event.max_participants
    return fill >= QUEUE_THRESHOLD


DRAIN_INTERVAL_SECONDS = 15


def maybe_drain(event_id: int) -> None:
    """Lazily admit the next batch if enough time passed since the last drain.

    There is no background worker — every queue read calls this, so as long as
    waiting users poll their status the line keeps moving (~DRAIN_BATCH per
    DRAIN_INTERVAL_SECONDS).
    """
    try:
        r = _redis()
        gate = f'queue_drain:{event_id}'
        # SET NX EX acts as a distributed "only one drain per interval" lock.
        if r.set(gate, '1', nx=True, ex=DRAIN_INTERVAL_SECONDS):
            drain_queue(event_id)
    except Exception as exc:
        logger.warning('Queue drain failed for event %s: %s', event_id, exc)


def join_queue(event_id: int, user_id: int) -> dict:
    """Add user to queue. Returns position and estimated wait."""
    r = _redis()
    key = queue_key(event_id)
    now = time.time()

    # Only add if not already in queue
    r.zadd(key, {str(user_id): now}, nx=True)
    r.expire(key, 3600)  # queue expires in 1h
    maybe_drain(event_id)

    position = r.zrank(key, str(user_id))
    total = r.zcard(key)
    wait_minutes = max(1, (position or 0) // DRAIN_BATCH * 2)

    return {
        'position': (position or 0) + 1,
        'total': total,
        'wait_minutes': wait_minutes,
        'status': 'queued',
    }


def get_queue_status(event_id: int, user_id: int) -> dict:
    """Current queue status for a user."""
    maybe_drain(event_id)
    r = _redis()
    key = queue_key(event_id)
    sess_key = session_key(event_id, user_id)

    # Check if user has an active token (was admitted)
    token_data = r.hgetall(sess_key)
    if token_data and float(token_data.get('expires', 0)) > time.time():
        return {
            'status': 'admitted',
            'token': token_data['token'],
            'expires_in': int(float(token_data['expires']) - time.time()),
        }

    position = r.zrank(key, str(user_id))
    if position is None:
        return {'status': 'not_in_queue'}

    total = r.zcard(key)
    wait_minutes = max(1, position // DRAIN_BATCH * 2)
    return {
        'position': position + 1,
        'total': total,
        'wait_minutes': wait_minutes,
        'status': 'queued',
    }


def drain_queue(event_id: int, n: int = DRAIN_BATCH) -> list[int]:
    """
    Admit the next N users from queue by issuing access tokens.
    Returns list of admitted user_ids.
    """
    r = _redis()
    key = queue_key(event_id)
    expires = time.time() + TOKEN_TTL_SECONDS

    # Get top N members (lowest score = earliest join)
    members = r.zrange(key, 0, n - 1)
    admitted = []

    for user_id_str in members:
        token = str(uuid.uuid4())
        sess_key = session_key(event_id, int(user_id_str))
        r.hset(sess_key, mapping={'token': token, 'expires': str(expires)})
        r.expire(sess_key, TOKEN_TTL_SECONDS + 60)
        r.zrem(key, user_id_str)
        admitted.append(int(user_id_str))

    return admitted


def validate_queue_token(event_id: int, user_id: int) -> bool:
    """Validate that a user holds a valid admission token."""
    r = _redis()
    sess_key = session_key(event_id, user_id)
    token_data = r.hgetall(sess_key)
    if not token_data:
        return False
    return float(token_data.get('expires', 0)) > time.time()


def leave_queue(event_id: int, user_id: int) -> None:
    """Remove user from queue (on cancel or purchase completion)."""
    r = _redis()
    r.zrem(queue_key(event_id), str(user_id))
    r.delete(session_key(event_id, user_id))
