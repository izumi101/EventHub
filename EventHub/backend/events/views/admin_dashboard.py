"""Platform-wide stats for the admin dashboard."""

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.choices import EventStatusChoices, RegistrationStatusChoices
from common.schema import ERROR, UNAUTHENTICATED

from .. import schema as api
from ..models import INACTIVE_REGISTRATION_STATUSES, Event, Registration
from ..serializers import EventListSerializer


class AdminDashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: api.AdminDashboardSerializer, 401: UNAUTHENTICATED, 403: ERROR})
    def get(self, request):
        from collections import defaultdict
        from decimal import Decimal

        from django.contrib.auth.models import User as DjangoUser
        from django.db.models import Count, Q, Sum

        from bookings.models import Booking
        from common.choices import PaymentStatusChoices
        from payments.models import Payment

        if not request.user.is_superuser:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        total_users = DjangoUser.objects.filter(is_active=True).count()
        total_events = Event.objects.count()
        published_events = Event.objects.filter(status=EventStatusChoices.PUBLISHED).count()
        total_registrations = Registration.objects.exclude(status=RegistrationStatusChoices.CANCELLED).count()
        confirmed_registrations = Registration.objects.filter(status=RegistrationStatusChoices.CONFIRMED).count()

        # Money is only summed within one currency, net of refunds, and
        # includes paid group bookings (they have no Payment row).
        totals = defaultdict(Decimal)
        for row in (
            Payment.objects.filter(status__in=[PaymentStatusChoices.COMPLETED, PaymentStatusChoices.REFUNDED])
            .values('currency')
            .annotate(gross=Sum('amount'), refunded=Sum('refunded_amount'))
        ):
            totals[(row['currency'] or 'usd').upper()] += row['gross'] - row['refunded']
        for row in (
            Booking.objects.filter(status=Booking.Status.CONFIRMED, amount_paid__isnull=False)
            .values('event__currency')
            .annotate(total=Sum('amount_paid'))
        ):
            totals[(row['event__currency'] or 'USD').upper()] += row['total']
        revenue_by_currency = [
            {'currency': cur, 'amount': str(amount.quantize(Decimal('0.01')))} for cur, amount in sorted(totals.items())
        ]

        top_events = (
            Event.objects.filter(status=EventStatusChoices.PUBLISHED)
            .annotate(
                reg_count=Count(
                    'registrations',
                    filter=~Q(registrations__status__in=INACTIVE_REGISTRATION_STATUSES),
                )
            )
            .order_by('-reg_count')
            .select_related('organizer', 'category')
            .with_capacity()[:5]
        )

        return Response(
            {
                'total_users': total_users,
                'total_events': total_events,
                'published_events': published_events,
                'total_registrations': total_registrations,
                'confirmed_registrations': confirmed_registrations,
                'revenue_by_currency': revenue_by_currency,
                'top_events': EventListSerializer(top_events, many=True, context={'request': request}).data,
            }
        )
