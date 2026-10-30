# Handoff: production roadmap status

Read this first when continuing the production-readiness work in a new session.

- **Branch:** `claude/laughing-lamport-n3z4dz` (all work below is pushed there; `main` has everything up to PR #2).
- **Full roadmap:** the owner keeps `PLAN.md` (Russian, 11 phases + 1Б). Ask for it if you need task-level detail; the summary below is enough to continue Phase 0.
- **Principle agreed with the owner:** everything at production level — no "minimal" variants.

## Working rules

- Conventional Commits (`feat(api): …`, `fix(…)`, `style`, `refactor`, `build`, `ci`, `docs`).
- Pin third-party versions that are at least two weeks old; pin GitHub Actions by commit SHA with the tag in a comment.
- Don't open a PR unless the owner asks. Verify before every push (tests, lint, schema, build).
- Project code and docs in English (`AGENTS.md`); talk to the owner in Russian.

## Phase 0 — engineering foundation

| Step | Status | Commits |
|---|---|---|
| 0.1 daphne → gunicorn + uvicorn workers, no ignored CVEs | done | `3ac2e64` |
| 0.3 `/api/v1`, deprecated `/api/` alias, OpenAPI contract, generated TS types, CI checks, `API contract` workflow | done | `109a61c`, `0c179a8` |
| 0.2 repo tooling | **in progress** | `19fe845` (ruff format), `f74feee` (lint fixes, full ruff rule set in CI) |
| 0.4 feature flags (self-hosted Unleash) | todo | — |

### 0.2 — what is left

1. **Frontend ESLint + Prettier** (`angular-eslint`). Commit the bulk Prettier reformat on its own and add its SHA to `.git-blame-ignore-revs`; fix lint findings in a separate commit; add both checks to the `frontend` CI job.
2. **`.pre-commit-config.yaml`** at the repo root:
   - `astral-sh/ruff-pre-commit` v0.17.1 (`38bfb07c0c64c304f47eb52090f8288150c77730`), args pointing at `EventHub/backend/pyproject.toml`;
   - `pre-commit/pre-commit-hooks` v6.0.0 (`3e8a8703264a2f4a69428a0aa4dcb512790b2c8c`): trailing whitespace, EOF, check-yaml/json, merge conflicts, private keys, large files;
   - `gitleaks/gitleaks` v8.30.1 (`83d9cd684c87d95d656c1458ef04895a7f1cbd8e`);
   - local hooks for ESLint/Prettier via `npx`.
3. **gitleaks in CI** (full-history scan on push/PR).
4. **PR title check** (Conventional Commits): `amannn/action-semantic-pull-request` v6.1.1 (`48f256284bd46cdaab1048c3721360e808335d50`).
5. **release-please**: `googleapis/release-please-action` v5.0.0 (`45996ed1f6d02564a971a2fa1b5860e934307cf7`), config + manifest, one product version (also bump `frontend/package.json`). The owner must enable *Settings → Actions → Allow GitHub Actions to create pull requests*.
6. **Renovate** `renovate.json`: groups (Angular, Django/DRF, GitHub Actions), digest pinning for actions, automerge patch updates on green CI, lock-file maintenance (`requirements*.lock` are built by `uv pip compile`, see their headers). The owner installs the Renovate GitHub App.
7. Pin the existing actions in `ci.yml` (`actions/checkout`, `setup-python`, `setup-node`, `upload-artifact`) by SHA.
8. Document for the owner the branch protection to enable on `main`: PR required, required checks (backend, frontend, docker, e2e, search-image, API contract, PR title, gitleaks).

## Next phases (summary of PLAN.md)

1. Payments: `PaymentProvider` layer (move Stripe into it), Freedom Pay provider + protocol-compatible **emulator** (CI/demo), method selection by currency, reconciliation job, missing Stripe events. Freedom Pay test credentials are pending (owner wrote to them). `freedompay.kz` is blocked by the cloud session's network policy.
1Б. Platform commission + **double-entry ledger** + organizer payouts (agency model, IBAN profile with 2FA-protected changes, weekly payouts, bank registry export, agent reports). Note: today `Event.service_fee_percent` is set by organizers — the platform commission must be admin-controlled.
2. Buyer emails (ticket + PDF, cancellation, refunds, reminders — `event_reminder` exists but is never sent), web push, SMS.
3. Legal & personal data (KZ law): offer, privacy policy, consents, data export/deletion, retention.
4. Security: TOTP + passkeys, tamper-evident audit log, SAST/DAST/Trivy/SBOM/cosign.
5. Infra: **Yandex Cloud kz1**, Terraform, Managed Kubernetes, Helm, Argo CD, canary (Argo Rollouts), preview envs, managed PostgreSQL (check pgvector), backups + restore tests, DR drills.
6. Observability: Prometheus stack, Loki, Tempo/OpenTelemetry, GlitchTip, SLOs (Sloth), runbooks, status page.
7. Load (k6) + chaos tests; 8. Product (i18n ru/kk/en, offline PWA scanner, Wallet); 9. Code quality; 10. Defense prep; 11. Product documentation (MkDocs, Diátaxis).

## Decisions already made (don't relitigate)

Transactional outbox in Postgres instead of Celery; no Kafka; Redis stays (channels, throttling, waiting room); uvicorn instead of daphne; API versioned under `/api/v1` with the committed `openapi.yaml` as the contract; Freedom Pay for KZT, Stripe for other currencies; Yandex Cloud kz1 for data residency.

## Verify locally

```bash
# Backend (PostgreSQL 16 + pgvector and Redis running)
cd EventHub/backend
export DJANGO_DEBUG=1
python manage.py test --noinput            # includes the schema drift test
ruff format --check . && ruff check .      # ruff==0.17.1
python manage.py makemigrations --check --dry-run
python manage.py spectacular --file openapi.yaml --validate --fail-on-warn   # after API changes

# Frontend
cd EventHub/frontend
npm run api:types && npm test && npm run build
E2E_BASE_URL=http://localhost:4200 npx playwright test   # against `docker compose up`
```
