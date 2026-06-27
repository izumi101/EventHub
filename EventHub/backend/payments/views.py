import stripe
import logging
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from events.models import Registration
from .models import Payment
from common.choices import PaymentStatusChoices
from .services import (
    confirm_stripe_checkout_session,
    create_checkout_session,
    create_mock_checkout_session,
    verify_payment as verify_payment_service,
    refund_payment as refund_payment_service,
    mark_offline_paid as mark_offline_paid_service,
)
from common.permissions import can_manage_event

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class CreateCheckoutSessionView(APIView):
    """
    Creates a Stripe Checkout Session for a paid event registration.
    Returns the session ID and the checkout URL to redirect the user to Stripe.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, registration_id):
        registration = get_object_or_404(
            Registration, id=registration_id, user=request.user
        )

        from events.billing import registration_amount
        if registration_amount(registration) <= 0:
            return Response(
                {'error': 'This registration is free, no payment needed'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = getattr(registration, 'payment', None)
        if payment and payment.status == PaymentStatusChoices.COMPLETED:
            return Response(
                {'error': 'Payment already completed'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Local dev without a real Stripe key: simulate a successful payment.
        if settings.STRIPE_MOCK_MODE:
            success_url, _payment = create_mock_checkout_session(registration=registration)
            return Response({
                'checkout_url': success_url,
                'session_id': _payment.stripe_checkout_session_id,
                'mock': True,
            })

        try:
            checkout_session, _payment = create_checkout_session(registration=registration)
            return Response({
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id,
            })

        except stripe.error.StripeError as e:
            logger.error('Stripe error creating checkout session: %s', e)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class StripeWebhookView(APIView):
    """
    Listens to Stripe webhooks.
    When checkout.session.completed event is received, marks the corresponding payment as completed and confirms the registration.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.warning('Invalid Stripe webhook signature or payload: %s', e)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            metadata = session.get('metadata', {})

            # Single-seat registration payment
            registration_id = metadata.get('registration_id')
            if registration_id:
                try:
                    confirm_stripe_checkout_session(session)
                    logger.info('Payment completed for registration %s', registration_id)
                except Payment.DoesNotExist:
                    logger.warning('Payment object not found for session %s', session['id'])

            # Group booking payment
            booking_id = metadata.get('booking_id')
            if booking_id:
                try:
                    from bookings.payments import confirm_booking_by_session
                    confirm_booking_by_session(session['id'])
                    logger.info('Booking %s confirmed via webhook', booking_id)
                except Exception as exc:
                    logger.warning('Booking confirm failed for %s: %s', booking_id, exc)

        return Response(status=status.HTTP_200_OK)


class VerifyPaymentView(APIView):
    """
    Verifies the payment status of a registration given the checkout session_id.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({'error': 'session_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = verify_payment_service(session_id)
            return Response({
                'status': payment.status,
                'event_title': payment.registration.event.title,
                'amount': str(payment.amount),
            })
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)


class RefundPaymentView(APIView):
    """Organizer refunds a registration's payment (full or partial)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, registration_id):
        registration = get_object_or_404(Registration, id=registration_id)
        if not can_manage_event(registration.event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        payment = getattr(registration, 'payment', None)
        if not payment:
            return Response({'error': 'No payment found for this registration.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            payment = refund_payment_service(
                payment=payment,
                amount=request.data.get('amount'),  # None = full
                reason=request.data.get('reason', ''),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': payment.status,
            'refunded_amount': str(payment.refunded_amount),
            'net_amount': str(payment.net_amount),
        })


class MarkOfflinePaidView(APIView):
    """Organizer manually marks a registration as paid (cash / bank transfer)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, registration_id):
        registration = get_object_or_404(Registration, id=registration_id)
        if not can_manage_event(registration.event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        payment = mark_offline_paid_service(
            registration=registration,
            amount=request.data.get('amount'),
        )
        return Response({'status': payment.status, 'amount': str(payment.amount), 'method': payment.method})


class InvoiceView(APIView):
    """Render a printable HTML invoice for a registration.

    Accessible to the ticket owner or the event organizer. Auth comes via the
    `token` query param (so a plain browser tab/window can open it) or a normal
    Authorization header.
    """
    permission_classes = [AllowAny]

    def get(self, request, registration_id):
        registration = get_object_or_404(
            Registration.objects.select_related('event', 'user', 'ticket_type', 'seat', 'promo_code', 'payment'),
            id=registration_id,
        )

        user = request.user if request.user.is_authenticated else None
        if user is None:
            user = self._user_from_token(request)

        if user is None:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        is_owner = registration.user_id == user.id
        is_manager = can_manage_event(registration.event, user)
        if not (is_owner or is_manager):
            return Response({'error': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)

        from .invoice import invoice_response
        return invoice_response(registration)

    @staticmethod
    def _user_from_token(request):
        token = request.query_params.get('token')
        if not token:
            return None
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth.models import User
            access = AccessToken(token)
            return User.objects.filter(id=access['user_id']).first()
        except Exception:
            return None
