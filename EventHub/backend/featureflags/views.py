from django.utils.cache import patch_cache_control
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.schema import UNAUTHENTICATED

from .schema import FeatureFlagsResponseSerializer
from .service import client_flags


class FeatureFlagsView(APIView):
    """
    The client-visible feature flags, evaluated server-side for the signed-in
    user. The SPA reads this once after login instead of talking to Unleash:
    no Unleash token reaches the browser.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Feature flags for the current user',
        responses={200: FeatureFlagsResponseSerializer, 401: UNAUTHENTICATED},
    )
    def get(self, request):
        response = Response({'flags': client_flags(request.user)})
        # Per-user answer: never stored by shared caches or the browser.
        patch_cache_control(response, private=True, no_store=True)
        return response
