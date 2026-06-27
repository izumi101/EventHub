from rest_framework import generics, viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import (
    BasePermission,
    SAFE_METHODS,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
    AllowAny,
)
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction, models
from django.db.models import Q, Count

from common.choices import EventStatusChoices, RegistrationStatusChoices
from common.permissions import can_manage_event

from .models import Category, Event, Registration, SeatMap, EventSeat, Favorite, Review, Notification, PromoCode, CheckInList, CheckInLog
from .serializers import (
    CategorySerializer,
    EventListSerializer,
    EventCreateSerializer,
    RegistrationSerializer,
    SeatMapSerializer,
    FavoriteSerializer,
    ReviewSerializer,
    ReviewCreateSerializer,
    NotificationSerializer,
    PromoCodeSerializer,
    CheckInListSerializer,
    CheckInLogSerializer,
)
from .services import (
    approve_event as approve_event_service,
    cancel_registration as cancel_registration_service,
    check_in_registration as check_in_registration_service,
    register_for_event as register_for_event_service,
    reject_event as reject_event_service,
    release_expired_seat_holds,
)


class IsOrganizerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.organizer == request.user


def _event_queryset_for_user(user):
    queryset = Event.objects.select_related('organizer', 'category').prefetch_related('registrations')
    if user.is_authenticated and user.is_superuser:
        return queryset
    if user.is_authenticated:
        return queryset.filter(Q(organizer=user) | Q(status=EventStatusChoices.PUBLISHED))
    return queryset.filter(status=EventStatusChoices.PUBLISHED)


def _restrict_status_list(queryset, user, status_value):
    if status_value == EventStatusChoices.PENDING:
        if user.is_authenticated and user.is_superuser:
            return queryset.filter(status=EventStatusChoices.PENDING)
        if user.is_authenticated:
            return queryset.filter(status=EventStatusChoices.PENDING, organizer=user)
        return queryset.none()

    if status_value == EventStatusChoices.PUBLISHED:
        return queryset.filter(status=EventStatusChoices.PUBLISHED)

    if user.is_authenticated and user.is_superuser:
        return queryset.filter(status=status_value)
    if user.is_authenticated:
        return queryset.filter(status=status_value, organizer=user)
    return queryset.filter(status=EventStatusChoices.PUBLISHED)


# ---- CBV: Categories ---- #
class CategoryListCreateView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None

    def get_permissions(self):
        if self.request.method == 'POST':
            from rest_framework.permissions import IsAdminUser
            return [IsAdminUser()]
        return [AllowAny()]


