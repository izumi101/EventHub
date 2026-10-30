"""Response shape of GET /api/v1/feature-flags/, for the OpenAPI schema.

One boolean property per client-visible flag, named by its key, so the
generated TypeScript types know every flag name. Built from the registry;
documentation only (the view returns a plain dict).
"""

from rest_framework import serializers

from .registry import CLIENT_FLAGS

FeatureFlagsSerializer = type(
    'FeatureFlagsSerializer',
    (serializers.Serializer,),
    {
        '__module__': __name__,
        '__doc__': 'Client-visible flags evaluated for the current user: flag key → on/off.',
        **{
            flag.key: serializers.BooleanField(
                help_text=f"{flag.description} Default when Unleash can't answer: {'on' if flag.default else 'off'}."
            )
            for flag in CLIENT_FLAGS
        },
    },
)


class FeatureFlagsResponseSerializer(serializers.Serializer):
    flags = FeatureFlagsSerializer()
