from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from datetime import timedelta
import stripe

from events.models import Category, Event, Registration
from payments.models import Payment


class PaymentsTests(APITestCase):
    def setUp(self):
        # Create users
        self.organizer = User.objects.create_user(
            username="organizer", email="org@example.com", password="password123"
        )
        self.attendee = User.objects.create_user(
            username="attendee", email="att@example.com", password="password123"
        )

        # Create category and events
        self.category = Category.objects.create(name="Tech", icon="cpu")
        
        self.paid_event = Event.objects.create(
            title="Paid Event",
            description="Paid entry",
            organizer=self.organizer,
            category=self.category,
            date=timezone.now() + timedelta(days=2),
            location="New York",
            price=50.00,
            max_participants=10,
            status="published"
        )

        self.free_event = Event.objects.create(
            title="Free Event",
            description="Free entry",
            organizer=self.organizer,
            category=self.category,
            date=timezone.now() + timedelta(days=2),
            location="Online",
            price=0.00,
            max_participants=10,
            status="published"
        )

        # Create registrations
        self.paid_registration = Registration.objects.create(
            user=self.attendee, event=self.paid_event, status="pending"
        )
        self.free_registration = Registration.objects.create(
            user=self.attendee, event=self.free_event, status="pending"
        )

    def test_create_checkout_session_free_event(self):
        self.client.force_authenticate(user=self.attendee)
        url = reverse("create-checkout", args=[self.free_registration.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "This registration is free, no payment needed")

    @override_settings(STRIPE_MOCK_MODE=False)
    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session_paid_event_success(self, mock_stripe_create):
        # Mock stripe session return value
        class MockSession:
            id = "cs_test_12345"
            url = "https://checkout.stripe.com/pay/cs_test_12345"

        mock_stripe_create.return_value = MockSession()

        self.client.force_authenticate(user=self.attendee)
        url = reverse("create-checkout", args=[self.paid_registration.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["session_id"], "cs_test_12345")
        self.assertEqual(response.data["checkout_url"], "https://checkout.stripe.com/pay/cs_test_12345")

        # Verify Payment model was created in db
        payment = Payment.objects.get(registration=self.paid_registration)
        self.assertEqual(payment.stripe_checkout_session_id, "cs_test_12345")
        self.assertEqual(payment.amount, 50.00)
        self.assertEqual(payment.status, "pending")

    def test_verify_payment_not_found(self):
        self.client.force_authenticate(user=self.attendee)
        url = reverse("verify-payment") + "?session_id=nonexistent"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_verify_payment_success(self):
        payment = Payment.objects.create(
            registration=self.paid_registration,
            amount=50.00,
            stripe_checkout_session_id="cs_test_12345",
            status="completed"
        )
        self.client.force_authenticate(user=self.attendee)
        url = reverse("verify-payment") + "?session_id=cs_test_12345"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["event_title"], "Paid Event")

    @patch("stripe.Webhook.construct_event")
    def test_stripe_webhook_completed(self, mock_construct_event):
        # Setup payment in db
        payment = Payment.objects.create(
            registration=self.paid_registration,
            amount=50.00,
            stripe_checkout_session_id="cs_test_12345",
            status="pending"
        )

        mock_construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_12345",
                    "payment_intent": "pi_test_intent_123",
                    "metadata": {
                        "registration_id": self.paid_registration.id
                    }
                }
            }
        }

        url = reverse("stripe-webhook")
        response = self.client.post(url, data={}, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.stripe_payment_intent_id, "pi_test_intent_123")

        self.paid_registration.refresh_from_db()
        self.assertEqual(self.paid_registration.status, "confirmed")

    @override_settings(STRIPE_MOCK_MODE=False)
    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session_updates_existing_payment(self, mock_stripe_create):
        class MockSession:
            id = "cs_test_abc"
            url = "https://checkout.stripe.com/pay/cs_test_abc"

        mock_stripe_create.return_value = MockSession()

        existing = Payment.objects.create(
            registration=self.paid_registration,
            amount=10.00,
            stripe_checkout_session_id="old_session",
            status="pending"
        )

        self.client.force_authenticate(user=self.attendee)
        url = reverse("create-checkout", args=[self.paid_registration.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        existing.refresh_from_db()
        self.assertEqual(existing.stripe_checkout_session_id, "cs_test_abc")
        self.assertEqual(existing.amount, 50.00)
