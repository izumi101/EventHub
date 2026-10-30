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
| 0.2 repo tooling: ESLint + Prettier, pre-commit, gitleaks, PR title check, release-please, Renovate, SHA-pinned actions | done | `19fe845`, `f74feee`, then the 0.2 commits listed in `git log` (`build(frontend): add ESLint`, `style(frontend): format with prettier`, `ci: …`) |
| 0.4 feature flags (self-hosted Unleash, opt-in compose profile `flags`) | done | `feat(flags)`, `feat(frontend): feature flag service`, `docs: feature flags guide` — see `FEATURE_FLAGS.md` |

Phase 0 is complete. Next is **Phase 1 (payments)**.

### Owner actions still required (GitHub settings, cannot be done from code)

1. **Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests"** (release-please opens its release PR).
2. **Install the Renovate GitHub App** on the repository.
3. **Branch protection on `main`**: PR required; required checks: `backend`, `frontend`, `docker`, `e2e`, `search-image`, `API contract`, `PR title`, `gitleaks`, `pre-commit`. Renovate runs with `platformAutomerge`, which merges immediately if no checks are required; without branch protection set `platformAutomerge` to `false` in `renovate.json`.
4. PRs opened with the default `GITHUB_TOKEN` (release PRs) do not trigger other workflows; to run required checks on them, give release-please a PAT or GitHub App token via its `token` input.
5. First release: the repo has no tags. Tag the baseline `v1.0.0` after merging to `main` (or set `bootstrap-sha` in `release-please-config.json`), otherwise the first release PR walks the whole history.
6. Locally, once per clone: `pre-commit install` (hooks: ruff, whitespace/EOF/yaml/json, gitleaks, ESLint, Prettier, Conventional Commits) and `npm ci` in `EventHub/frontend`.

### Notes for later phases

- `requirements*.lock` are updated by Renovate as plain pins (its `pip-compile` manager cannot read `uv pip compile --python-platform` headers); regenerate with the command in the lock header after changing `requirements.txt` by hand.
- The `GITLEAKS_VERSION` and SHA-256 in `.github/workflows/gitleaks.yml` are not tracked by Renovate; bump them together with the pre-commit hook revision.
- `.gitleaks.toml` allowlists exactly one false positive (`LinkedinIcon` in `footer/brand-icons.ts`); never allowlist a real secret, rotate it.
- ESLint runs typed linting (`strictTypeChecked`); `.git-blame-ignore-revs` lists the bulk-format commits.
- Feature flags are opt-in locally (`COMPOSE_PROFILES=flags`, `UNLEASH_ENABLED=1`); the default stack and the e2e job do not start Unleash. Every flag has a safe default in `featureflags/registry.py` and an owner and removal date.

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
npm run lint && npm run format:check
npm run api:types && npm test && npm run build
E2E_BASE_URL=http://localhost:4200 npx playwright test   # against `docker compose up`
```