# ---- CBV: Events (full CRUD via ViewSet) ---- #
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
        queryset = _event_queryset_for_user(user)
        is_detail = self.action not in ['list']
        status_param = self.request.query_params.get('status')
        if is_detail:
            if not user.is_authenticated:
                queryset = queryset.filter(status=EventStatusChoices.PUBLISHED)
            else:
                # Ticket holders keep access to events that left the public
                # list (cancelled / completed) — their tickets link here.
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
            queryset = _restrict_status_list(queryset, user, status_param)

        # Hide events that already happened unless explicitly requested.
        if not is_detail and self.request.query_params.get('upcoming') == 'true':
            from django.utils import timezone
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
                from .search import semantic_search
                queryset = semantic_search(semantic_q, limit=40, extra_qs=queryset)
            except Exception:
                # Fallback to keyword if embeddings not ready
                queryset = queryset.filter(
                    Q(title__icontains=semantic_q) |
                    Q(description__icontains=semantic_q)
                )

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        profile_role = getattr(getattr(user, 'profile', None), 'role', '')
        if not (user.is_staff or user.is_superuser or profile_role == 'organizer'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                'Only organizer accounts can create events. '
                'Ask an administrator to create an organizer account for you.'
            )
        event = serializer.save()
        # Index new event asynchronously (fire-and-forget in same process for now)
        try:
            from .search import index_event
            import threading
            threading.Thread(target=index_event, args=(event,), daemon=True).start()
        except Exception:
            pass

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Lazy lifecycle: a published event whose end has passed becomes
        # "completed" the first time anyone opens it.
        from .services import mark_completed_if_past
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
            from .services import attendee_cancel
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
            from .services import request_refund as request_refund_service
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
        from .pricing import get_dynamic_price
        return Response(get_dynamic_price(event))

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def submit(self, request, pk=None):
        """Send a draft (e.g. a clone) to admin review."""
        event = self.get_object()
        try:
            from .services import submit_event
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
            from .services import cancel_event as cancel_event_service
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
        from .queue import join_queue, is_queue_active
        if not is_queue_active(event):
            return Response({'status': 'not_needed', 'message': 'Queue not active for this event.'})
        result = join_queue(event.id, request.user.id)
        return Response(result)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def queue_status(self, request, pk=None):
        """Check queue position / admission status."""
        event = self.get_object()
        from .queue import get_queue_status, is_queue_active
        if not is_queue_active(event):
            return Response({'status': 'not_needed'})
        result = get_queue_status(event.id, request.user.id)
        return Response(result)

    @action(detail=True, methods=['get', 'post', 'delete'], permission_classes=[IsAuthenticated])
    def waitlist(self, request, pk=None):
        """GET = my status · POST = join · DELETE = leave the waitlist."""
        event = self.get_object()
        from .waitlist import join_waitlist, leave_waitlist, position, promote_waitlist

        if request.method == 'POST':
            # The waitlist leads to a ticket — same attendee-only rule as buying.
            from .services import ensure_attendee_can_buy
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
        from .promo import quote, PromoError
        code = request.data.get('code', '')

        base_price = None
        ticket_type_id = request.data.get('ticket_type_id')
        seat_id = request.data.get('seat_id')
        if ticket_type_id:
            from .models import TicketType
            tt = TicketType.objects.filter(id=ticket_type_id, event=event).first()
            if tt:
                base_price = tt.price
        elif seat_id:
            seat = EventSeat.objects.filter(id=seat_id, seat_map__event=event).first()
            if seat:
                from .seat_pricing import seat_price
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
        from .services import clone_event
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
        from .analytics import event_analytics
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

        from .messaging import broadcast_to_attendees
        result = broadcast_to_attendees(event=event, subject=subject, body=body, audience=audience)
        return Response(result)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated], url_path='export-attendees')
    def export_attendees(self, request, pk=None):
        """CSV of all attendees for the organizer to download."""
        event = self.get_object()
        if not can_manage_event(event, request.user):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        from .exports import attendees_csv_response
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


# ---- CBV: Registrations ViewSet for Check-in ---- #
class RegistrationViewSet(viewsets.GenericViewSet):
    queryset = Registration.objects.all()
    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='check-in/(?P<uuid>[^/.]+)')
    def check_in(self, request, uuid=None):
        registration = Registration.objects.filter(ticket_uuid=uuid).first()
        if registration is None:
            # Group-booking tickets live in BookingSeat, not Registration.
            return self._check_in_booking_seat(request, uuid)

        try:
            registration, used = check_in_registration_service(registration=registration, actor=request.user)
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
                    'checked_in_at': registration.checked_in_at
                },
                status=status.HTTP_200_OK
            )

        return Response({
            'message': 'Ticket valid! Welcome to the event.',
            'status': 'success',
            'attendee': registration.user.username,
            'event': registration.event.title
        }, status=status.HTTP_200_OK)

    def _check_in_booking_seat(self, request, uuid):
        """Validate a group-booking seat ticket by its UUID."""
        from bookings.models import Booking, BookingSeat
        from common.permissions import can_check_in_event
        from django.utils import timezone as _tz

        seat_ticket = get_object_or_404(
            BookingSeat.objects.select_related('booking__event', 'booking__owner', 'claimed_by'),
            ticket_uuid=uuid,
        )
        booking = seat_ticket.booking
        if not can_check_in_event(booking.event, request.user):
            return Response({'error': 'You do not have check-in rights for this event.'},
                            status=status.HTTP_403_FORBIDDEN)
        if booking.status != Booking.Status.CONFIRMED:
            return Response({'error': 'Ticket is NOT paid — the group booking was never completed.',
                             'status': 'invalid'}, status=status.HTTP_400_BAD_REQUEST)

        attendee = (
            seat_ticket.attendee_name
            or (seat_ticket.claimed_by.username if seat_ticket.claimed_by_id else '')
            or booking.owner.username
        )
        if seat_ticket.is_checked_in:
            return Response({
                'message': 'Ticket already checked in!',
                'status': 'used',
                'attendee': attendee,
                'checked_in_at': seat_ticket.checked_in_at,
            })

        seat_ticket.is_checked_in = True
        seat_ticket.checked_in_at = _tz.now()
        seat_ticket.save(update_fields=['is_checked_in', 'checked_in_at'])
        return Response({
            'message': f'Ticket valid! Group seat {seat_ticket.seat.row}-{seat_ticket.seat.col}.',
            'status': 'success',
            'attendee': attendee,
            'event': booking.event.title,
        })


