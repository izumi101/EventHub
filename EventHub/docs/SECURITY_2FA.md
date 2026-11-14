# Two-factor authentication: operator guide

Design and rationale: [`adr/0002-two-factor-authentication.md`](adr/0002-two-factor-authentication.md). Demo walkthrough: [`DEMO.md`](DEMO.md) section 6.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `MFA_REQUIRED_ROLES` | `organizer,staff,superuser` | Roles that must use 2FA (also `attendee`). Empty turns enforcement off for a staged rollout. |
| `MFA_ENCRYPTION_KEY` | dev key in DEBUG only | Encrypts TOTP secrets. Required with `DJANGO_DEBUG=0`; comma list for rotation (first encrypts). Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. |
| `MFA_STEP_UP_MAX_AGE_SECONDS` | `600` | How long a second-factor proof covers sensitive actions. |
| `MFA_EMAIL_ALLOWED_FOR_REQUIRED_ROLES` | `1` | Email codes count as the factor of required roles. Set `0` in production to require an authenticator app or a passkey from organizers and admins. |
| `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGINS` | `localhost`, `http://localhost:4200,https://localhost` | Passkey relying party: the bare host name and every origin the SPA is served from. Changing the RP ID invalidates registered passkeys. |
| `MFA_TOTP_ISSUER` | `EventHub` | Name shown in authenticator apps. |

Email codes are delivered by the outbox worker; with the console email backend (DEBUG) they appear in the worker log.

## Users

- Users manage their factors in the app: **Profile → Security** (`/profile/security`). Removing a factor, regenerating recovery codes and adding a factor to an account that has one ask for a fresh second factor.
- A user who must use 2FA and has none is taken through enrollment at sign-in; the Django admin (`/admin/`) asks staff for a second factor after the password (authenticator code, recovery code or an email code).

## Locked-out users

A user who lost every factor and every recovery code is reset by an operator **after verifying their identity out of band** (for example a call to the phone number on file plus a detail only the account owner knows; never on the strength of an email from the account's own address alone):

```bash
docker compose exec backend python manage.py mfa_reset <username> --yes-i-verified-the-user
```

It removes every factor, recovery code and pending email code, clears the lockout, signs the user out everywhere, logs `mfa.admin_reset` and notifies the user. Users who must use 2FA enroll again at their next sign-in.

## Audit

The `mfa` logger records enabling and disabling factors, recovery-code use, failed attempts, lockouts, email codes sent (purpose, not the code), clone warnings and admin resets with user id and client IP — never codes or secrets.
