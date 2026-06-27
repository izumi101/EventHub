# pyrefly: ignore [missing-import]
from django.contrib.auth.models import User
# pyrefly: ignore [missing-import]
from django.urls import reverse
# pyrefly: ignore [missing-import]
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import EmailVerificationCode, PasswordResetCode


class AccountsTests(APITestCase):
    def setUp(self):
        # Create a test user
        self.user_password = "securePassword123"
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password=self.user_password,
            first_name="Test",
            last_name="User"
        )
        # Update user role to organizer
        self.profile = self.user.profile
        self.profile.role = "organizer"
        self.profile.save()

    def test_send_verification_code_success(self):
        url = reverse("register_send_code")
        data = {"email": "newuser@example.com"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(EmailVerificationCode.objects.filter(email="newuser@example.com").exists())

    def test_send_verification_code_existing_email(self):
        url = reverse("register_send_code")
        data = {"email": "testuser@example.com"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_registration_code_success(self):
        email = "newuser@example.com"
        verification = EmailVerificationCode.create_for_email(email)
        url = reverse("verify_registration_code")
        data = {"email": email, "code": verification.code}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_verify_registration_code_invalid(self):
        url = reverse("verify_registration_code")
        data = {"email": "newuser@example.com", "code": "000000"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_user_success(self):
        email = "newuser@example.com"
        verification = EmailVerificationCode.create_for_email(email)
        url = reverse("register")
        data = {
            "username": "newuser",
            "email": email,
            "password": "newPassword123",
            "password2": "newPassword123",
            "first_name": "New",
            "last_name": "User",
            "verification_code": verification.code,
            "role": "attendee"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_user_invalid_verification(self):
        url = reverse("register")
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newPassword123",
            "password2": "newPassword123",
            "verification_code": "000000",
            "role": "attendee"
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_success(self):
        url = reverse("login")
        # Test login via username
        data = {"username": "testuser", "password": self.user_password}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tokens", response.data)

        # Test login via email
        data = {"username": "testuser@example.com", "password": self.user_password}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_failure(self):
        url = reverse("login")
        data = {"username": "testuser", "password": "wrongpassword"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_get_and_put(self):
        # Authenticate client
        self.client.force_authenticate(user=self.user)
        url = reverse("profile")
        
        # Test GET profile
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "testuser")

        # Test PUT profile
        data = {
            "first_name": "UpdatedName",
            "profile": {
                "bio": "New bio info",
                "location": "New location"
            }
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "UpdatedName")
        self.assertEqual(self.user.profile.bio, "New bio info")

    def test_password_reset_flow(self):
        # Step 1: Request reset code
        url_request = reverse("password_reset_request")
        data_request = {"identifier": "testuser@example.com"}
        response_request = self.client.post(url_request, data_request)
        self.assertEqual(response_request.status_code, status.HTTP_200_OK)
        
        reset_code = PasswordResetCode.objects.filter(user=self.user).first()
        self.assertIsNotNone(reset_code)

        # Step 2: Verify reset code
        url_verify = reverse("password_reset_verify")
        data_verify = {"identifier": "testuser@example.com", "code": reset_code.code}
        response_verify = self.client.post(url_verify, data_verify)
        self.assertEqual(response_verify.status_code, status.HTTP_200_OK)
        self.assertIn("reset_token", response_verify.data)
        
        reset_token = response_verify.data["reset_token"]

        # Step 3: Confirm new password
        url_confirm = reverse("password_reset_confirm")
        data_confirm = {
            "reset_token": reset_token,
            "new_password": "newSecurePassword123",
            "new_password2": "newSecurePassword123"
        }
        response_confirm = self.client.post(url_confirm, data_confirm)
        self.assertEqual(response_confirm.status_code, status.HTTP_200_OK)
        
        # Test login with new password
        self.client.logout()
        url_login = reverse("login")
        data_login = {"username": "testuser", "password": "newSecurePassword123"}
        response_login = self.client.post(url_login, data_login)
        self.assertEqual(response_login.status_code, status.HTTP_200_OK)

    def test_password_reset_flow_via_username(self):
        url_request = reverse("password_reset_request")
        response_request = self.client.post(url_request, {"identifier": "testuser"})
        self.assertEqual(response_request.status_code, status.HTTP_200_OK)

        reset_code = PasswordResetCode.objects.filter(user=self.user).first()
        self.assertIsNotNone(reset_code)

        url_verify = reverse("password_reset_verify")
        response_verify = self.client.post(url_verify, {"identifier": "testuser", "code": reset_code.code})
        self.assertEqual(response_verify.status_code, status.HTTP_200_OK)
