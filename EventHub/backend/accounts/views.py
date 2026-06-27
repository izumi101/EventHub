from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from .serializers import RegisterSerializer, LoginSerializer, UserSerializer, OrganizerCreateSerializer
from .services import (
    build_auth_payload,
    confirm_password_reset,
    login_user,
    request_password_reset,
    send_registration_code,
    verify_password_reset_code,
    verify_registration_code,
)


class RegisterView(APIView):
    """
    Handles new user registration.
    Validates user credentials, verification code, and creates the user profile.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'register'

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(build_auth_payload(user), status=status.HTTP_201_CREATED)


class AdminCreateOrganizerView(APIView):
    """
    Admin-only: creates an organizer account.
    Attendees cannot promote themselves — this is the only way to get the role.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = OrganizerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class RegisterSendCodeView(APIView):
    """
    Sends a registration verification code to the target email.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'register'

    def post(self, request):
        email = request.data.get('email', '').strip()

        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            verification = send_registration_code(email)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({'error': 'Failed to send verification email. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        payload = {'message': 'Verification code sent successfully. Please check your email.'}
        # Dev convenience: without real SMTP the console backend only logs the
        # email, so surface the code to the UI instead of stranding the user.
        from django.conf import settings
        if 'console' in settings.EMAIL_BACKEND:
            payload['dev_code'] = verification.code
            payload['message'] = 'Email is not configured — use this code.'
        return Response(payload)


class VerifyRegistrationCodeView(APIView):
    """
    Verifies the email registration code.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'register'

    def post(self, request):
        email = request.data.get('email', '').strip()
        code = request.data.get('code', '').strip()

        if not email or not code:
            return Response({'error': 'Email and code are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            verify_registration_code(email, code)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Code verified successfully.'})


class LoginView(APIView):
    """
    Handles user login, supporting both username and email as identifiers.
    Returns access and refresh JWT tokens on successful authentication.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data['username']
            user = login_user(identifier, serializer.validated_data['password'])
            if user:
                return Response(build_auth_payload(user))
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    Blacklists the user's refresh token to sign out.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh_token = request.data.get('refresh')
        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass
        return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """
    Retrieves or updates the authenticated user's profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AvatarUploadView(APIView):
    """Upload (or clear) the authenticated user's profile avatar."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        avatar = request.FILES.get('avatar')
        if not avatar:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        if avatar.size > 5 * 1024 * 1024:
            return Response({'error': 'Avatar must be under 5 MB.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate the upload really is an image. Assigning straight to the
        # ImageField and calling save() skips field validation, so without this
        # a non-image (e.g. an HTML/SVG file carrying a script) could be stored
        # under MEDIA and served back to other users.
        allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
        if getattr(avatar, 'content_type', None) not in allowed_types:
            return Response({'error': 'Avatar must be a JPEG, PNG, WebP or GIF image.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from PIL import Image
            Image.open(avatar).verify()
            avatar.seek(0)
        except Exception:
            return Response({'error': 'Uploaded file is not a valid image.'}, status=status.HTTP_400_BAD_REQUEST)

        profile = request.user.profile
        profile.avatar = avatar
        profile.save(update_fields=['avatar'])
        return Response(UserSerializer(request.user).data)

    def delete(self, request):
        profile = request.user.profile
        if profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None
            profile.save(update_fields=['avatar'])
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(APIView):
    """
    Sends a 6-digit password reset code to the user's associated email if the account exists.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'password_reset'

    def post(self, request):
        identifier = request.data.get('identifier', '').strip()
        if not identifier:
            return Response({'error': 'Please enter your email or username.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            request_password_reset(identifier)
        except Exception:
            # We intentionally do not reveal whether the account exists.
            pass

        return Response({'message': 'If an account exists, a reset code has been sent to the associated email.'})


class PasswordResetVerifyView(APIView):
    """
    Verifies the password reset code and returns a one-time reset token.
    """
    permission_classes = [AllowAny]
    throttle_scope = 'password_reset'

    def post(self, request):
        identifier = request.data.get('identifier', '').strip()
        code = request.data.get('code', '').strip()

        if not identifier or not code:
            return Response({'error': 'Identifier and code are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            reset_entry = verify_password_reset_code(identifier, code)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'reset_token': reset_entry.reset_token, 'message': 'Code verified successfully.'})


class PasswordResetConfirmView(APIView):
    """
    Resets the user's password using the one-time reset token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        reset_token = request.data.get('reset_token', '').strip()
        new_password = request.data.get('new_password', '').strip()
        new_password2 = request.data.get('new_password2', '').strip()

        if not reset_token or not new_password:
            return Response({'error': 'Reset token and new password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != new_password2:
            return Response({'error': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            confirm_password_reset(reset_token, new_password, new_password2)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Password has been reset successfully. You can now log in.'})


class ChangePasswordView(APIView):
    """Change password for authenticated users (old password required)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')
        new_password2 = request.data.get('new_password2', '')

        if not old_password or not new_password:
            return Response({'error': 'All fields are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_password(old_password):
            return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != new_password2:
            return Response({'error': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save()
        return Response({'message': 'Password changed successfully.'})
