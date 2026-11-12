# Freedom Pay gateway emulator

A standalone service that speaks the Freedom Pay (ex-PayBox) **Merchant API**
as specified in [`docs/payments/freedompay-protocol.md`](../docs/payments/freedompay-protocol.md)
("the spec"). EventHub's `FreedomPayProvider` is developed, tested in CI and
demoed against it with only `FREEDOMPAY_API_URL` changed. It is also the
gateway for failure-mode tests (circuit breaker, reconciliation).

It is **strict**: a client that gets the protocol wrong fails here the way it
would fail against the real gateway (bad signature: the real error codes;
unsigned or wrongly signed answers when a fault is injected; strict parsing of
the merchant's callback replies).

- Python 3.12, Starlette, Jinja2, httpx, uvicorn; SQLite (WAL) for all state.
- One process. State (payments, the callback retry schedule, the virtual clock,
  faults) is in `FPAY_DB_PATH` and survives restarts.
- No real card data: PANs are masked on entry, CVVs are never stored, logs are
  JSON and scrub anything that looks like a card number.

## Quick start

```bash
docker build -t fpay-emulator ./EventHub/fpay-emulator
docker run --rm -p 18080:8080 \
  -e FPAY_MERCHANTS=12345:my_test_secret \
  -e FPAY_PUBLIC_URL=http://localhost:18080 \
  fpay-emulator
curl -s localhost:18080/status/healthcheck   # {"status":"ok","time":"..."}
```

Locally without Docker (in this directory):

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.lock
FPAY_MERCHANTS=12345:my_test_secret .venv/bin/python -m fpay_emulator   # http://localhost:8080
```

Point the backend at it: `FREEDOMPAY_API_URL=http://localhost:18080` (or
`http://fpay-emulator:8080` inside compose), with the same merchant id and
secret as in `FPAY_MERCHANTS`.

## Merchant API (protocol endpoints)

All accept `POST` and `GET`; bodies as `application/x-www-form-urlencoded`
(recommended), `multipart/form-data`, `application/json` (string values), a GET
query string, or XML in the single form field `pg_xml` (root `<request>`).
PHP-style nesting (`pg_receipt_positions[0][name]`) is supported. Answers are
XML with HTTP 200, also for errors.

| Path | Script name signed | Notes |
|---|---|---|
| `/init_payment`, `/init_payment.php` | as called | all documented params; returns `pg_redirect_url` to this emulator's page |
| `/payment.php` | `payment.php` | browser form variant: 302 to the page, errors rendered as HTML |
| `/get_status3.php` | `get_status3.php` | element order like the real one (not alphabetical, `pg_sig` in the middle) |
| `/get_status2.php`, `/get_status.php` | as called | undocumented legacy aliases answering like `get_status3.php` (`FPAY_LEGACY_STATUS_ENDPOINTS`) |
| `/do_capture.php` | `do_capture.php` | two-step capture; one clearing per payment, a repeat returns it |
| `/cancel`, `/cancel.php` | as called | hold release or full refund |
| `/revoke`, `/revoke.php` | as called | full or partial refunds, `pg_idempotency_key` |
| `GET /status/healthcheck` | - | `{"status":"ok","time":...}` |

**Signature** (spec section 2): `md5(script ; sorted flattened values ; secret)`,
script = last path segment exactly as called, nested params flattened with the
`name + %03d position` rule. Every merchant call is verified; successful answers
are signed with the same script name; request errors are unsigned single-line
XML.

**Request error codes** (unsigned `pg_error_code`): `1100` no `pg_merchant_id`
(and a bad signature or unknown merchant on `get_status*.php`); `9998` unknown
merchant or bad/missing signature elsewhere; `94031` missing/invalid parameter
(also unknown payment on `revoke`, malformed JSON/XML body); `1200` status
without id; `11068` payment not found / other merchant (status); `9999` string
`pg_payment_id` in a JSON status request; `340` capture/cancel of an unknown,
unpaid or foreign payment (and revoke of a foreign one); `11074` clearing above
the amount; `110691` refund of an unsuccessful payment; `9014` refund after the
hold was released; `9994` refunds disabled; `11054` refund window passed;
`91021` / `91031` a refund / cancellation of the same payment is in progress;
`9908` duplicate `pg_order_id` (only with `FPAY_ORDER_ID_UNIQUENESS=reject`).

