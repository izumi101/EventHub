"""Enqueue and execute background jobs.

    enqueue('send_email', {...})       # inside the business transaction
    run_due_jobs()                     # in the worker (manage.py run_worker)

Delivery is at-least-once: a handler may run again if the worker dies after
the side effect but before recording success, so handlers must tolerate it.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import Job

logger = logging.getLogger(__name__)

# kind → handler. An allow-list: job rows only ever name one of these.
HANDLERS = {
    'send_email': 'jobs.handlers.send_email',
    'deliver_webhook': 'events.webhooks.deliver_job',
    'index_event': 'events.search.index_event_job',
}

LEASE = timedelta(minutes=5)
MAX_BACKOFF = timedelta(hours=1)


class PermanentJobError(Exception):
    """Raise from a handler when retrying can't help (e.g. URL blocked)."""


def enqueue(kind: str, payload: dict, *, max_attempts: int = 5, delay: timedelta = None) -> Job:
    if kind not in HANDLERS:
        raise ValueError(f'Unknown job kind: {kind}')
    job = Job.objects.create(
        kind=kind,
        payload=payload,
        max_attempts=max_attempts,
        run_after=timezone.now() + (delay or timedelta(0)),
    )
    if getattr(settings, 'JOBS_RUN_INLINE', False):
        # Local convenience without a worker: run right after commit.
        transaction.on_commit(lambda: run_job(job.pk))
    return job


def backoff(attempt: int) -> timedelta:
    """30 s, 1 min, 2 min, 4 min … capped at an hour."""
    return min(timedelta(seconds=30 * 2 ** (attempt - 1)), MAX_BACKOFF)


def _claim(limit: int) -> list:
    """Lease up to `limit` due jobs. Short transaction; SKIP LOCKED lets
    several workers run side by side without taking the same job."""
    now = timezone.now()
    # A job whose lease ran out while it was running took its worker down
    # with it (OOM, kill). Once it has used up its attempts, stop handing it
    # out — otherwise a job that crashes the worker would cycle forever.
    Job.objects.filter(
        status=Job.STATUS_RUNNING,
        run_after__lte=now,
        attempts__gte=F('max_attempts'),
    ).update(status=Job.STATUS_FAILED, last_error='The worker stopped while running this job.')
    with transaction.atomic():
        jobs = list(
            Job.objects.select_for_update(skip_locked=True)
            .filter(Q(status=Job.STATUS_PENDING) | Q(status=Job.STATUS_RUNNING), run_after__lte=now)
            .order_by('run_after', 'id')[:limit]
        )
        if jobs:
            Job.objects.filter(pk__in=[j.pk for j in jobs]).update(
                status=Job.STATUS_RUNNING,
                run_after=now + LEASE,
                attempts=F('attempts') + 1,
            )
    for job in jobs:
        job.attempts += 1
    return jobs


def _execute(job: Job) -> bool:
    try:
        import_string(HANDLERS[job.kind])(**job.payload)
    except Exception as exc:
        permanent = isinstance(exc, PermanentJobError) or job.attempts >= job.max_attempts
        Job.objects.filter(pk=job.pk).update(
            status=Job.STATUS_FAILED if permanent else Job.STATUS_PENDING,
            run_after=timezone.now() + backoff(job.attempts),
            last_error=f'{type(exc).__name__}: {exc}'[:2000],
        )
        log = logger.error if permanent else logger.warning
        log(
            'Job %s (%s) attempt %s/%s failed%s: %s',
            job.pk,
            job.kind,
            job.attempts,
            job.max_attempts,
            ' permanently' if permanent else '',
            exc,
        )
        return False
    Job.objects.filter(pk=job.pk).update(status=Job.STATUS_DONE, last_error='')
    return True


def run_due_jobs(limit: int = 50) -> int:
    """Run every job that is due now (one batch). Returns how many ran."""
    jobs = _claim(limit)
    for job in jobs:
        _execute(job)
    return len(jobs)


def run_job(job_id: int) -> None:
    """Run one specific job now if it is still pending (inline mode)."""
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(
                pk=job_id,
                status=Job.STATUS_PENDING,
            )
            .first()
        )
        if job is None:
            return
        Job.objects.filter(pk=job.pk).update(
            status=Job.STATUS_RUNNING,
            run_after=timezone.now() + LEASE,
            attempts=F('attempts') + 1,
        )
    job.attempts += 1
    _execute(job)


def purge_finished(older_than: timedelta = timedelta(days=7)) -> int:
    cutoff = timezone.now() - older_than
    deleted, _ = Job.objects.filter(status=Job.STATUS_DONE, updated_at__lt=cutoff).delete()
    return deleted
