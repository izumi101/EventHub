"""Registrations: ticket check-in by UUID and the attendee's own list."""

import uuid as uuid_lib

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema

from common.choices import RegistrationStatusChoices
from common.schema import ERROR, NOT_FOUND, UNAUTHENTICATED

from django.db.models import Prefetch

from .. import schema as api
from ..models import Event, Registration
from ..serializers import RegistrationSerializer
from ..services import check_in_registration


class RegistrationViewSet(viewsets.GenericViewSet):
    queryset = Registration.objects.all()
    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter(
                'uuid',
                OpenApiTypes.UUID,
                OpenApiParameter.PATH,
                description='Ticket code from the QR (single or group-booking seat).',
            )
        ],
        responses={
            200: api.TicketCheckInResultSerializer,
            400: api.TicketRefusedSerializer,
            401: UNAUTHENTICATED,
            403: ERROR,
            404: NOT_FOUND,
        },
    )
    @action(detail=False, methods=['post'], url_path='check-in/(?P<uuid>[^/.]+)')
    def check_in(self, request, uuid=None):
        try:
            uuid = uuid_lib.UUID(str(uuid))
        except ValueError:
            return Response({'error': 'Invalid ticket code.', 'status': 'invalid'}, status=status.HTTP_400_BAD_REQUEST)
        registration = Registration.objects.select_related('event').filter(ticket_uuid=uuid).first()
        if registration is None:
            # Group-booking tickets live in BookingSeat, not Registration.
            return self._check_in_booking_seat(request, uuid)

        try:
            registration, used = check_in_registration(registration=registration, actor=request.user)
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc), 'status': 'invalid'}, status=status.HTTP_400_BAD_REQUEST)

        if used:
            return Response(
                {
                    'message': 'Ticket already checked in!',
                    'status': 'used',
                    'attendee': registration.user.username,
                    'checked_in_at': registration.checked_in_at,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                'message': 'Ticket valid! Welcome to the event.',
                'status': 'success',
                'attendee': registration.user.username,
                'event': registration.event.title,
            },
            status=status.HTTP_200_OK,
        )

    def _check_in_booking_seat(self, request, uuid):
        """Validate a group-booking seat ticket by its UUID."""
        from bookings.models import Booking, BookingSeat
        from common.permissions import can_check_in_event
        from django.utils import timezone as _tz

        seat_ticket = get_object_or_404(
            BookingSeat.objects.select_related('booking__event', 'booking__owner', 'claimed_by', 'seat'),
            ticket_uuid=uuid,
        )
        booking = seat_ticket.booking
        if not can_check_in_event(booking.event, request.user):
            return Response(
                {'error': 'You do not have check-in rights for this event.'}, status=status.HTTP_403_FORBIDDEN
            )
        if booking.status != Booking.Status.CONFIRMED:
            return Response(
                {'error': 'Ticket is NOT paid — the group booking was never completed.', 'status': 'invalid'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendee = (
            seat_ticket.attendee_name
            or (seat_ticket.claimed_by.username if seat_ticket.claimed_by_id else '')
            or booking.owner.username
        )
        # Conditional UPDATE: of two simultaneous scans only one flips the flag.
        with transaction.atomic():
            admitted = BookingSeat.objects.filter(pk=seat_ticket.pk, is_checked_in=False).update(
                is_checked_in=True,
                checked_in_at=_tz.now(),
            )
        if not admitted:
            seat_ticket.refresh_from_db(fields=['checked_in_at'])
            return Response(
                {
                    'message': 'Ticket already checked in!',
                    'status': 'used',
                    'attendee': attendee,
                    'checked_in_at': seat_ticket.checked_in_at,
                }
            )

        return Response(
            {
                'message': f'Ticket valid! Group seat {seat_ticket.seat.row}-{seat_ticket.seat.col}.',
                'status': 'success',
                'attendee': attendee,
                'event': booking.event.title,
            }
        )


class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (
            Registration.objects.filter(user=self.request.user)
            .exclude(status=RegistrationStatusChoices.CANCELLED)
            .select_related(
                'user',
                'seat',
                'seat__seat_map',
                'payment',
                'promo_code',
                'ticket_type',
                'refund_request',
            )
            .prefetch_related(
                # Events come with their capacity counts annotated, so the
                # nested event card doesn't run extra queries per ticket.
                Prefetch('event', queryset=Event.objects.select_related('organizer', 'category').with_capacity()),
                'answers__question',
            )
        )
        # ?event=<id> lets the event page fetch exactly its own registration
        # instead of paging through everything the user ever booked.
        event_id = self.request.query_params.get('event')
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs
