import logging

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import can_manage_event
from common.schema import ERROR, NOT_FOUND, UNAUTHENTICATED
from events.models import Registration
from mfa.stepup import require_recent_mfa

from . import schema
from .models import Payment
from .providers.base import PaymentProviderError
from .services import (
    confirm_stripe_checkout_session,
    create_checkout_session,
    create_mock_checkout_session,
    stripe_to_dict,
)
from .services import (
    mark_offline_paid as mark_offline_paid_service,
)
from .services import (
    refund_payment as refund_payment_service,
)
from .services import (
    verify_payment as verify_payment_service,
)

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class CreateCheckoutSessionView(APIView):
    """
    Opens a payment page for a paid event registration and returns its URL.

    KZT events go to Freedom Pay when it is enabled (the answer also carries
    a QR code of the payment page); every other currency keeps the Stripe
    path (real, or simulated with PAYMENTS_MOCK_MODE).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: schema.CheckoutSessionResponseSerializer,
            400: ERROR,
            401: UNAUTHENTICATED,
            404: NOT_FOUND,
            502: ERROR,
        },
    )
    def post(self, request, registration_id):
        registration = get_object_or_404(
            Registration.objects.select_related('event'), id=registration_id, user=request.user
        )

        from events.billing import registration_amount

        if registration_amount(registration) <= 0:
            return Response(
                {'error': 'This registration is free, no payment needed'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from . import freedompay_flow

        try:
            if freedompay_flow.provider_for(registration) == freedompay_flow.PROVIDER:
                checkout = freedompay_flow.start_checkout(registration)
                return Response(
                    {
                        'checkout_url': checkout.result.redirect_url,
                        'session_id': checkout.result.session_id,
                        'provider': freedompay_flow.PROVIDER,
                        'payment_id': checkout.payment.pk,
                        'qr_code': checkout.qr_data_url,
                        'amount': str(checkout.payment.amount),
                        'currency': checkout.payment.currency.upper(),
                    }
                )

            # Local dev with explicit STRIPE_MOCK_MODE: simulate a successful payment.
            if settings.STRIPE_MOCK_MODE:
                success_url, _payment = create_mock_checkout_session(registration=registration)
                return Response(
                    {
                        'checkout_url': success_url,
                        'session_id': _payment.stripe_checkout_session_id,
                        'mock': True,
                        'provider': 'mock',
                        'payment_id': _payment.pk,
                        'qr_code': None,
                        'amount': str(_payment.amount),
                        'currency': _payment.currency.upper(),
                    }
                )

            checkout_session, _payment = create_checkout_session(registration=registration)
            return Response(
                {
                    'checkout_url': checkout_session.url,
                    'session_id': checkout_session.id,
                    'provider': 'stripe',
                    'payment_id': _payment.pk,
                    'qr_code': None,
                    'amount': str(_payment.amount),
                    'currency': _payment.currency.upper(),
                }
            )
        except ValueError as exc:
            # Not payable any more: paid already, cancelled, hold expired.
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PaymentProviderError as exc:
            logger.error('Payment provider error creating checkout: %s', exc)
            return Response(
                {'error': 'The payment provider is unavailable. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except stripe.error.StripeError as e:
            logger.error('Stripe error creating checkout session: %s', e)
            return Response(
                {'error': 'The payment provider is unavailable. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class StripeWebhookView(APIView):
    """
    Listens to Stripe webhooks. On checkout.session.completed it marks the
    corresponding payment as completed and confirms the registration.
    """

    permission_classes = [AllowAny]
    # Signed by Stripe; bursts from Stripe's few IPs must not hit the
    # anonymous rate limit (a 429 just delays every confirmation).
    throttle_classes = []

    @extend_schema(exclude=True)  # called by Stripe, not by API clients
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.warning('Invalid Stripe webhook signature or payload: %s', e)
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event['type'] in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
            session = stripe_to_dict(event['data']['object'])
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'session_id',
                OpenApiTypes.STR,
                required=True,
                description='Payment provider session id from the success redirect.',
            )
        ],
        responses={200: schema.PaymentVerificationSerializer, 400: ERROR, 401: UNAUTHENTICATED, 404: ERROR},
    )
    def get(self, request):
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({'error': 'session_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = verify_payment_service(session_id, request.user)
            return Response(
                {
                    'status': payment.status,
                    'event_title': payment.registration.event.title,
                    'amount': str(payment.amount),
                    'currency': (payment.currency or 'usd').upper(),
                }
            )
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)


class RefundPaymentView(APIView):
    """Organizer refunds a registration's payment (full or partial). Needs a
    recent second factor (step-up)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=schema.RefundRequestSerializer,
        responses={
            200: schema.RefundResultSerializer,
            400: ERROR,
            401: UNAUTHENTICATED,
            403: OpenApiResponse(ERROR.response, description='Refused; `code` mfa_step_up_required asks for 2FA.'),
            404: ERROR,
        },
    )
    def post(self, request, registration_id):
        registration = get_object_or_404(Registration, id=registration_id)
        if not can_manage_event(registration.event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        require_recent_mfa(request)

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

        return Response(
            {
                'status': payment.status,
                'refunded_amount': str(payment.refunded_amount),
                'net_amount': str(payment.net_amount),
            }
        )


class MarkOfflinePaidView(APIView):
    """Organizer manually marks a registration as paid (cash / bank transfer)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=schema.OfflinePaymentRequestSerializer,
        responses={
            200: schema.OfflinePaymentResultSerializer,
            400: ERROR,
            401: UNAUTHENTICATED,
            403: ERROR,
            404: NOT_FOUND,
        },
    )
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

    @extend_schema(
        responses={
            (200, 'text/html'): OpenApiResponse(OpenApiTypes.STR, description='Printable HTML invoice.'),
            401: UNAUTHENTICATED,
            403: ERROR,
            404: NOT_FOUND,
        }
    )
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


class PaymentStatusView(APIView):
    """The buyer's payment, provider-neutral, for the success page and the QR
    dialog to poll: a single ticket's or a group booking's. A Freedom Pay
    payment that is still pending after a few seconds is re-checked with
    the gateway (rate-limited)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: schema.PaymentStatusResponseSerializer, 401: UNAUTHENTICATED, 404: NOT_FOUND},
    )
    def get(self, request, payment_id):
        from django.db.models import Q

        # Owner only: anybody else gets the same 404 as a missing payment.
        payment = get_object_or_404(
            Payment.objects.select_related('registration__event', 'booking__event'),
            Q(registration__user=request.user) | Q(booking__owner=request.user),
            pk=payment_id,
        )
        from .freedompay_flow import refresh_status

        payment = refresh_status(payment)
        registration, booking = payment.registration, payment.booking
        target = registration or booking
        target.refresh_from_db(fields=['status'])
        return Response(
            {
                'payment_id': payment.pk,
                'provider': payment.provider
                or ('mock' if payment.stripe_checkout_session_id.startswith('mock_') else 'stripe'),
                'status': payment.status,
                'registration_id': registration.pk if registration else None,
                'registration_status': registration.status if registration else None,
                'booking_id': booking.pk if booking else None,
                'booking_status': booking.status if booking else None,
                'event_id': target.event_id,
                'event_title': target.event.title,
                'amount': str(payment.amount),
                'currency': (payment.currency or 'usd').upper(),
            }
        )


