"""OpenAPI generation tweaks."""

from drf_spectacular.openapi import AutoSchema as SpectacularAutoSchema
from rest_framework import serializers

from .api_versioning import CURRENT_PREFIX


def only_current_version(endpoints):
    """Document /api/v1/ only — the unversioned alias is the same API."""
    return [endpoint for endpoint in endpoints if endpoint[0].startswith(CURRENT_PREFIX)]


class AutoSchema(SpectacularAutoSchema):
    """A model serializer renders every declared field of an instance, so in
    responses all of its fields are present ("required" in OpenAPI terms);
    `required=False` only describes input. Without this, generated clients
    type fields like `description` as possibly missing. (Serializers must not
    drop fields per request — declare a separate serializer instead.)

    Plain `Serializer` shapes keep their own required flags: there, optional
    keys really can be absent."""

    def _map_basic_serializer(self, serializer, direction):
        schema = super()._map_basic_serializer(serializer, direction)
        if direction == 'response' and isinstance(serializer, serializers.ModelSerializer):
            schema['required'] = sorted(schema.get('properties', {}))
        return schema
