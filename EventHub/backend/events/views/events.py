"""Event catalog: categories, the main Event CRUD/actions, listings."""

import logging

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import generics, viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import (
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
    IsAdminUser,
    AllowAny,
)
from rest_framework.response import Response

from common.choices import EventStatusChoices, RegistrationStatusChoices
from common.permissions import can_manage_event

from ..analytics import event_analytics
from ..exports import attendees_csv_response
from ..messaging import broadcast_to_attendees
from ..models import Category, Event, EventSeat, SeatMap, TicketType
from ..pricing import get_dynamic_price
from ..promo import quote, PromoError
from ..queue import get_queue_status, is_queue_active, join_queue
from ..seat_pricing import seat_price
from ..serializers import (
    CategorySerializer,
    EventCreateSerializer,
    EventListSerializer,
    RegistrationSerializer,
    SeatMapSerializer,
)
from ..services import (
    approve_event as approve_event_service,
    attendee_cancel,
    cancel_event as cancel_event_service,
    clone_event,
    mark_completed_if_past,
    register_for_event as register_for_event_service,
    reject_event as reject_event_service,
    release_expired_seat_holds,
    request_refund as request_refund_service,
    submit_event,
)
from ..waitlist import join_waitlist, leave_waitlist, position, promote_waitlist
from .base import IsOrganizerOrReadOnly, event_queryset_for_user, restrict_status_list

logger = logging.getLogger(__name__)


