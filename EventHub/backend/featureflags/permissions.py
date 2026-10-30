from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from .registry import Flag
from .service import is_enabled


def require_flag(flag: Flag) -> type[BasePermission]:
    """A DRF permission class that hides a view while `flag` is off for the
    requesting user: the endpoint answers 404, as if it didn't exist yet.

        permission_classes = [IsAuthenticated, require_flag(Flags.CHECKIN_OFFLINE_SCANNER)]

    List it after the authentication permission, so anonymous callers still
    get 401 and the flag is evaluated with the user's context.
    """

    class FlagEnabled(BasePermission):
        def has_permission(self, request, view):
            if is_enabled(flag, getattr(request, 'user', None)):
                return True
            raise NotFound()

    FlagEnabled.__name__ = FlagEnabled.__qualname__ = f'RequireFlag_{flag.key.replace(".", "_")}'
    return FlagEnabled
