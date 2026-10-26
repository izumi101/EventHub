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

        try:
            # Local dev with explicit STRIPE_MOCK_MODE: simulate a successful payment.
            if settings.STRIPE_MOCK_MODE:
                success_url, _payment = create_mock_checkout_session(registration=registration)
                return Response({
                    'checkout_url': success_url,
                    'session_id': _payment.stripe_checkout_session_id,
                    'mock': True,
                })

            checkout_session, _payment = create_checkout_session(registration=registration)
            return Response({
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id,
            })
        except ValueError as exc:
            # Not payable any more: paid already, cancelled, hold expired.
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.StripeError as e:
            logger.error('Stripe error creating checkout session: %s', e)
            return Response(
                {'error': 'The payment provider is unavailable. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
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

        if event['type'] in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
            session = event['data']['object']
            metadata = session.get('metadata') or {}
            # Delayed payment methods report "completed" before the money is in.
            if session.get('payment_status', 'paid') != 'paid':
                return Response(status=status.HTTP_200_OK)

            # Errors propagate as a 500 on purpose: Stripe retries the
            # webhook, and both confirmations are idempotent.
            if metadata.get('registration_id'):
                confirm_stripe_checkout_session(session)
            if metadata.get('booking_id'):
                from bookings.payments import confirm_booking_by_session
                confirm_booking_by_session(session)

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
            payment = verify_payment_service(session_id, request.user)
            return Response({
                'status': payment.status,
                'event_title': payment.registration.event.title,
                'amount': str(payment.amount),
                'currency': (payment.currency or 'usd').upper(),
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

        try:
            payment = mark_offline_paid_service(
                registration=registration,
                amount=request.data.get('amount'),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': payment.status, 'amount': str(payment.amount), 'method': payment.method})


class InvoiceView(APIView):
    """Render a printable HTML invoice for a registration.

    Accessible to the ticket owner or the event organizer via the normal
    Authorization header (the SPA fetches it as a blob). Tokens are never
    accepted in the query string: URLs end up in logs, history and Referer.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, registration_id):
        registration = get_object_or_404(
            Registration.objects.select_related('event', 'user', 'ticket_type', 'seat', 'promo_code', 'payment'),
            id=registration_id,
        )
        user = request.user
        if not (registration.user_id == user.id or can_manage_event(registration.event, user)):
            return Response({'error': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)

        from .invoice import invoice_response
        return invoice_response(registration)