# ---- CBV: My events (organized) ---- #
class MyEventsView(generics.ListAPIView):
    serializer_class = EventListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Event.objects.filter(organizer=self.request.user).select_related('organizer', 'category').prefetch_related('registrations')


# ---- CBV: My registrations ---- #
class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Heal any pending-but-paid registrations before listing so the UI
        # reflects the true (confirmed) state instead of "payment incomplete".
        from .services import reconcile_paid_registrations
        reconcile_paid_registrations(user=self.request.user)
        qs = Registration.objects.filter(user=self.request.user).exclude(status=RegistrationStatusChoices.CANCELLED).select_related('event', 'event__organizer', 'event__category', 'seat')
        # ?event=<id> lets the event page fetch exactly its own registration
        # instead of paging through everything the user ever booked.
        event_id = self.request.query_params.get('event')
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs


# ---- CBV: Recommendations ---- #
class RecommendationsView(generics.ListAPIView):
    serializer_class = EventListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            from .recommendations import get_recommendations
            return get_recommendations(self.request.user, limit=10)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning('Recommendations error: %s', exc)
            return Event.objects.filter(status=EventStatusChoices.PUBLISHED).order_by('-created_at')[:10]


# ───────────── FAVORITES ─────────────

class FavoritesListView(generics.ListAPIView):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Favorite.objects.filter(user=self.request.user).select_related('event', 'event__organizer', 'event__category')


class FavoriteToggleView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        fav, created = Favorite.objects.get_or_create(user=request.user, event=event)
        if not created:
            fav.delete()
            return Response({'favorited': False})
        return Response({'favorited': True}, status=status.HTTP_201_CREATED)

    def get(self, request, event_id):
        exists = Favorite.objects.filter(user=request.user, event_id=event_id).exists()
        return Response({'favorited': exists})


# ───────────── REVIEWS ─────────────

class EventReviewsView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(event_id=self.kwargs['event_id']).select_related('user', 'user__profile')

    def perform_create(self, serializer):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        serializer.save(user=self.request.user, event=event)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event_id'] = self.kwargs['event_id']
        return ctx


# ───────────── NOTIFICATIONS ─────────────

class NotificationsListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)[:50]


class NotificationMarkReadView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
        else:
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True})


# ───────────── PROMO CODES (organizer) ─────────────

class EventPromoCodesView(generics.ListCreateAPIView):
    """List + create promo codes for an event the user manages."""
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAuthenticated]

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            return PromoCode.objects.none()
        return event.promo_codes.all()

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)


class PromoCodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PromoCode.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')


# ───────────── CUSTOM QUESTIONS (organizer) ─────────────

class EventQuestionsView(generics.ListCreateAPIView):
    """List + create custom checkout questions for an event you manage.

    GET is public (the checkout form needs them); POST requires management.
    """
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        from .serializers import EventQuestionSerializer
        return EventQuestionSerializer

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        from .models import EventQuestion
        return EventQuestion.objects.filter(event_id=self.kwargs['event_id'])

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)


class EventQuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import EventQuestionSerializer
        return EventQuestionSerializer

    def get_queryset(self):
        from .models import EventQuestion
        return EventQuestion.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')


class EventTicketTypesView(generics.ListCreateAPIView):
    """List + create ticket tiers for an event.

    GET is public (the buy box needs them); POST requires management.
    """
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        from .serializers import TicketTypeSerializer
        return TicketTypeSerializer

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        from .models import TicketType
        return TicketType.objects.filter(event_id=self.kwargs['event_id'])

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)


class TicketTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import TicketTypeSerializer
        return TicketTypeSerializer

    def get_queryset(self):
        from .models import TicketType
        return TicketType.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')


class _ManagedEventListCreate(generics.ListCreateAPIView):
    """Base for event-scoped collections only managers may list+create."""
    permission_classes = [IsAuthenticated]
    model = None  # set in subclass

    def _event(self):
        return get_object_or_404(Event, pk=self.kwargs['event_id'])

    def get_queryset(self):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            return self.model.objects.none()
        return self.model.objects.filter(event=event)

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')
        serializer.save(event=event)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['event'] = self._event()
        return ctx


