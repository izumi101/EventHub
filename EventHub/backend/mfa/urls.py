from django.urls import path

from . import views

urlpatterns = [
    # Login, second step (after POST /auth/login/ answered mfa_required)
    path('login/verify/', views.MFALoginVerifyView.as_view(), name='mfa_login_verify'),
    path('login/webauthn/options/', views.MFALoginWebAuthnOptionsView.as_view(), name='mfa_login_webauthn_options'),
    path('login/email/send/', views.MFALoginEmailSendView.as_view(), name='mfa_login_email_send'),
    # Status and management
    path('status/', views.MFAStatusView.as_view(), name='mfa_status'),
    path('totp/', views.TOTPDeviceView.as_view(), name='mfa_totp'),
    path('totp/setup/', views.TOTPSetupView.as_view(), name='mfa_totp_setup'),
    path('totp/confirm/', views.TOTPConfirmView.as_view(), name='mfa_totp_confirm'),
    path('email/send/', views.EmailSendView.as_view(), name='mfa_email_send'),
    path('email/enable/', views.EmailEnableView.as_view(), name='mfa_email_enable'),
    path('email/disable/', views.EmailDisableView.as_view(), name='mfa_email_disable'),
    path(
        'webauthn/register/options/', views.PasskeyRegisterOptionsView.as_view(), name='mfa_webauthn_register_options'
    ),
    path('webauthn/register/verify/', views.PasskeyRegisterVerifyView.as_view(), name='mfa_webauthn_register_verify'),
    path('webauthn/credentials/<int:pk>/', views.PasskeyDetailView.as_view(), name='mfa_webauthn_credential'),
    path('recovery-codes/regenerate/', views.RecoveryCodesRegenerateView.as_view(), name='mfa_recovery_regenerate'),
    path('disable/', views.MFADisableView.as_view(), name='mfa_disable'),
    # Step-up for sensitive actions
    path('step-up/', views.StepUpView.as_view(), name='mfa_step_up'),
    path('step-up/webauthn/options/', views.StepUpWebAuthnOptionsView.as_view(), name='mfa_step_up_webauthn_options'),
]
