"""Feature flags backed by a self-hosted Unleash server (docs/FEATURE_FLAGS.md).

from featureflags import Flags, is_enabled, require_flag
"""

from .permissions import require_flag
from .registry import Flag, Flags
from .service import client_flags, is_enabled, override_flags

__all__ = ['Flag', 'Flags', 'client_flags', 'is_enabled', 'override_flags', 'require_flag']
