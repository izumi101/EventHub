from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('register/send-code/', views.RegisterSendCodeView.as_view(), name='register_send_code'),
    path('register/verify-code/', views.VerifyRegistrationCodeView.as_view(), name='verify_registration_code'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/avatar/', views.AvatarUploadView.as_view(), name='profile_avatar'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Password reset flow
    path('password-reset/request/', views.PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password-reset/verify/', views.PasswordResetVerifyView.as_view(), name='password_reset_verify'),
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    # Admin-only organizer provisioning
    path('admin/organizers/', views.AdminCreateOrganizerView.as_view(), name='admin_create_organizer'),
]