class _ManagedDetail(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    model = None

    def get_queryset(self):
        return self.model.objects.select_related('event')

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if not can_manage_event(obj.event, request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')


# ── Event staff ──
class EventStaffView(_ManagedEventListCreate):
    from .models import EventStaff as _M
    model = _M

    def get_serializer_class(self):
        from .serializers import EventStaffSerializer
        return EventStaffSerializer

    def perform_create(self, serializer):
        event = self._event()
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not manage this event.')
        serializer.save()  # create() reads event from context


class EventStaffDetailView(_ManagedDetail):
    from .models import EventStaff as _M
    model = _M

    def get_serializer_class(self):
        from .serializers import EventStaffSerializer
        return EventStaffSerializer


# ── Webhooks ──
class EventWebhooksView(_ManagedEventListCreate):
    from .models import Webhook as _M
    model = _M

    def get_serializer_class(self):
        from .serializers import WebhookSerializer
        return WebhookSerializer


class WebhookDetailView(_ManagedDetail):
    from .models import Webhook as _M
    model = _M

    def get_serializer_class(self):
        from .serializers import WebhookSerializer
        return WebhookSerializer


# ── Affiliates ──
class EventAffiliatesView(_ManagedEventListCreate):
    from .models import Affiliate as _M
    model = _M

    def get_serializer_class(self):
        from .serializers import AffiliateSerializer
        return AffiliateSerializer


class AffiliateDetailView(_ManagedDetail):
    from .models import Affiliate as _M
    model = _M

    def get_serializer_class(self):
        from .serializers import AffiliateSerializer
        return AffiliateSerializer


class AffiliateClickView(generics.GenericAPIView):
    """Public: record a click when someone opens an event via ?ref=CODE."""
    permission_classes = [AllowAny]

    def post(self, request, event_id):
        from .models import Affiliate
        code = (request.data.get('code') or '').strip()
        if code:
            Affiliate.objects.filter(
                event_id=event_id, code__iexact=code, is_active=True,
            ).update(clicks=models.F('clicks') + 1)
        return Response({'ok': True})


class EventRefundRequestsView(generics.ListAPIView):
    """Organizer lists refund requests for their event (pending first)."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import RefundRequestSerializer
        return RefundRequestSerializer

    def get_queryset(self):
        from .models import RefundRequest
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            return RefundRequest.objects.none()
        qs = RefundRequest.objects.filter(
            registration__event=event,
        ).select_related('registration__user', 'registration__payment', 'registration__ticket_type')
        # Pending first, then most recent.
        from django.db.models import Case, When, IntegerField
        return qs.annotate(
            _order=Case(When(status='pending', then=0), default=1, output_field=IntegerField()),
        ).order_by('_order', '-created_at')


class ResolveRefundRequestView(generics.GenericAPIView):
    """Organizer approves or rejects a refund request."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .models import RefundRequest
        from .services import resolve_refund_request
        rr = get_object_or_404(RefundRequest.objects.select_related('registration__event', 'registration__user'), pk=pk)
        approve = bool(request.data.get('approve'))
        try:
            resolve_refund_request(
                refund_request=rr, actor=request.user, approve=approve,
                note=request.data.get('note', ''),
            )
        except PermissionError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': rr.status})


class EventWaitlistView(generics.ListAPIView):
    """Organizer views everyone on the waitlist for their event."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import WaitlistEntrySerializer
        return WaitlistEntrySerializer

    def get_queryset(self):
        from .models import WaitlistEntry
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            return WaitlistEntry.objects.none()
        return WaitlistEntry.objects.filter(event=event).select_related('user')


# ───────────── ADMIN DASHBOARD ─────────────

class AdminDashboardView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth.models import User as DjangoUser
        from payments.models import Payment
        from common.choices import PaymentStatusChoices

        if not request.user.is_superuser:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        total_users = DjangoUser.objects.filter(is_active=True).count()
        total_events = Event.objects.count()
        published_events = Event.objects.filter(status=EventStatusChoices.PUBLISHED).count()
        total_registrations = Registration.objects.exclude(status=RegistrationStatusChoices.CANCELLED).count()
        confirmed_registrations = Registration.objects.filter(status=RegistrationStatusChoices.CONFIRMED).count()

        from django.db.models import Sum
        revenue = Payment.objects.filter(
            status=PaymentStatusChoices.COMPLETED
        ).aggregate(total=Sum('amount'))['total'] or 0

        top_events = (
            Event.objects
            .filter(status=EventStatusChoices.PUBLISHED)
            .annotate(reg_count=models.Count('registrations'))
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


# ─── Check-in Lists ──────────────────────────────────────────────────────────

class EventCheckInListsView(generics.ListCreateAPIView):
    """GET list / POST create check-in lists for an event (organizer only)."""
    serializer_class = CheckInListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # lists are few; frontend expects a bare array

    def _get_event(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied
        return event

    def get_queryset(self):
        return CheckInList.objects.filter(event_id=self.kwargs['event_id'])

    def perform_create(self, serializer):
        event = self._get_event()
        # First list becomes default automatically
        is_first = not CheckInList.objects.filter(event=event).exists()
        serializer.save(event=event, is_default=is_first)


class CheckInListDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PUT / DELETE a single check-in list."""
    serializer_class = CheckInListSerializer
    permission_classes = [IsAuthenticated]
    queryset = CheckInList.objects.all()

    def get_object(self):
        obj = get_object_or_404(CheckInList, pk=self.kwargs['pk'])
        if not can_manage_event(obj.event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied
        return obj


class CheckInListAttendeesView(generics.ListAPIView):
    """Return all registrations for an event with their check-in status for a specific list."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, **kwargs):
        checkin_list = get_object_or_404(CheckInList, pk=pk)
        if not can_manage_event(checkin_list.event, request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied

        regs = (
            Registration.objects
            .filter(event=checkin_list.event)
            .exclude(status__in=[RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED])
            .select_related('user')
            .prefetch_related('checkin_logs')
        )

        # Latest log entry per registration for this list
        log_map = {}
        for log in CheckInLog.objects.filter(checkin_list=checkin_list).select_related('scanned_by'):
            if log.registration_id not in log_map:
                log_map[log.registration_id] = log

        result = []
        for reg in regs:
            u = reg.user
            last_log = log_map.get(reg.id)
            result.append({
                'id': reg.id,
                'ticket_uuid': str(reg.ticket_uuid),
                'username': u.username,
                'full_name': f'{u.first_name} {u.last_name}'.strip() or u.username,
                'email': u.email,
                'status': reg.status,
                'is_checked_in': last_log.action == CheckInLog.ACTION_CHECK_IN if last_log else False,
                'checked_in_at': last_log.created_at if (last_log and last_log.action == CheckInLog.ACTION_CHECK_IN) else None,
                'scanned_by': last_log.scanned_by.username if (last_log and last_log.scanned_by) else None,
            })

        return Response(result)


class CheckInListCheckInView(generics.GenericAPIView):
    """POST ticket_uuid to check in (or undo) within a specific list."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, **kwargs):
        checkin_list = get_object_or_404(CheckInList, pk=pk)
        if not can_manage_event(checkin_list.event, request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied

        ticket_uuid = request.data.get('ticket_uuid')
        action_type = request.data.get('action', CheckInLog.ACTION_CHECK_IN)
        note = request.data.get('note', '')

        if not ticket_uuid:
            return Response({'error': 'ticket_uuid required'}, status=status.HTTP_400_BAD_REQUEST)

        reg = get_object_or_404(Registration, ticket_uuid=ticket_uuid, event=checkin_list.event)

        with transaction.atomic():
            log = CheckInLog.objects.create(
                checkin_list=checkin_list,
                registration=reg,
                action=action_type,
                scanned_by=request.user,
                note=note,
            )
            # Keep global is_checked_in in sync with the default list
            if checkin_list.is_default:
                reg.is_checked_in = (action_type == CheckInLog.ACTION_CHECK_IN)
                if reg.is_checked_in:
                    from django.utils import timezone
                    reg.checked_in_at = timezone.now()
                else:
                    reg.checked_in_at = None
                reg.save(update_fields=['is_checked_in', 'checked_in_at'])

        u = reg.user
        return Response({
            'message': 'Checked in' if action_type == CheckInLog.ACTION_CHECK_IN else 'Undone',
            'attendee': f'{u.first_name} {u.last_name}'.strip() or u.username,
            'action': action_type,
            'log_id': log.id,
        })


class EventCheckInLogsView(generics.ListAPIView):
    """GET recent check-in log entries for an event (organizer, newest first)."""
    serializer_class = CheckInLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # frontend expects a bare array; capped below

    def get_queryset(self):
        event = get_object_or_404(Event, pk=self.kwargs['event_id'])
        if not can_manage_event(event, self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied
        return (
            CheckInLog.objects
            .filter(checkin_list__event=event)
            .select_related('checkin_list', 'registration__user', 'scanned_by')
        )[:200]
