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
from .services import create_booking, claim_seat, cancel_booking, release_expired_bookings


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
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    """GET /api/bookings/{id}/  — owner views their booking."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, owner=request.user)
        release_expired_bookings(booking.event)
        booking.refresh_from_db()
        return Response(BookingSerializer(booking).data)


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
        release_expired_bookings(booking.event)
        booking.refresh_from_db()
        return Response(BookingSerializer(booking).data)


class ClaimSeatView(APIView):
    """POST /api/bookings/shared/{token}/claim/  — claim one seat."""
    permission_classes = [AllowAny]

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
        return Response(BookingSerializer(booking).data)


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

        if booking.status != Booking.Status.CONFIRMED and not settings.STRIPE_MOCK_MODE:
            try:
                import stripe
                stripe.api_key = settings.STRIPE_SECRET_KEY
                session = stripe.checkout.Session.retrieve(session_id)
                if session.get('payment_status') == 'paid':
                    from .payments import confirm_booking_by_session
                    confirm_booking_by_session(session_id)
                    booking.refresh_from_db()
            except Exception:
                pass

        return Response(BookingSerializer(booking).data)


class MyBookingsView(APIView):
    """GET /api/bookings/  — list the user's confirmed/holding bookings."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bookings = (
            Booking.objects
            .filter(owner=request.user)
            .exclude(status__in=[Booking.Status.EXPIRED, Booking.Status.CANCELLED])
            .prefetch_related('seats__seat')
        )
        return Response(BookingSerializer(bookings, many=True).data)