class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminUser()]
        return [AllowAny()]


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.filter(status=EventStatusChoices.PUBLISHED)
    permission_classes = [IsAuthenticatedOrReadOnly, IsOrganizerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'description', 'location']
    ordering_fields = ['date', 'price', 'created_at']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return EventCreateSerializer
        return EventListSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = event_queryset_for_user(user)
        is_detail = self.action not in ['list']
        status_param = self.request.query_params.get('status')
        if is_detail:
            if not user.is_authenticated:
                queryset = queryset.filter(status=EventStatusChoices.PUBLISHED)
            else:
                # Ticket holders keep access to events that left the public
                # list (cancelled / completed) — their tickets link here.
                from django.db.models import Q
                queryset = (
                    Event.objects
                    .select_related('organizer', 'category')
                    .prefetch_related('registrations')
                    .filter(
                        Q(organizer=user)
                        | Q(status__in=[EventStatusChoices.PUBLISHED, EventStatusChoices.CANCELLED, EventStatusChoices.COMPLETED])
                        | Q(registrations__user=user)
                    ).distinct()
                    if not user.is_superuser else queryset
                )
        else:
            if not status_param:
                status_param = EventStatusChoices.PUBLISHED
            queryset = restrict_status_list(queryset, user, status_param)

        # Hide events that already happened unless explicitly requested.
        if not is_detail and self.request.query_params.get('upcoming') == 'true':
            queryset = queryset.filter(date__gte=timezone.now())

        category = self.request.query_params.get('category')
        is_free = self.request.query_params.get('is_free')
        is_online = self.request.query_params.get('is_online')
        location = self.request.query_params.get('location')

        if category:
            queryset = queryset.filter(category_id=category)
        if is_free == 'true':
            queryset = queryset.filter(price=0)
        if is_online == 'true':
            queryset = queryset.filter(is_online=True)
        if location:
            queryset = queryset.filter(location__icontains=location)

        # Semantic search — overrides keyword search when ?q= is provided
        semantic_q = self.request.query_params.get('q')
        if semantic_q:
            try:
                from ..search import semantic_search
                queryset = semantic_search(semantic_q, limit=40, extra_qs=queryset)
            except Exception:
                # Fallback to keyword if embeddings not ready
                from django.db.models import Q
                queryset = queryset.filter(
                    Q(title__icontains=semantic_q) |
                    Q(description__icontains=semantic_q)
                )

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        profile_role = getattr(getattr(user, 'profile', None), 'role', '')
        if not (user.is_staff or user.is_superuser or profile_role == 'organizer'):
            raise PermissionDenied(
                'Only organizer accounts can create events. '
                'Ask an administrator to create an organizer account for you.'
            )
        event = serializer.save()
        # Index new event asynchronously (fire-and-forget in same process for now)
        try:
            from ..search import index_event
            import threading
            threading.Thread(target=index_event, args=(event,), daemon=True).start()
        except Exception:
            pass

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Lazy lifecycle: a published event whose end has passed becomes
        # "completed" the first time anyone opens it.
        mark_completed_if_past(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    # Custom action: get registrations for an event
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def registrations(self, request, pk=None):
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        registrations = event.registrations.all()
        serializer = RegistrationSerializer(registrations, many=True)
        return Response(serializer.data)

    # Custom action: get stats for an event dashboard
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def stats(self, request, pk=None):
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        total_regs = event.registrations.filter(status=RegistrationStatusChoices.CONFIRMED).count()
        checked_in = event.registrations.filter(is_checked_in=True).count()

        return Response({
            'total_registrations': total_regs,
            'checked_in': checked_in,
            'remaining': total_regs - checked_in,
            'check_in_rate': round((checked_in / total_regs * 100), 2) if total_regs > 0 else 0
        })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        if not request.user.is_superuser:
            return Response({'error': 'Only admins can approve events'}, status=status.HTTP_403_FORBIDDEN)
        event = self.get_object()
        approve_event_service(event)
        return Response({'message': 'Event approved and published', 'status': EventStatusChoices.PUBLISHED})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def reject(self, request, pk=None):
        if not request.user.is_superuser:
            return Response({'error': 'Only admins can reject events'}, status=status.HTTP_403_FORBIDDEN)
        event = self.get_object()
        reject_event_service(event)
        return Response({'message': 'Event rejected', 'status': EventStatusChoices.REJECTED})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def register(self, request, pk=None):
        event = self.get_object()

        try:
            seat_id = request.data.get('seat_id')
            registration = register_for_event_service(
                user=request.user,
                event=event,
                notes=request.data.get('notes', ''),
                seat_id=seat_id,
                promo_code=request.data.get('promo_code', ''),
                answers=request.data.get('answers') or {},
                ticket_type_id=request.data.get('ticket_type_id'),
                donation_amount=request.data.get('donation_amount'),
                affiliate_code=request.data.get('affiliate_code', ''),
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RegistrationSerializer(registration)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel(self, request, pk=None):
        event = self.get_object()
        try:
            attendee_cancel(user=request.user, event=event)
        except Http404:
            return Response({'error': 'Registration not found'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Registration cancelled'})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='request-refund')
    def request_refund(self, request, pk=None):
        """Attendee submits a refund request for the organizer to review."""
        event = self.get_object()
        try:
            req = request_refund_service(
                user=request.user, event=event,
                reason=request.data.get('reason', ''),
            )
        except Http404:
            return Response({'error': 'Registration not found'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Refund request submitted.', 'status': req.status}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def pricing(self, request, pk=None):
        """Dynamic pricing info for an event."""
        event = self.get_object()
        return Response(get_dynamic_price(event))

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        """Send a draft (e.g. a clone) to admin review."""
        event = self.get_object()
        try:
            submit_event(event=event, actor=request.user)
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Event submitted for review.', 'status': event.status})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='cancel-event')
    def cancel_event(self, request, pk=None):
        """Organizer cancels the event: refunds paid tickets, notifies attendees."""
        event = self.get_object()
        try:
            result = cancel_event_service(event=event, actor=request.user)
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Event cancelled.', 'status': event.status, **result})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='seat-map/create')
    def create_seat_map(self, request, pk=None):
        """Organizer generates a seat map (rows × cols with optional VIP/premium rows)."""
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        if SeatMap.objects.filter(event=event).exists():
            return Response({'error': 'This event already has a seat map.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rows = max(1, min(int(request.data.get('rows', 6)), 26))
            cols = max(1, min(int(request.data.get('cols', 8)), 30))
            vip_rows = max(0, min(int(request.data.get('vip_rows', 0)), rows))
            premium_rows = max(0, min(int(request.data.get('premium_rows', 0)), rows - vip_rows))
        except (TypeError, ValueError):
            return Response({'error': 'rows/cols must be numbers.'}, status=status.HTTP_400_BAD_REQUEST)

        zones = {
            'premium': list(range(1, premium_rows + 1)),
            'vip': list(range(premium_rows + 1, premium_rows + vip_rows + 1)),
            'standard': list(range(premium_rows + vip_rows + 1, rows + 1)),
        }
        with transaction.atomic():
            seat_map = SeatMap.objects.create(
                event=event, rows=rows, cols=cols,
                layout={'price_zones': {k: v for k, v in zones.items() if v}},
            )
            EventSeat.objects.bulk_create([
                EventSeat(
                    seat_map=seat_map, row=r, col=c,
                    price_zone=(
                        'premium' if r in zones['premium']
                        else 'vip' if r in zones['vip']
                        else 'standard'
                    ),
                )
                for r in range(1, rows + 1) for c in range(1, cols + 1)
            ])
            # Keep the advertised capacity consistent with the physical seats.
            if request.data.get('sync_capacity', True):
                event.max_participants = rows * cols
                event.save(update_fields=['max_participants'])

        serializer = SeatMapSerializer(seat_map)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def queue_join(self, request, pk=None):
        """Join the waiting queue for a high-demand event."""
        event = self.get_object()
        if not is_queue_active(event):
            return Response({'status': 'not_needed', 'message': 'Queue not active for this event.'})
        result = join_queue(event.id, request.user.id)
        return Response(result)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def queue_status(self, request, pk=None):
        """Check queue position / admission status."""
        event = self.get_object()
        if not is_queue_active(event):
            return Response({'status': 'not_needed'})
        result = get_queue_status(event.id, request.user.id)
        return Response(result)

    @action(detail=True, methods=['get', 'post', 'delete'], permission_classes=[IsAuthenticated])
    def waitlist(self, request, pk=None):
        """GET = my status · POST = join · DELETE = leave the waitlist."""
        event = self.get_object()

        if request.method == 'POST':
            # The waitlist leads to a ticket — same attendee-only rule as buying.
            from ..services import ensure_attendee_can_buy
            try:
                ensure_attendee_can_buy(request.user)
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            # Only meaningful when the event is actually full.
            release_expired_seat_holds(event)
            if event.available_spots > 0:
                return Response({'status': 'spots_available',
                                 'message': 'Spots are available — just register directly.'})
            join_waitlist(user=request.user, event=event)
            promote_waitlist(event)  # in case a spot is already free for them
            return Response(position(user=request.user, event=event), status=status.HTTP_201_CREATED)

        if request.method == 'DELETE':
            leave_waitlist(user=request.user, event=event)
            return Response({'status': 'left'})

        # GET
        release_expired_seat_holds(event)
        promote_waitlist(event)
        pos = position(user=request.user, event=event)
        return Response(pos or {'status': 'not_joined'})

    @action(detail=True, methods=['post'], permission_classes=[AllowAny], url_path='validate-promo')
    def validate_promo(self, request, pk=None):
        """Public: check a promo code and return the discounted price.

        Accepts optional `ticket_type_id` / `seat_id` so the quote is computed
        from the price the attendee actually selected.
        """
        event = self.get_object()
        code = request.data.get('code', '')

        base_price = None
        ticket_type_id = request.data.get('ticket_type_id')
        seat_id = request.data.get('seat_id')
        if ticket_type_id:
            tt = TicketType.objects.filter(id=ticket_type_id, event=event).first()
            if tt:
                base_price = tt.price
        elif seat_id:
            seat = EventSeat.objects.filter(id=seat_id, seat_map__event=event).first()
            if seat:
                base_price = seat_price(event, seat)

        try:
            return Response(quote(event, code, base_price=base_price))
        except PromoError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def clone(self, request, pk=None):
        """Duplicate an event (organizer only). Copies seat map + promo codes."""
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        new_event = clone_event(event=event, actor=request.user)
        return Response(
            EventListSerializer(new_event, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def analytics(self, request, pk=None):
        """Sales analytics for the organizer's dashboard."""
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return Response(event_analytics(event))

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def broadcast(self, request, pk=None):
        """Send a message to attendees (in-app + email). Organizer only."""
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

        subject = (request.data.get('subject') or '').strip()
        body = (request.data.get('body') or '').strip()
        audience = request.data.get('audience', 'all')
        if not subject or not body:
            return Response({'error': 'Subject and message are required.'}, status=status.HTTP_400_BAD_REQUEST)

        result = broadcast_to_attendees(event=event, subject=subject, body=body, audience=audience)
        return Response(result)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated], url_path='export-attendees')
    def export_attendees(self, request, pk=None):
        """CSV of all attendees for the organizer to download."""
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        return attendees_csv_response(event)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def seat_map(self, request, pk=None):
        """Получить схему мест для события."""
        event = self.get_object()
        # Release any expired holds so the map reflects real availability.
        release_expired_seat_holds(event)
        try:
            seat_map = event.seat_map
        except SeatMap.DoesNotExist:
            return Response({'error': 'No seat map for this event'}, status=status.HTTP_404_NOT_FOUND)

        serializer = SeatMapSerializer(seat_map)
        return Response(serializer.data)


class MyEventsView(generics.ListAPIView):
    serializer_class = EventListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Event.objects.filter(organizer=self.request.user).select_related('organizer', 'category').prefetch_related('registrations')


class RecommendationsView(generics.ListAPIView):
    serializer_class = EventListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            from ..recommendations import get_recommendations
            return get_recommendations(self.request.user, limit=10)
        except Exception as exc:
            logger.warning('Recommendations error: %s', exc)
            return Event.objects.filter(status=EventStatusChoices.PUBLISHED).order_by('-created_at')[:10]
