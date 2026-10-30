"""System checks (`manage.py check`, run on every management command and
server start): broken flag declarations are errors, overdue flags warnings."""

from django.core.checks import Error, Tags, Warning, register
from django.utils import timezone

from .registry import ALL_FLAGS, registry_problems


def overdue_flags(flags=None, today=None):
    flags = ALL_FLAGS if flags is None else flags
    today = today or timezone.localdate()
    return [flag for flag in flags if flag.remove_by < today]


@register(Tags.compatibility)
def check_flag_registry(app_configs=None, **kwargs):
    messages = [
        Error(problem, hint='Fix the declaration in featureflags/registry.py.', id='featureflags.E001')
        for problem in registry_problems()
    ]
    messages += [
        Warning(
            f'Feature flag {flag.key!r} was due for removal on {flag.remove_by.isoformat()} (owner: {flag.owner}).',
            hint='Finish the rollout and delete the flag and the losing code path, or agree on a new date.',
            id='featureflags.W001',
        )
        for flag in overdue_flags()
    ]
    return messages
