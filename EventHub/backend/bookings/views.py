import logging

import stripe
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from events.models import Event

from .models import Booking
from .payments import create_booking_checkout
from .serializers import (
    BookingSerializer,
    BookingCreateSerializer,
    ClaimSeatSerializer,
)
from .services import create_booking, claim_seat, cancel_booking, refund_booking

logger = logging.getLogger(__name__)


def _ctx(request, **extra):
    return {'viewer': request.user, **extra}


class BookingCreateView(APIView):
    """POST /api/bookings/  — hold a group of seats."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = BookingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        event = get_object_or_404(Event, pk=ser.validated_data['event'])
        try:
            booking = create_booking(
                user=request.user,
                event=event,
                seat_ids=ser.validated_data['seat_ids'],
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking, context=_ctx(request)).data, status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    """GET /api/bookings/{id}/  — owner views their booking."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, owner=request.user)
        return Response(BookingSerializer(booking, context=_ctx(request)).data)


class BookingCheckoutView(APIView):
    """POST /api/bookings/{id}/checkout/  — pay for the whole group."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, owner=request.user)
        try:
            result = create_booking_checkout(booking)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class BookingCancelView(APIView):
    """POST /api/bookings/{id}/cancel/  — release the held seats."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, owner=request.user)
        try:
            cancel_booking(booking)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': 'cancelled'})


class SharedBookingView(APIView):
    """GET /api/bookings/shared/{token}/  — friends open the invite link."""
    permission_classes = [AllowAny]

    def get(self, request, token):
        booking = get_object_or_404(Booking, share_token=token)
        return Response(BookingSerializer(booking, context=_ctx(request, via_share_link=True)).data)


class ClaimSeatView(APIView):
    """POST /api/bookings/shared/{token}/claim/  — claim one seat."""
    permission_classes = [AllowAny]
    throttle_scope = 'claim'

    def post(self, request, token):
        booking = get_object_or_404(Booking, share_token=token)
        ser = ClaimSeatSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            claim_seat(
                booking=booking,
                seat_id=ser.validated_data['seat_id'],
                attendee_name=ser.validated_data['name'],
                user=request.user if request.user.is_authenticated else None,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        booking.refresh_from_db()
        return Response(BookingSerializer(booking, context=_ctx(request, via_share_link=True)).data)


class VerifyBookingView(APIView):
    """GET /api/bookings/verify/?session_id=…  — success page confirms a paid
    booking even when the Stripe webhook is not forwarded (local dev)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings

        session_id = request.query_params.get('session_id', '')
        if not session_id:
            return Response({'error': 'session_id required'}, status=status.HTTP_400_BAD_REQUEST)

        booking = get_object_or_404(Booking, stripe_session_id=session_id, owner=request.user)

        if booking.status == Booking.Status.HOLDING and not settings.STRIPE_MOCK_MODE:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            from payments.services import stripe_to_dict
            try:
                session = stripe_to_dict(stripe.checkout.Session.retrieve(session_id))
            except stripe.error.StripeError as exc:
                logger.warning('Could not retrieve Stripe session %s: %s', session_id, exc)
            else:
                if session.get('payment_status') == 'paid':
                    from .payments import confirm_booking_by_session
                    confirm_booking_by_session(session)
                    booking.refresh_from_db()

        return Response(BookingSerializer(booking, context=_ctx(request)).data)


class MyBookingsView(APIView):
    """GET /api/bookings/  — list the user's confirmed/holding bookings."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bookings = (
            Booking.objects
            .filter(owner=request.user)
            .exclude(status__in=[Booking.Status.EXPIRED, Booking.Status.CANCELLED])
            .select_related('event', 'owner')
        )
        return Response(BookingSerializer(bookings, many=True, context=_ctx(request)).data)


class EventBookingsView(APIView):
    """GET /api/bookings/event/{event_id}/  — the event team lists group bookings."""
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        from common.permissions import can_manage_event
        event = get_object_or_404(Event, pk=event_id)
        if not can_manage_event(event, request.user):
            return Response({'error': 'You do not manage this event.'}, status=status.HTTP_403_FORBIDDEN)
        bookings = (
            Booking.objects.filter(event=event)
            .exclude(status__in=[Booking.Status.CANCELLED, Booking.Status.EXPIRED])
            .select_related('event', 'owner')
        )
        # The organizer isn't the owner: ticket UUIDs and share links stay hidden.
        return Response(BookingSerializer(bookings, many=True, context=_ctx(request)).data)


class BookingRefundView(APIView):
    """POST /api/bookings/{id}/refund/  — the event team refunds one paid group booking."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        try:
            booking = refund_booking(booking, actor=request.user,
                                     reason=str(request.data.get('reason', '') or ''))
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.StripeError as exc:
            logger.error('Stripe refund failed for booking %s: %s', pk, exc)
            return Response({'error': 'The payment provider refused the refund. Try again later.'},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response(BookingSerializer(booking, context=_ctx(request)).data)
