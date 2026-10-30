from django.db import models
from django.utils import timezone


class Job(models.Model):
    """A unit of background work (transactional outbox).

    The row is written in the same database transaction as the business
    change that needs it, so a job exists if and only if that change was
    committed. `run_worker` executes due jobs with retries and backoff.
    """

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    kind = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    # Pending: earliest start. Running: lease end — a job whose worker died
    # is picked up again once its lease expires.
    run_after = models.DateTimeField(default=timezone.now)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['run_after', 'id']
        indexes = [models.Index(fields=['status', 'run_after'], name='job_status_run_after_idx')]

    def __str__(self):
        return f'{self.kind} #{self.pk} ({self.status})'