@method_decorator(csrf_exempt, name='dispatch')
class FreedomPayCallbackView(View):
    """Freedom Pay Result notifications (server to server).

    Public and without CSRF (the gateway has no session); authenticity is
    the `pg_sig` signature plus a `get_status3.php` confirmation before a
    ticket is issued. Every answer is the signed XML the gateway expects;
    a notification we cannot authenticate is answered `error` with HTTP 400
    and changes nothing.
    """

    http_method_names = ['post']

    def post(self, request):
        from .freedompay_flow import PaymentNotConfirmed, handle_notification
        from .freedompay_flow import provider as freedompay_provider
        from .providers.base import InvalidCallback
        from .providers.freedompay import MAX_CALLBACK_BYTES

        gateway = freedompay_provider()
        try:
            declared = int(request.META.get('CONTENT_LENGTH') or 0)
        except ValueError:
            declared = 0
        if declared > MAX_CALLBACK_BYTES:
            return HttpResponse(status=413)
        try:
            result = gateway.handle_callback(request)
        except InvalidCallback as exc:
            logger.warning('Rejected Freedom Pay notification: %s', exc)
            if exc.code == 'too_large':
                return HttpResponse(status=413)
            return gateway.invalid_callback_response(request, 'Invalid notification')
        try:
            outcome = handle_notification(gateway, result)
        except PaymentNotConfirmed as exc:
            # Not applied: answering `error` makes the gateway retry later.
            logger.warning('Freedom Pay payment %s not confirmed yet: %s', result.provider_payment_id, exc)
            return gateway.callback_response(result, 'error')
        return gateway.callback_response(result, outcome)
