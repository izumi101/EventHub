# ADR 0002: Two-factor authentication

- Status: accepted (2026-11-12)
- Scope: roadmap phase 4.1 (`PLAN.md` 4.1, "2FA: TOTP + WebAuthn / passkeys")
- Operator guide: [`docs/SECURITY_2FA.md`](../SECURITY_2FA.md)

## Context

Organizers move money (refunds, event cancellation with refunds, later
payouts) and download attendee personal data. Admins can do anything. Until
now every account was protected by a password only, the API issued a
SimpleJWT pair straight from `POST /auth/login/`, and `/admin/` was a plain
Django session login. A phished or reused password was a full account
takeover, including payout details once phase 1Б lands — `PLAN.md` puts 2FA
before payouts for exactly that reason.

Constraints:

- The SPA authenticates with JWTs kept by the browser (`Authorization:
  Bearer`), refreshed with rotation and blacklisting. There is no server
  session for the API, so "has this request passed a second factor, and how
  long ago" has to be answerable from the token.
- The defense demo runs on `http://localhost:4200`; the LAN demo
  (`scripts/demo-lan.sh`) is plain HTTP on an IP address.
- One maintainer: well-known libraries, no hosted identity provider.

## Decision

### 1. Factors: TOTP and WebAuthn, plus recovery codes

- **TOTP** (RFC 6238, 6 digits, 30 s, SHA-1 — what every authenticator app
  supports) via `pyotp`. Works everywhere, offline, including on the LAN demo.
- **WebAuthn / passkeys** (platform or roaming authenticators) via
  `webauthn` (py_webauthn, Duo Labs) on the server and
  `@simplewebauthn/browser` in the SPA. Phishing-resistant: the browser binds
  the assertion to the origin, so a look-alike site gets nothing usable.
- **Recovery codes**: 10 one-time codes of 80 bits each
  (`xxxx-xxxx-xxxx-xxxx`, base32), shown once, stored as salted SHA-256
  (80 bits make offline guessing hopeless without a slow hash, and checking
  ten codes stays cheap). Regenerating them needs a fresh second factor.

SMS and email OTP were rejected: SIM swap and mailbox takeover are the
attacks 2FA is meant to stop, and both cost money or depend on delivery.

### 2. Login is two requests; the first never returns a session

`POST /auth/login/` checks the password, then answers one of:

| Situation | Response (200) |
|---|---|
| No second factor, none required | `{user, tokens}` — unchanged behaviour |
| Second factor enrolled | `{mfa_required: true, challenge_token, methods, expires_in}` |
| Role requires 2FA, none enrolled | `{mfa_enrollment_required: true, enrollment_token, expires_in}` |

`challenge_token` and `enrollment_token` are SimpleJWT tokens of their own
types (`mfa_challenge`, 5 minutes; `mfa_enrollment`, 15 minutes), signed with
the same key. `JWTAuthentication` only accepts `token_type=access`, so neither
can be used as an access or refresh token. A challenge token allows five
wrong codes and is spent (its `jti` recorded in the shared cache with
`cache.add`) the moment it is exchanged for a JWT pair. An enrollment token is
accepted only by the enrollment endpoints, only while the user still has no
factor, and is spent when the first factor is activated.

`POST /auth/mfa/login/verify/` exchanges the challenge token plus a TOTP
code, a recovery code or a WebAuthn assertion for the JWT pair.

### 3. Second-factor time lives in the token (stateless step-up)

Tokens issued after a second factor carry `amr` (RFC 8176 values: `pwd`,
`otp`, `hwk`, plus `rec` for a recovery code) and `mfa_at` (Unix time of the
proof). SimpleJWT copies refresh claims into each new access token, so
**refreshing keeps the original `mfa_at`**: a 7-day refresh token never turns
into a fresh proof.