**Business declines** (signed, `pg_status=error`, `pg_failure_code`): cancel
`10033` already cancelled, `90131` not successful, `900811` partial refund or
partial clearing exists; revoke `900811` over the refundable remainder.
Declined refunds are listed in `pg_refund_payments` with status `error`.

**Money semantics**: `pg_payment_status` stays `success` after refunds and
cancellations. Refunds via `/revoke` appear as `pg_refund_amount` (negative,
two decimals) and `pg_refund_payments/pg_refund_payment[]`; cancellations
(and a merchant's `rejected` reply) as `pg_revoked_amount` and
`pg_revoked_payments/pg_revoked_payment[]`. `revoke` of an uncaptured two-step
payment captures the full amount first. Amounts are printed in their shortest
form (`100`, `482.5`), refund sums as `-20.00`; compare amounts as decimals.

## Hosted payment page

`/pay.html?customer=<uuid>` shows the merchant, description and amount, a card
form and one-click demo scenarios: **Pay (success)**, **Decline (insufficient
funds)**, **3-D Secure challenge** (second page, password `12345678`, Confirm or
Cancel), **Never answer** (stays `process` until the lifetime ends) and
**Abandon** (leave; the payment stays `waiting` and expires). Opening the page
moves `new` to `waiting`. A payment past its lifetime is unpayable and ends as
`error` with failure code `10018`.

Test cards (expiry 12/30, CVV 3 digits, cardholder at least two Latin words):

| Card | Outcome |
|---|---|
| `4716047261941981`, `4939770956154989`, `4111111111111111`, `6224466455690681278`, `623275279933273424`, `62528733472390953` | success |
| `4916307416334310` | 3-D Secure, then success (or `10004` with a wrong password) |
| `5335215945367703` 99999, `4916109830832246` 100066, `5548398681700148` 10009, `5475102935853613` 11036, `5555555555555557` 11024, `4444444444444422` 10001, `4444444411111111` 10022, `4444444499999999` 10018, `5484458131482832` 10004 | declined with that code |
| any other Luhn-valid card | `10005` in test mode, success when `FPAY_MERCHANT_TEST_MODE=0` |
| an expiry in the past | `10017` |

After the payment the buyer returns with `pg_success_url` / `pg_failure_url`
and their methods: `GET` (link), `POST` (button), `AUTOGET` (meta refresh after
`pg_timeout_after_payment` seconds, a plain 302 when it is `0`), `AUTOPOST`
(auto-submitted form). The success redirect carries `pg_order_id`,
`pg_payment_id`, your custom params, `pg_salt`, `pg_sig` (script = last path
segment of the success URL). The failure redirect carries `pg_order_id`,
`pg_payment_id`, `pg_failure_code`, `pg_failure_description` and your params,
**unsigned**.

## Callbacks to the merchant

- **Check** (`pg_check_url`, or the merchant default when omitted; an empty
  value disables it) is called before authorisation only when
  `FPAY_CHECK_ENABLED=1`. Anything but a valid signed `ok` (`rejected`,
  `error`, an invalid reply, non-200, no answer within
  `FPAY_CHECK_TIMEOUT_SECONDS`) declines the payment with
  `FPAY_REJECT_FAILURE_CODE` (and the merchant's `pg_description`).
- **Result** (`pg_result_url` or the merchant default) after success, decline
  and lifetime expiry, using `pg_request_method` (`POST` form, `GET` query
  appended to the URL, `XML` = POST with one field `pg_xml`), signed with the
  last path segment of the callback URL. Fields: `pg_order_id`,
  `pg_payment_id`, `pg_amount`, `pg_currency`, `pg_net_amount`,
  `pg_ps_amount`, `pg_ps_full_amount`, `pg_ps_currency` (success only),
  `pg_description`, `pg_result` (1/0), `pg_payment_date`, `pg_can_reject`,
  `pg_testing_mode`, `pg_captured`, user contact fields, `pg_payment_method`,
  card fields (masked PAN, expiry, owner, brand), `pg_reference`, your custom
  params, `pg_salt`, `pg_sig`.
- **Reply parsing** (`FPAY_REPLY_MODE=strict`, default): the reply must be
  HTTP 200 with a `<response>` document containing `pg_status`
  (`ok`/`rejected`/`error`), `pg_description`, `pg_salt` (echoing the request
  salt, see below) and a valid `pg_sig` for the same script name and secret.
  `lenient` accepts any HTTP 200.
- **Retries**: a non-200, a timeout, a connection error, an invalid reply (strict)
  or `error` is retried at `first_attempt + k * FPAY_RETRY_INTERVAL_SECONDS`
  while within `FPAY_RETRY_WINDOW_SECONDS` (defaults 1800/7200: attempts at 0,
  30, 60, 90 and 120 minutes), also after the lifetime has passed. Only the
  first attempt carries `pg_can_reject=1`; repeats carry the same business data
  with a new salt. `rejected` is honoured only with `pg_can_reject=1`: the
  payment is cancelled (`pg_revoked_*`) and the buyer is sent to the failure
  URL; otherwise it is logged as `rejected_ignored`. The schedule is stored in
  SQLite and resumes after a restart.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FPAY_MERCHANTS` | (required) | `id:secret[,id2:secret2]` (numeric ids; the secret may contain `:`) |
| `FPAY_MERCHANT_<id>_CHECK_URL` / `_RESULT_URL` / `_SUCCESS_URL` / `_FAILURE_URL` | none | merchant defaults used when the request omits the URL |
| `FPAY_MERCHANT_<id>_REQUEST_METHOD` | `POST` | default `pg_request_method` |
| `FPAY_MERCHANT_<id>_NAME` | `Merchant <id>` | name shown on the payment page |
| `FPAY_PUBLIC_URL` | `http://localhost:8080` | base of `pg_redirect_url` (what the browser can reach) |
| `FPAY_DB_PATH` | `fpay-emulator.sqlite3` (`/data/...` in the image) | SQLite file |
| `FPAY_HOST`, `FPAY_PORT` | `0.0.0.0`, `8080` | listen address |
| `FPAY_FORWARDED_ALLOW_IPS` | `127.0.0.1` | proxies trusted for `X-Forwarded-*` |
| `FPAY_COMMISSION_PERCENT` | `2.5` | fee that drives `pg_net_amount` / `pg_ps_full_amount` |
| `FPAY_COMMISSION_PAYER` | `merchant` | `merchant`: net = amount - fee; `client`: buyer pays amount + fee |
| `FPAY_TIMEZONE` | `Asia/Almaty` | zone of `pg_payment_date` (callbacks, refund entries) |
| `FPAY_DEFAULT_CURRENCY`, `FPAY_CURRENCIES` | `KZT`, `KZT,USD,EUR,RUB,UZS,KGS` | merchant currency and accepted `pg_currency` |
| `FPAY_MERCHANT_TEST_MODE` | `1` | merchant in test mode: every payment is a test one, only test cards work |
| `FPAY_AUTO_CLEARING_DEFAULT` | `1` | merchant default of `pg_auto_clearing` |
| `FPAY_AUTO_CAPTURE_DAYS`, `FPAY_AUTO_CAPTURE_ACTION` | `5`, `capture` | uncaptured two-step payments are captured/cancelled after N days (`0` = never) |
| `FPAY_AUTO_PROCESS_TEST_PAYMENTS` | `0` | test payments are not auto-processed (S10, S11) |
| `FPAY_LIFETIME_MIN_SECONDS` | `300` | lower clamp of `pg_lifetime` (default 86400, max 604800) |
| `FPAY_ORDER_ID_UNIQUENESS` | `off` | `off`, `return_existing`, `reject` (9908) |
| `FPAY_SALT_STRICT` | `1` | `pg_salt` must be Latin letters and digits |
| `FPAY_TAX_TYPES` | `0,3,7,11` | accepted receipt `tax_type` values |
| `FPAY_REFUNDS_ENABLED` | `1` | `0` answers 9994 |
| `FPAY_REFUND_WINDOW_DAYS` | `180` | 11054 after that (`0` = no limit) |
| `FPAY_CHECK_ENABLED` | `0` | call the Check URL |
| `FPAY_CHECK_TIMEOUT_SECONDS`, `FPAY_CALLBACK_TIMEOUT_SECONDS` | `30`, `30` | callback timeouts |
| `FPAY_REJECT_FAILURE_CODE` | `99999` | failure code of a Check refusal or a Result `rejected` |
| `FPAY_REPLY_MODE` | `strict` | `strict` or `lenient` reply parsing |
| `FPAY_REPLY_SALT_MUST_ECHO` | `1` | the reply's `pg_salt` must equal the request's |
| `FPAY_RETRY_ON_ERROR_REPLY` | `1` | a valid `error` reply is retried |
| `FPAY_RETRY_INTERVAL_SECONDS`, `FPAY_RETRY_WINDOW_SECONDS` | `1800`, `7200` | Result retry schedule |
| `FPAY_CALLBACK_SIGN_URL_QUERY` | `get_only` | URL query params of callback/success URLs enter the signature: `never`, `get_only`, `always` |
| `FPAY_RESULT_FAILURE_FIELDS` | `0` | send `pg_failure_code`/`_description` in failed Result calls |
| `FPAY_RESULT_ON_EXPIRY`, `FPAY_EXPIRY_PG_RESULT` | `1`, `0` | send a Result when the lifetime expires, with `pg_result` 0 or 2 |
| `FPAY_BAD_SIGNATURE_CODE`, `FPAY_STATUS_BAD_SIGNATURE_CODE` | `9998`, `1100` | error code for a bad signature / unknown merchant |
| `FPAY_LEGACY_STATUS_ENDPOINTS` | `1` | serve `get_status2.php` and `get_status.php` |
| `FPAY_JSON_STATUS_ID_MUST_BE_NUMBER` | `1` | 9999 for a JSON string `pg_payment_id` on status |
| `FPAY_3DS_PASSWORD` | `12345678` | 3-D Secure test password |
| `FPAY_CONTROL_ENABLED`, `FPAY_CONTROL_TOKEN` | `1`, none | control API on/off and its `X-Emulator-Token` |
| `FPAY_SCHEDULER_TICK_SECONDS` | `1` | background scheduler period |
| `FPAY_LOG_LEVEL` | `INFO` | JSON logs on stdout |

## Decisions on UNVERIFIED points of the spec

Where the spec says UNVERIFIED the emulator picks the behaviour a correct
client must survive anyway, and makes it switchable.

| Spec point | Default | Switch | Why |
|---|---|---|---|
| Bad signature code per endpoint (S8/S10 say 1100, live probe 9998) | 9998, but 1100 on `get_status*.php` | `FPAY_BAD_SIGNATURE_CODE`, `FPAY_STATUS_BAD_SIGNATURE_CODE` | matches the live probes; clients should treat both as an auth failure |
| `pg_lifetime` minimum (60 in S2, 300 in L2) | 300, out-of-range values clamped | `FPAY_LIFETIME_MIN_SECONDS` | a client must not rely on lifetimes shorter than 300 s |
| Does FP verify the reply XML / signature? | yes (strict) | `FPAY_REPLY_MODE` | a client that sends a sloppy reply fails here, not in production |
| Must the reply echo the request `pg_salt`? | yes | `FPAY_REPLY_SALT_MUST_ECHO` | echoing satisfies both readings |
| Retry on `error` replies, "non-200" vs "500" | every non-200 and `error` are retried | `FPAY_RETRY_ON_ERROR_REPLY` | exposes clients that do not answer repeats identically |
| Check/Result timeout (not published) | 30 s | `FPAY_CHECK_TIMEOUT_SECONDS`, `FPAY_CALLBACK_TIMEOUT_SECONDS` | |
| URL query params in the callback signature | included only for GET callbacks/redirects (they arrive in `$_GET`) | `FPAY_CALLBACK_SIGN_URL_QUERY` | use query-free callback URLs and POST, as the spec recommends |
| `pg_failure_code` in failed Result calls | not sent | `FPAY_RESULT_FAILURE_FIELDS` | clients must read the code from `get_status3.php` |
| `pg_ps_*` on failure | not sent | - | "may be missing on failure" (L2) |
| Result on lifetime expiry, `pg_result` value | sent, `pg_result=0` | `FPAY_RESULT_ON_EXPIRY`, `FPAY_EXPIRY_PG_RESULT=2` | clients must also handle `2` and the absence of a call |
| `pg_payment_date` time zone | `Asia/Almaty` (UTC+5); `get_status3` `pg_create_date` stays UTC `Z` | `FPAY_TIMEZONE` | a client must not assume UTC |
| `get_status2.php` / `get_status.php` | answer like `get_status3.php`, signed with their own script name | `FPAY_LEGACY_STATUS_ENDPOINTS` | live but undocumented |
| JSON: string `pg_payment_id` on status gives 9999 (S7) vs "all values as strings" (S1) | 9999 | `FPAY_JSON_STATUS_ID_MUST_BE_NUMBER` | use form encoding |
| `pg_order_id` uniqueness | off (duplicates allowed, status by order id returns the latest) | `FPAY_ORDER_ID_UNIQUENESS` | merchant setting |
| Test mode: auto-processed or admin-driven | processed by the page / control API; test payments never auto-captured | `FPAY_MERCHANT_TEST_MODE`, `FPAY_AUTO_PROCESS_TEST_PAYMENTS` | |
| 3DS test password (legacy L1) | `12345678` | `FPAY_3DS_PASSWORD` | |
| `tax_type` enum | current one: `0,3,7,11` | `FPAY_TAX_TYPES` | |
| Refund time window (180 days?) | 180 days (11054) | `FPAY_REFUND_WINDOW_DAYS` | |
| `revoke` vs `cancel` in `get_status3` lists | revoke: `pg_refund_*`; cancel and merchant `rejected`: `pg_revoked_*` | - | inferred from the field shapes in S7 |
| Failure code of a Check refusal / Result `rejected` | `99999` (none documented) | `FPAY_REJECT_FAILURE_CODE` | |
| Partial clearing then cancel | `900811` | - | S9 lists 900811 "cannot refund in full"; L4 also has 11072 |
| Query params on a POST URL | ignored (body only) | - | PHP would not mix them into `$_POST` |
| Test vs `test-api.` host, IP allow-list, callback source IPs | not emulated | - | contract questions for the manager |

## Control API (`/_emulator`)

JSON in and out. When `FPAY_CONTROL_TOKEN` is set every call needs the header
`X-Emulator-Token`. Disable the whole API with `FPAY_CONTROL_ENABLED=0`.
`{id}` is a `pg_payment_id` or the page's customer uuid.

```bash
E=http://localhost:18080/_emulator; H='X-Emulator-Token: change-me'; J='content-type: application/json'

curl -s -X POST -H "$H" $E/reset                                 # forget everything (ids are never reused)
curl -s -H "$H" "$E/payments?order_id=ORD-1&status=new&limit=10"  # list (also merchant_id)
curl -s -H "$H" $E/payments/1030000000001                         # full state, operations, callback jobs, delivery log
curl -s -X POST -H "$H" -H "$J" -d '{"scenario":"decline","failure_code":"10009"}' $E/payments/1030000000001/scenario
curl -s -X POST -H "$H" -H "$J" -d '{}' $E/payments/1030000000001/complete         # settle now (pre-set scenario or success)
curl -s -X POST -H "$H" -H "$J" -d '{"scenario":"3ds_fail"}' $E/payments/1030000000001/complete
curl -s -X POST -H "$H" $E/replay-callback/1030000000001          # re-send the Result call (pg_can_reject=0)
curl -s -X POST -H "$H" -H "$J" -d '{"advance_seconds":1800}' $E/clock   # move virtual time, then run due work
curl -s -H "$H" $E/clock                                          # {"now":..., "offset_seconds":...}
curl -s -X POST -H "$H" $E/tick                                   # run due expiries, auto-captures, retries now
curl -s -X POST -H "$H" -H "$J" -d '{"endpoint":"revoke","mode":"http_502","phase":"after","count":1}' $E/faults
curl -s -H "$H" $E/faults
curl -s -X DELETE -H "$H" $E/faults
```

Scenarios: `success`, `decline` (with `failure_code`, default 10009),
`3ds_success`, `3ds_fail` (10004), `hang` (status `process` until the
lifetime ends), `abandon` (status `waiting`). A pre-set scenario also decides
the outcome when a browser pays with any valid card (useful for browser e2e).
`complete` on a payment waiting in a 3-D Secure challenge finishes it.

Faults: `endpoint` is `init_payment`, `payment`, `get_status` (all three status
scripts), `do_capture`, `cancel`, `revoke`, `healthcheck` or `*`; optional
`count` (default unlimited) and `probability` (0..1]. Send one object or
`{"faults": [...]}`.

| `mode` | Effect |
|---|---|
| `http_500`, `http_502` | HTML error page with that status. `phase: "after"` processes the request first (the operation happened, the answer is lost: reconcile with `get_status3.php` by `pg_order_id`) |
| `timeout` | waits `latency_ms` (default 30000), then 504 |
| `latency` | waits `latency_ms` (default 1000) *inside* the operation, holding the payment's lock: a concurrent refund/cancel gets 91021/91031 |
| `drop` | aborts the TCP connection without an answer (`phase` as above) |
| `malformed_xml` | truncated, not well-formed XML with HTTP 200 |
| `unsigned_success` | the success answer without `pg_sig` (clients must treat it as an error, S1) |
| `wrong_signature` | the success answer with a wrong `pg_sig` |

## Tests

```bash
.venv/bin/python -m pytest -q                       # unit + full-flow suite (hermetic, ~10 s)
.venv/bin/python -m pytest -q --cov --cov-report=term-missing
uvx ruff@0.17.1 format --check . && uvx ruff@0.17.1 check .
```

The flow tests run the app in-process (httpx ASGI transport) and a real fake
merchant HTTP server on 127.0.0.1 (`tests/merchant.py`) that verifies the
emulator's signatures and answers with programmable replies.

### Contract suite (`contract_tests/`)

A separate suite that talks to a gateway **only over HTTP** with its own
independent signing code. It runs against the emulator in CI and, unchanged,
against the real Freedom Pay test API.

```bash
# Against the emulator (destructive steps are driven by the control API):
docker run -d --name fpay -p 18080:8080 -e FPAY_MERCHANTS=12345:contract_secret \
  -e FPAY_CONTROL_TOKEN=ctl-token fpay-emulator
FPAY_CONTRACT_BASE_URL=http://localhost:18080 FPAY_CONTRACT_MERCHANT_ID=12345 \
FPAY_CONTRACT_SECRET=contract_secret FPAY_CONTRACT_CONTROL_TOKEN=ctl-token \
  .venv/bin/python -m pytest contract_tests -v

# Against the real test API (merchant in test mode, real test credentials):
FPAY_CONTRACT_BASE_URL=https://api.freedompay.kz FPAY_CONTRACT_MERCHANT_ID=<id> \
FPAY_CONTRACT_SECRET=<payment key> .venv/bin/python -m pytest contract_tests -v
# ...add FPAY_CONTRACT_ALLOW_DESTRUCTIVE=1 and -s to also pay (by hand, in the
# browser link the test prints) and refund; FPAY_CONTRACT_MANUAL_TIMEOUT=300.
```

Without `/_emulator` and without `FPAY_CONTRACT_ALLOW_DESTRUCTIVE=1` the pay and
refund test is skipped; the read-only and error checks still run (they create
one unpaid test invoice). Never put real credentials in files; pass them in the
environment only.

## Regenerating the locks

```bash
uv pip compile requirements.txt --python-version 3.12 --python-platform x86_64-manylinux_2_28 --exclude-newer <date two weeks ago> -o requirements.lock
uv pip compile requirements-dev.txt --python-version 3.12 --python-platform x86_64-manylinux_2_28 --exclude-newer <date two weeks ago> -o requirements-dev.lock
```

## Not emulated

Payouts, recurring payments, Apple/Google Pay tokens, the payment frame mode
(`pg_payment_route=frame` is accepted and ignored), OFD fiscal receipts (the
positions are validated and stored only), currency conversion, IP allow-lists,
and several merchant processes (`9995`, `9996`, `9997` codes). The emulator is
single-process by design: run one replica per database file.
