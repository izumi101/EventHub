from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from datetime import timedelta

from events.models import Category, Event, Registration


class EventsTests(APITestCase):
    def setUp(self):
        # Create users
        self.organizer = User.objects.create_user(
            username="organizer", email="org@example.com", password="password123"
        )
        self.organizer.profile.role = "organizer"
        self.organizer.profile.save()

        self.attendee = User.objects.create_user(
            username="attendee", email="att@example.com", password="password123"
        )
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password123"
        )

        # Create category
        self.category = Category.objects.create(
            name="Technology", description="Tech events", icon="cpu"
        )

        # Create event
        self.event = Event.objects.create(
            title="Tech Summit 2026",
            description="All about technology",
            organizer=self.organizer,
            category=self.category,
            date=timezone.now() + timedelta(days=5),
            location="Silicon Valley",
            price=99.99,
            max_participants=5,
            status="published"
        )

    def test_list_categories(self):
        url = reverse("category-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Technology")

    def test_create_category_authenticated(self):
        # Regular (non-staff) users may NOT create categories.
        self.client.force_authenticate(user=self.organizer)
        url = reverse("category-list")
        data = {"name": "Business", "description": "Business networking", "icon": "briefcase"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Category.objects.filter(name="Business").exists())

    def test_create_category_admin(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("category-list")
        data = {"name": "Business", "description": "Business networking", "icon": "briefcase"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Category.objects.filter(name="Business").exists())

    def test_create_category_unauthenticated(self):
        url = reverse("category-list")
        data = {"name": "Business", "description": "Business networking"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_events(self):
        url = reverse("event-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check pagination structure
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)

    def test_create_event(self):
        self.client.force_authenticate(user=self.organizer)
        url = reverse("event-list")
        data = {
            "title": "Design Workshop",
            "description": "UI/UX basics",
            "category_id": self.category.id,
            "date": (timezone.now() + timedelta(days=2)).isoformat(),
            "location": "Online",
            "is_online": True,
            "price": 0.00,
            "max_participants": 20
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Event.objects.filter(title="Design Workshop").exists())

    def test_update_event_owner(self):
        self.client.force_authenticate(user=self.organizer)
        url = reverse("event-detail", args=[self.event.id])
        data = {
            "title": "Updated Tech Summit",
            "category_id": self.category.id,
            "date": self.event.date.isoformat(),
            "location": self.event.location
        }
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Updated Tech Summit")

    def test_update_event_non_owner(self):
        self.client.force_authenticate(user=self.attendee)
        url = reverse("event-detail", args=[self.event.id])
        data = {"title": "Malicious Update"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_register_for_event_success(self):
        self.client.force_authenticate(user=self.attendee)
        url = reverse("event-register", args=[self.event.id])
        data = {"notes": "Looking forward to it!"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Registration.objects.filter(user=self.attendee, event=self.event).exists())

    def test_register_for_event_organizer_fails(self):
        self.client.force_authenticate(user=self.organizer)
        url = reverse("event-register", args=[self.event.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_then_reregister_event(self):
        self.client.force_authenticate(user=self.attendee)
        register_url = reverse("event-register", args=[self.event.id])
        cancel_url = reverse("event-cancel", args=[self.event.id])

        first = self.client.post(register_url, {"notes": "See you there!"})
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        cancel = self.client.post(cancel_url)
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)

        second = self.client.post(register_url, {"notes": "Re-registering"})
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

        registration = Registration.objects.get(user=self.attendee, event=self.event)
        self.assertEqual(registration.status, "pending")
        self.assertEqual(registration.notes, "Re-registering")

    def test_cancel_pending_registration(self):
        # Attendees may only release an unpaid (pending) hold.
        registration = Registration.objects.create(user=self.attendee, event=self.event, status="pending")
        self.client.force_authenticate(user=self.attendee)
        url = reverse("event-cancel", args=[self.event.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        registration.refresh_from_db()
        self.assertEqual(registration.status, "cancelled")

    def test_cancel_confirmed_registration_rejected(self):
        # Confirmed tickets can't be self-cancelled — refunds go through
        # the refund-request flow instead.
        registration = Registration.objects.create(user=self.attendee, event=self.event, status="confirmed")
        self.client.force_authenticate(user=self.attendee)
        url = reverse("event-cancel", args=[self.event.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        registration.refresh_from_db()
        self.assertEqual(registration.status, "confirmed")

    def test_refund_request_rejected_after_check_in(self):
        # Once the ticket is scanned at the door, refunds are off the table.
        Registration.objects.create(
            user=self.attendee, event=self.event, status="confirmed", is_checked_in=True,
        )
        self.client.force_authenticate(user=self.attendee)
        url = reverse("event-request-refund", args=[self.event.id])
        response = self.client.post(url, {"reason": "Changed my mind"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("used for entry", response.data["error"])

    def test_check_in_ticket(self):
        registration = Registration.objects.create(user=self.attendee, event=self.event, status="confirmed")
        self.client.force_authenticate(user=self.organizer)
        url = reverse("registration-check-in", args=[registration.ticket_uuid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        registration.refresh_from_db()
        self.assertTrue(registration.is_checked_in)

    def test_check_in_ticket_unauthorized(self):
        registration = Registration.objects.create(user=self.attendee, event=self.event, status="confirmed")
        self.client.force_authenticate(user=self.attendee)
        url = reverse("registration-check-in", args=[registration.ticket_uuid])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_check_in_ticket_twice_returns_used(self):
        registration = Registration.objects.create(user=self.attendee, event=self.event, status="confirmed")
        self.client.force_authenticate(user=self.organizer)
        url = reverse("registration-check-in", args=[registration.ticket_uuid])

        first = self.client.post(url)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["status"], "success")

        second = self.client.post(url)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["status"], "used")

    def test_admin_can_approve_event(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("event-approve", args=[self.event.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, "published")