Sensitive endpoints call `mfa.stepup.require_recent_mfa(request)`. It passes
when `now - mfa_at <= MFA_STEP_UP_MAX_AGE_SECONDS` (default 600 s, the same
order as GitHub's "sudo mode"); otherwise it answers

```json
403 {"error": "...", "code": "mfa_step_up_required", "methods": ["totp", "webauthn", "recovery_code"], "max_age": 600}
```

`POST /auth/mfa/step-up/` verifies a factor and returns a new access token
with a new `mfa_at` (same `user_id`, `amr` extended); the refresh token is not
touched. The SPA's interceptor shows a dialog and retries the original call.

Endpoints behind step-up: organizer payment refund, approving a refund
request, booking refund, event cancellation, attendee CSV export, password
change, disabling 2FA, removing TOTP or a passkey, adding a factor when one
exists, regenerating recovery codes. For the money/data endpoints a user
*without* any factor gets `mfa_enrollment_required` (event team members are
not covered by the role rule but still must have 2FA to refund or export);
for password change an attendee who never enabled 2FA proceeds as before.

### 4. Enforcement by role, configurable for rollout

`MFA_REQUIRED_ROLES` (comma list of `organizer`, `staff`, `superuser`,
`attendee`; default `organizer,staff,superuser`). Such a user without a
factor gets only an enrollment token at login. `MFAJWTAuthentication` (the
API's authentication class) additionally rejects any access token without
`mfa_at` for a user who is required to have 2FA or has enabled it, with 401
`code: mfa_required` — this covers tokens minted before the user's role or
factors changed. The WebSocket JWT middleware applies the same rule.

An empty `MFA_REQUIRED_ROLES` turns enforcement off for a staged rollout;
users who enrolled keep being asked for their factor.

### 5. Django admin

`/admin/` keeps Django's password login, and `mfa.middleware.AdminMFAMiddleware`
sends every staff session that has not passed a second factor to
`/admin/mfa/verify/` (TOTP or recovery code, same lockout as the API). A staff
member who must have 2FA and has none is told to enroll in the app first. The
verified flag is bound to the session and user id; Django rotates the session
on login.

### 6. Secrets and verification details

- TOTP secrets are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256)
  under a key derived by HKDF-SHA256 from `MFA_ENCRYPTION_KEY`. A comma list
  enables rotation (first key encrypts, all decrypt). With `DJANGO_DEBUG=0`
  the settings refuse to start without a real key; a dev default exists only
  for DEBUG and tests.
- TOTP accepts the current step ±1 (clock drift) and **remembers the last
  accepted step** per device: a conditional `UPDATE ... WHERE last_used_step <
  step` makes a code (and any older one) single-use even under concurrency.
- All code comparisons use `hmac.compare_digest`.
- Enrollment creates an inactive TOTP device; it becomes active only after
  the first valid code.
- WebAuthn: RP ID and allowed origins from `WEBAUTHN_RP_ID` /
  `WEBAUTHN_ORIGINS`; challenges are random, stored in the cache for 5
  minutes and consumed on first use (`cache.delete` returns whether this
  caller removed it). The sign counter is stored; a non-increasing counter
  (when the authenticator keeps one) is refused and logged as a possible
  cloned authenticator. Attestation is `none` — we do not restrict
  authenticator models.
- Brute force: per-user lockout in the database (5 consecutive failures
  lock for 1 minute, doubling up to 1 hour; reset on success) plus DRF
  throttles per IP (`mfa_ip`) and per user (`mfa_user`). Only someone who
  already passed the password (login) or holds an access token (step-up)
  can reach these checks, so the lockout cannot be triggered anonymously.
- Audit: the `mfa` logger records enable/disable, recovery-code use, failed
  attempts, lockouts, clone warnings and admin resets — user id, method and
  client IP, never codes or secrets. Enabling or disabling 2FA, adding or
  removing a passkey and using a recovery code also create an in-app
  notification and an email (`jobs.handlers.enqueue_email`).
- Activating the first factor signs out all other sessions (their refresh
  tokens were obtained with the password only).

### 7. Recovery for locked-out users

`manage.py mfa_reset <username> --yes-i-verified-the-user` removes every
factor and recovery code, clears the lockout, revokes refresh tokens, logs
the reset and notifies the user. Without the flag it refuses. Identity
verification is a human process and is documented in `SECURITY_2FA.md`.

## Consequences

- Login for enrolled users becomes two round trips; the SPA hides it behind
  one screen. Organizers and admins must enroll at their first login after
  the release (the demo `organizer` included).
- A stolen access token (60 min) still works for non-sensitive calls; the
  step-up window limits damage on the sensitive ones to 10 minutes after the
  last proof.
- Passkeys need a secure context: `http://localhost` works, the plain-HTTP
  LAN IP of the demo does not (browsers refuse WebAuthn there and an IP can't
  be an RP ID). TOTP works everywhere.
- Changing `WEBAUTHN_RP_ID` (e.g. moving to a real domain) invalidates all
  registered passkeys; users fall back to TOTP or recovery codes.
- Losing `MFA_ENCRYPTION_KEY` disables every TOTP device (users fall back to
  passkeys / recovery codes or an admin reset). Keep it with the other
  secrets and rotate by prepending a new key.
- Tests that call sensitive endpoints authenticate with a token carrying
  `mfa_at` (`mfa.testing.mfa_access_token`).

## Out of scope

- Login with a passkey alone (usernameless / passwordless) — the password
  step stays.
- "Remember this device", trusted-device cookies.
- Session/device management UI and new-device login alerts (PLAN 4.1, next
  item).
- Passkeys in the Django admin (TOTP or recovery code there).
- Breached-password checks and payout-details protection (separate items).
- Hardware-attestation allow-lists (FIDO MDS).
- An email-change endpoint: the API has none today (email is read-only in
  `UserSerializer`); when one is added it must call `require_recent_mfa`.
