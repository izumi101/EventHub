"""Platform-wide stats for the admin dashboard."""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.choices import EventStatusChoices, RegistrationStatusChoices

from ..models import Event, Registration
from ..serializers import EventListSerializer


class AdminDashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth.models import User as DjangoUser
        from django.db.models import Count, Sum
        from payments.models import Payment
        from common.choices import PaymentStatusChoices

        if not request.user.is_superuser:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        total_users = DjangoUser.objects.filter(is_active=True).count()
        total_events = Event.objects.count()
        published_events = Event.objects.filter(status=EventStatusChoices.PUBLISHED).count()
        total_registrations = Registration.objects.exclude(status=RegistrationStatusChoices.CANCELLED).count()
        confirmed_registrations = Registration.objects.filter(status=RegistrationStatusChoices.CONFIRMED).count()

        revenue = Payment.objects.filter(
            status=PaymentStatusChoices.COMPLETED
        ).aggregate(total=Sum('amount'))['total'] or 0

        top_events = (
            Event.objects
            .filter(status=EventStatusChoices.PUBLISHED)
            .annotate(reg_count=Count('registrations'))
            .order_by('-reg_count')[:5]
        )

        return Response({
            'total_users': total_users,
            'total_events': total_events,
            'published_events': published_events,
            'total_registrations': total_registrations,
            'confirmed_registrations': confirmed_registrations,
            'total_revenue': str(revenue),
            'top_events': EventListSerializer(top_events, many=True, context={'request': request}).data,
        })
