# Freedom Pay (ex-PayBox) Merchant API: protocol specification for a provider module and a gateway emulator

Research date: 2026-10-31. Scope: the Kazakhstan **Merchant API** (hosted payment page) at `api.freedompay.kz`, formerly PayBox (`api.paybox.money`).

> **Do not confuse it with FreedomPay Inc. (freedompay.com, US/UK).** That company is unrelated and has a different API.

## 0. Sources and confidence legend

Every statement below carries a source tag. **UNVERIFIED** means no official source confirmed it. Those items are inference, plugin behaviour or open questions, and must be confirmed with the Freedom Pay manager before any money moves.

| Tag | Source | Kind |
|---|---|---|
| S1 | https://docs.freedompay.kz/overview-741636m0.md (Merchant API Overview: signature, formats, test cards, errors) | Official, current |
| S2 | https://docs.freedompay.kz/create-payment-11620859e0.md (Create payment, `init_payment`) | Official, current |
| S3 | https://docs.freedompay.kz/create-payment-in-a-payment-frame-45808278e0.md (payment frame, return of client) | Official, current |
| S4 | https://docs.freedompay.kz/result-notify-12007677e0.md (Result URL) | Official, current |
| S5 | https://docs.freedompay.kz/check-request-12007679e0.md (Check URL) | Official, current |
| S6 | https://docs.freedompay.kz/redirect-back-12108349e0.md (Success/Failure redirect) | Official, current |
| S7 | https://docs.freedompay.kz/get-payment-status-11620963e0.md (`get_status3.php`) | Official, current |
| S8 | https://docs.freedompay.kz/refund-payment-11621013e0.md (`revoke`) | Official, current |
| S9 | https://docs.freedompay.kz/cancel-payment-11621007e0.md (`cancel`) | Official, current |
| S10 | https://docs.freedompay.kz/capture-payment-clearing-11621002e0.md (`do_capture.php`) | Official, current |
| S11 | https://docs.freedompay.kz/overview-782024m0.md (Payments overview, statuses) | Official, current |
| S12 | https://docs.freedompay.kz/overview-935332m0.md (healthcheck, status page) | Official, current |
| L1 | https://freedompay.kz/docs-en/merchant-api/intro | Official, legacy docs site |
| L2 | https://freedompay.kz/docs-en/merchant-api/pay | Official, legacy |
| L3 | https://freedompay.kz/docs-en/merchant-api/after-pay | Official, legacy |
| L4 | https://freedompay.kz/docs-en/merchant-api/error-list | Official, legacy |
| L5 | https://freedompay.kz/docs-en/gateway-api/intro | Official, legacy (Gateway/G2G API) |
| L6 | https://freedompay.kz/docs/merchant-api/pay (RU version of L2) | Official, legacy |
| P1 | https://github.com/PayBox/cscart-paybox, files `app/payments/paybox/PG_Signature.php` and `app/payments/paybox.php` | Official vendor plugin (PayBox GitHub org) |
| P2 | https://github.com/PayBox/opencart-paybox, files `catalog/model/extension/payment/paybox.php` and `catalog/controller/extension/payment/paybox.php` | Official vendor plugin |
| P3 | WordPress plugin `freedompay-payment-gateway` 1.10.0 (author "FreedomPay", updated 2025-03-12), https://downloads.wordpress.org/plugin/freedompay-payment-gateway.1.10.0.zip, file `includes/class-wc-freedompay-payment-gateway.php` | Official vendor plugin, the most recent code found |
| P4 | https://github.com/PayBox/module-presta-shop, file `paybox/controllers/front/callback.php` | Official vendor plugin (old) |
| X | Live probes I ran on 2026-10-31 against `api.freedompay.kz` and `test-api.freedompay.kz`, using an unsigned or bogus request (`pg_merchant_id=1`). No credentials were used. | Observed behaviour |

Network notes: every site above was reachable and nothing was blocked. `https://docs.freedompay.kz/llms-full.txt` returns 404, but `/llms.txt` and the per-page `.md` exports work. No public Freedom Pay Postman collection was found. The WooCommerce and Bitrix repos under github.com/PayBox contain only a README.

---

## 1. Hosts, transport, formats

### 1.1 Base URLs
| Purpose | URL | Source |
|---|---|---|
| Production (KZ) | `https://api.freedompay.kz` | S2, S7, L1, L5 |
| Other countries | `https://api.freedompay.uz`, `https://api.freedompay.kg` | S2 (OpenAPI `servers`) |
| "Test server" | `https://test-api.freedompay.kz`. It is listed only in the Gateway API intro. | L5 |
| Staging (plugin debug mode only) | `staging-api.freedompay.kz` | P3. The name did not resolve from my network (X). |
| Legacy PayBox | `https://api.paybox.money`. It still answers but returned HTTP 403 for `/init_payment.php`. | P1, P2, X |
| Healthcheck | `GET https://api.freedompay.kz/status/healthcheck` returns `{"status":"ok","time":"…"}`. Status page: https://status.freedompay.kz/ | S12 |
| Hosted payment page (returned to you, never built by you) | e.g. `https://customer.freedompay.kz/pay.html?customer=<uuid>` | S2 |

**Test mode is a property of the merchant account, not of a host.** All new merchants start in test mode, where only test payment methods work. FreedomPay admins switch the merchant to working mode after the signed connection act. In working mode, `pg_testing_mode=1` makes one transaction a test (contact the manager first). While the merchant is still in test mode the flag is irrelevant (L1). `test-api.freedompay.kz` answers exactly like production for unauthenticated probes (X).
- UNVERIFIED: whether a test merchant should call `api.` or `test-api.`. Ask the manager.

### 1.2 HTTP
- Methods: POST or GET. POST is recommended because with GET the signature travels in the URL (S1).
- Request body formats accepted (S1):
  - `application/x-www-form-urlencoded`, nested as `pg_receipt_positions[0][name]=v`
  - `multipart/form-data`, same nesting
  - `application/json`, nested as JSON arrays
  - GET query string
  - XML in a single form field `pg_xml` with root `<request>`. Use another format if you have nested params.
- JSON caveat (S1): pass all values as strings, e.g. `"pg_amount": "100.50"`. A JSON number is normalised before the signature check (`100.50` becomes `100.5`), so the signature fails. Contradiction: S7 says `pg_payment_id` must be a JSON *number* for `get_status3.php`, and a string returns `9999`. **Recommendation: use `application/x-www-form-urlencoded` for every call**, which avoids both traps.
- Response: always XML, root `<response>`, `Content-Type: text/xml` (S1).
  - HTTP status is 200 for every API answer, including errors (S1, S2).
  - 403/404 with HTML means a wrong URL or a request blocked before the API (S1).
  - Any other status means the outcome is unknown. Query `get_status3.php` by `pg_order_id` before retrying (S1).
- Observed (X): the content type is `text/xml; charset=utf-8` on `init_payment`, `revoke`, `cancel` and `do_capture.php`, and `text/xml` on `get_status*.php`. The XML declaration is sometimes `UTF-8` and sometimes `utf-8`. Error responses are a single line without whitespace, e.g.
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <response><pg_status>error</pg_status><pg_error_code>9998</pg_error_code><pg_error_description>Некорректная подпись запроса</pg_error_description></response>
  ```
  An empty POST (no `pg_merchant_id`) returned `pg_error_code` `1100` with the description `<caller-ip> отсутствует в списке доверенных` ("is not in the trusted list"). This suggests an IP allow-list for merchant-to-API calls. UNVERIFIED: whether merchant server IPs must be registered. Ask the manager.

### 1.3 Script paths (endpoint names)
The script name enters the signature, so the path you call must match the name you sign (S1). Probes (X): each path below answered with XML error 9998 or 1100, so it exists, unless the table says otherwise.

| Operation | Current doc path | Legacy path (also live) | Sources |
|---|---|---|---|
| Create payment (server-to-server) | `/init_payment` (S2) | `/init_payment.php` (L2, S1 example, P3) | S1, S2, L2, X |
| Create payment via browser form | `/payment.php` (GET/POST, signed with `payment.php`; errors render as HTML) | same | S2, P1, P2, X |
| Payment status | `/get_status3.php` | `/get_status2.php` and `/get_status.php` still respond (X), but no current doc describes them. UNVERIFIED. | S7, L3, P4, X |
| Capture (clearing, two-step) | `/do_capture.php` | `/clearing.php` returned **403 (does not exist)** | S10, L3, X |
| Cancel (full) | `/cancel` | `/cancel.php` | S9, L3, X |
| Refund (full or partial) | `/revoke` | `/revoke.php` | S8, L3, X |
| Payouts | `reg2nonreg`, `reg2reg`, `to_iban`, `payment_status2`, `balance_status`. These are signed with the **payout key**, not the payment key. There is no `reg2nonacc`. | — | S1 |

---

## 2. Signature (`pg_sig`)

### 2.1 Algorithm (verified against docs and three vendor plugins)
1. **Script name**: the last segment of the URL path, from the last `/` to the end or to `?`. Use it exactly as in the URL, e.g. `init_payment.php` or `init_payment` (S1, L1, L5).
2. **Values** of all message parameters except `pg_sig`, ordered by parameter name ascending (byte-wise ASCII, PHP `ksort`) (S1, L1, P1, P2, P3).
   - `pg_salt` takes part like any other field (S1).
   - Your own extra parameters, including names without `pg_`, also take part (S1, L1).
   - A parameter added after signing breaks the signature (S1).
3. **Secret key** of the merchant appended last. Use the payment key for payment methods and the payout key for payout methods (S1).
4. Join with `;`, compute MD5, and send it as 32 lowercase hex characters in `pg_sig` (S1, L1).

Formula: `pg_sig = md5( script ; v(k1) ; v(k2) ; … ; secret_key )`, where `k1 < k2 < …` are the parameter names sorted.

Details:
- **Nested params** (`pg_receipt_positions[...]`, `pg_extra_params[...]`, XML child tags) are flattened recursively (S1 code, L2 code, P1, P2, P3).
  - Each key is renamed to `parentName + key + sprintf('%03d', position)`, where `position` is the 1-based index inside its parent in insertion order. List elements use the index (`0`, `1`, …) as the key.
  - The flat map is then sorted by these synthetic names. Siblings therefore sort by name inside their parent, and the nested values sit where the parent name sorts.
  - XML only: same-name tags keep document order (L1, P1 `makeFlatParamsXML`).
- **Empty values** are included as empty strings, which produces `;;`. All parameters are included and PHP `implode` keeps empty elements (P1, P2, P3 code). The docs do not single out empty values, so this is inferred from the algorithm.
- **Encoding**: MD5 over UTF-8 bytes. The PHP plugins hash the UTF-8 string, and the Python reference in S1 uses `.encode()`, which defaults to UTF-8.
- **Edge case (my own analysis, UNVERIFIED on the server)**:
  - Flatten-sort and plain-sort differ when one key is a prefix of another followed by digits. `pg_param1` and `pg_param10` sort plain as `[pg_param1, pg_param10]` but flattened as `[pg_param10002, pg_param1001]`.
  - Plain-key examples in S7–S10 use `ksort` on raw keys, while S1 uses the flatten version for everything.
  - **Avoid such key pairs.** `pg_param1..3` alone are safe.
- **Response signature**: Freedom Pay signs successful responses with the same rules, the same script name and the same key, over all `<response>` children except `pg_sig` (S1).
  - Error responses with `pg_error_code` are **unsigned** (S1, S2, S7–S10).
  - S1 says to treat any response without `pg_sig` as an error and never use it to confirm a payment or payout.
- **Callbacks** (Check/Result/Success) are signed with the script name equal to the last path segment of *your* callback URL. S3 says this explicitly for `pg_success_url`. P2 signs callbacks to `index.php?route=…` with `index.php`. P1 uses `basename(PHP_SELF)`.
  - P3 uses `''` (empty string) for a result URL `/?wc-api=…`. When the path ends in `/`, the script name is the empty string (P1 `getScriptNameFromUrl` returns `""`, P3 passes `''`).
  - **Recommendation: use callback URLs with a non-empty last segment, no trailing slash and no query string**, e.g. `https://shop.example/payments/freedompay/result`, which gives the script name `result`.
- **Our reply to a callback** must be signed with the same script name (the last segment of our URL) and our secret key, over all reply fields except `pg_sig` (P1 and P2 implement this; L2 shows the signed reply format).
  - `pg_salt` in the reply: P1's code comment says the reply must echo the request's `pg_salt`, but the docs show an arbitrary "random string". UNVERIFIED. Echoing the incoming salt is compatible with both.
- **Query parameters already present in the callback URL** (e.g. `?route=`):
  - P3 (POST) verifies over the request body only, which excludes URL query params, and succeeds in production.
  - P1 (GET) verifies over the whole `$_GET`, which includes the URL's own params.
  - UNVERIFIED whether Freedom Pay includes pre-existing query params when it signs. This is a further reason to use query-free callback URLs and `pg_request_method=POST`.

### 2.2 Cross-check: published doc examples reproduced with my own implementation
Script: a throwaway independent re-implementation, the same as the reference `flatten`/`make_sig` in §2.3, run with `python3 -I`. It was deleted after the run to keep the scratchpad to this one file. Doc secret key: `test_secret_key`. Output:

```
overview init_payment.php    expected=b9ad75871668ca040f80f5f6b530e6ed got=b9ad75871668ca040f80f5f6b530e6ed MATCH
    string: init_payment.php;100;KZT;Order #1001;12345;order_1001;a1b2c3d4;test_secret_key
create payment /init_payment expected=ffda750b3bbc6a3475ac5ac8a246f739 got=ffda750b3bbc6a3475ac5ac8a246f739 MATCH
    string: init_payment;100;Order #1001;12345;a1b2c3d4;test_secret_key
get_status3.php              expected=2586378f4f7d4ddd950fd1532eaf4fdd got=2586378f4f7d4ddd950fd1532eaf4fdd MATCH
    string: get_status3.php;12345;1022123803890;a1b2c3d4;test_secret_key
revoke                       expected=c9b6030e425d4d5a4d81cdb0ac09a4e5 got=c9b6030e425d4d5a4d81cdb0ac09a4e5 MATCH
    string: revoke;12345;1023122203651;a1b2c3d4;test_secret_key
cancel                       expected=e91d9a1ffcd55f0aeb3dc149651410ea got=e91d9a1ffcd55f0aeb3dc149651410ea MATCH
    string: cancel;12345;1023122203626;a1b2c3d4;test_secret_key
do_capture.php               expected=6904b1ae1e4017a4e1ba88732d8db7c8 got=6904b1ae1e4017a4e1ba88732d8db7c8 MATCH
    string: do_capture.php;12345;1023122203594;a1b2c3d4;test_secret_key
init_payment.php variant of case 2: 4b979c3439ac142b79dd8617dfb09d5c   <- the script name matters
```
Sources for the expected values: S1, S2, S7, S8, S10, S9 (in case order). The response-signature examples in S7–S10 do **not** verify with `test_secret_key` (e.g. revoke response gives `5b709d10…`, published `5aaac59d…`). They were evidently signed with a real merchant key, so they cannot be used as test vectors.

Independent implementations agree:
- the docs' PHP `makeFlatParamsArray` + `ksort` + `array_unshift(script)` + `array_push(secret)` + `md5(implode(';'))` (L2, L3, S1);
- the docs' Python `flatten`/`make_sig` (S1);
- vendor plugins P1 `PG_Signature::make`, P2 `make`/`prepare_send`, P3 `generate_signature`/`prepare_request_data`.

### 2.3 Worked examples for our own fixtures (computed, reproducible)
Callback to `https://shop.example/payments/freedompay/result` (script `result`), secret `demo_secret`:
```
params: pg_order_id=ORD-42, pg_payment_id=1022123803890, pg_amount=1500.00, pg_currency=KZT,
        pg_result=1, pg_can_reject=1, pg_testing_mode=1, pg_payment_date=2026-10-31 12:00:00, pg_salt=q1w2e3r4
string: result;1500.00;1;KZT;ORD-42;2026-10-31 12:00:00;1022123803890;1;q1w2e3r4;1;demo_secret
pg_sig: 1e007dc444f186ca0f4634232d97ea60
reply fields: pg_status=ok, pg_description=Order paid, pg_salt=z9y8x7
string: result;Order paid;z9y8x7;ok;demo_secret
pg_sig: a80a6a0f3c446ef59eb45060b1af5a4a
```
Nested receipt (`init_payment.php`, `test_secret_key`):
```
flat keys: pg_amount002, pg_description003, pg_merchant_id001, pg_receipt_positions0050001count001,
           pg_receipt_positions0050001name002, pg_receipt_positions0050001price004,
           pg_receipt_positions0050001tax_type003, pg_salt004
string: init_payment.php;900;Ticket;12345;1;Ticket A;900;0;a1b2c3d4;test_secret_key
pg_sig: 51c5bcf8ec3172c2e8a1c6a18d06a008
```
Reference implementation (S1, Python):
```python
def flatten(params, parent=''):
    flat = {}
    for i, (key, value) in enumerate(params.items(), 1):
        if key == 'pg_sig':
            continue
        name = f'{parent}{key}{i:03d}'
        if isinstance(value, dict):
            flat.update(flatten(value, name))
        elif isinstance(value, list):
            flat.update(flatten({str(j): v for j, v in enumerate(value)}, name))
        else:
            flat[name] = str(value)
    return flat

def make_sig(script, params, secret_key):
    flat = flatten(params)
    return hashlib.md5(';'.join([script] + [flat[n] for n in sorted(flat)] + [secret_key]).encode()).hexdigest()
```
Use a constant-time comparison when you verify (`hmac.compare_digest`).

---

## 3. `init_payment` (create payment)

`POST https://api.freedompay.kz/init_payment` or `/init_payment.php`. Sign with the script name that matches the path (S1, S2).

### 3.1 Request parameters
Source: S2, current OpenAPI, unless noted. "Old" means the legacy docs L2/L6.

| Param | Req | Type / limits | Notes |
|---|---|---|---|
| `pg_merchant_id` | yes | integer | Issued at connection |
| `pg_amount` | yes | number, 0.01 to 99999999, **up to 2 decimals, dot separator** | Amount in `pg_currency` |
| `pg_description` | yes | string, maxLength **1024** | Shown to the client. P1 truncates to 255; P2 to 1024 and strips special characters. |
| `pg_salt` | yes | string of Latin letters and digits | Random |
| `pg_sig` | yes | `^[0-9a-f]{32}$` | |
| `pg_order_id` | no in S2 (old L2: **required**) | string, maxLength 50 | Uniqueness can be enabled per merchant: then a repeat returns the existing payment (S2). Error 9908 "Payment with given order_id already exists" and 9991 "non-unique order id" exist (L4). **Always send it, and keep it unique.** |
| `pg_currency` | no | ISO 4217 alpha-3 (3 chars). Merchant currency if omitted. | Old: KZT, USD, EUR, converted at the Central Bank rate (L2) |
| `pg_check_url` | no | URI, max 255 | Called only if Freedom Pay enabled checks for the merchant. Omitted means the merchant setting; empty string means no check (L2). |
| `pg_result_url` | no | URI, max 255 | Omitted means the merchant setting. Old: empty string means no result notify (L2). |
| `pg_request_method` | no | `GET` / `POST` / `XML` | How FP calls check/result. Default is the merchant setting, by default POST. `XML` is a POST with one field `pg_xml` (root `request`). It does not affect the success/failure redirect. |
| `pg_success_url`, `pg_failure_url` | no | URI, max 255 | Browser return URLs |
| `pg_success_url_method`, `pg_failure_url_method` | no | `GET` / `POST` (button on the FP page), `AUTOGET` (302), `AUTOPOST` (auto-submitted form) | |
| `pg_state_url`, `pg_state_url_method` | no (old only) | | Page where the client waits for the payment system (L2) |
| `pg_site_url` | no (old only) | | Return link for offline payment systems (L2) |
| `pg_payment_system` | no (old only) | e.g. `EPAYWEBKZT` | Pre-selects a payment system (L2) |
| `pg_payment_method` | no | `bankcard` / `mobile_commerce` (S2). Old list (L2): `wallet`, `internetbank`, `other`, `bankcard`, `cash`, `mobile_commerce`. | Narrows the methods shown on the page |
| `pg_lifetime` | no | integer seconds, default 86400, max 604800. **Minimum: S2 says 60, old L2 says 300.** Out-of-range values are clamped (L2). | UNVERIFIED which minimum applies; use ≥300 |
| `pg_language` | no | `ru`, `en`, `kz`, `kg`, `uz` (S2); old: `ru`, `en` | |
| `pg_user_id` | no (required with recurring/frame per L2) | `^[a-zA-Z0-9_-]+$` | Must be unique per user, otherwise users see each other's saved cards (L6 warning) |
| `pg_user_phone` | no | digits with country code, e.g. `77777777777` | |
| `pg_user_contact_email` | no | email | FP sends status emails to it (L2) |
| `pg_user_ip` | no | IPv4/IPv6 | For fraud review |
| `pg_postpone_payment` | no (old only) | 0/1 | Requires an email (L2) |
| `pg_testing_mode` | no | 1 = test, 0 = merchant setting | See §1.1 |
| `pg_auto_clearing` | no | 1 one-step / 0 two-step. Default is the merchant setting. | Two-step: capture with `do_capture.php` or release with `cancel` |
| `pg_recurring_start`, `pg_recurring_lifetime` | no | 0/1; months 1–156 | Needs enabling by the manager |
| `pg_idempotency_key` | no | string, unique per merchant | A repeat returns the payment already created |
| `pg_generate_qr` | no | 1/0 | Returns `pg_redirect_qr` (Base64 PNG 300×300) |
| `pg_timeout_after_payment` | no | seconds, default 10 | Delay before the redirect back |
| `pg_3ds_challenge` | no (old only) | 1 = request the challenge flow; the issuer may ignore it | L2 |
| `pg_token_3ds` | no | 1/0 | Apple/Google Pay only (S2) |
| `pg_payment_route` | frame only | `frame` | Requires enabling; otherwise ignored (S3) |
| `pg_param1..3` | no | string | Stored with the payment |
| any non-`pg_` param | no | string | Echoed to check/result URLs and signed; names must be unique and must not start with `pg_` (S2, L2) |
| `pg_commission_discount*`, `pg_loyalty_*`, `pg_extra_params[...]` (government fees) | no | | Not relevant for EventHub |
| `pg_receipt_positions[...]` | no | see §8 | Fiscal receipt |

### 3.2 Response
Success (signed), from S2:
```xml
<?xml version="1.0" encoding="utf-8"?>
<response>
    <pg_status>ok</pg_status>
    <pg_payment_id>1022123803884</pg_payment_id>
    <pg_redirect_url>https://customer.freedompay.kz/pay.html?customer=01a164ba-258a-73d8-a674-dbca94c7f165</pg_redirect_url>
    <pg_redirect_url_type>need data</pg_redirect_url_type>
    <pg_salt>30mVYG1WPelmyIT6</pg_salt>
    <pg_sig>31ead9b4469cd81d377685be79fb6e66</pg_sig>
</response>
```
- `pg_payment_id` is an integer, observed with 13 digits. Store it as BIGINT or string.
- `pg_redirect_url_type` is `need data` (the client enters missing data) or `payment system`.
- `pg_redirect_qr` is present only with `pg_generate_qr=1`.

Error (unsigned, HTTP 200), from S2:
```xml
<response><pg_status>error</pg_status><pg_error_code>1100</pg_error_code><pg_error_description>…</pg_error_description></response>
```

---

## 4. Callbacks to the merchant

### 4.1 Check URL (pre-authorisation order validation)
Called only if Freedom Pay enabled it for the merchant ("contact your manager"). When check URLs are empty or missing at init and in the settings, the step is skipped and the merchant is considered to accept (S5, L2).
- No answer within the time limit counts as a refusal (S5). UNVERIFIED: the timeout value is not published.
- The endpoint must be public, without auth (S5).

Request fields (form, or GET/XML per `pg_request_method`), from S5 and L2:

| Field | Required | Notes |
|---|---|---|
| `pg_order_id` | * | string ≤50 |
| `pg_payment_id` | * | integer |
| `pg_amount` | * | same as init |
| `pg_currency` | * | same as init |
| `pg_ps_amount` | * | amount in the payment system currency |
| `pg_ps_currency` | * | may be absent on failure |
| `pg_ps_full_amount` | * | amount the buyer pays including fees |
| your non-`pg_` params | | echoed |
| `pg_salt` | * | |
| `pg_sig` | * | |

Reply (XML, signed): `pg_status` = `ok` (accept), `rejected` (refuse) or `error` (could not interpret), plus `pg_description`, `pg_salt` and `pg_sig`.
```xml
<?xml version="1.0" encoding="utf-8"?>
<response>
    <pg_status>ok</pg_status>
    <pg_description>Payment allowed</pg_description>
    <pg_salt>random string</pg_salt>
    <pg_sig>…</pg_sig>
</response>
```

### 4.2 Result URL (payment result notification)
Called by the FP server after success or failure, using `pg_request_method` (S4, L2). Must be public, without auth (S4).

Request fields, from S4 (marked * = required in S4) with additions from L2/L6:

| Field | Notes |
|---|---|
| `pg_order_id`* | |
| `pg_payment_id`* | |
| `pg_amount`*, `pg_currency`* | invoice amount and currency |
| `pg_net_amount`* | example 482.5; amount net of fees |
| `pg_ps_amount`*, `pg_ps_full_amount`*, `pg_ps_currency`* | may be missing on failure (L2) |
| `pg_description`* | |
| `pg_result`* | **1 = success, 0 = failure, 2 = not completed** |
| `pg_payment_date`* | `YYYY-MM-DD HH:MM:SS`; the time zone is not stated (UNVERIFIED) |
| `pg_can_reject`* | 1 = the payment can be rolled back by answering `rejected` |
| `pg_testing_mode`* | 1 = test |
| `pg_captured` | card success only; 0 = two-step, capture pending |
| `pg_user_phone`, `pg_user_contact_email`, `pg_need_email_notification` | |
| `pg_payment_method` | e.g. `bankcard` |
| `pg_card_pan` (masked, e.g. `5483-18XX-XXXX-0293`), `pg_card_exp`, `pg_card_owner`, `pg_card_brand` (e.g. `VI`), `pg_card_token`, `pg_card_id` (deprecated) | card fields |
| `pg_reference` | RRN; appears in the RU example (L6) |
| `pg_discount_percent`, `pg_discount_amount` | only when a discount applies |
| `pg_recurring_profile_id` | recurring payments (S2) |
| your non-`pg_` params | echoed |
| `pg_salt`*, `pg_sig`* | |

UNVERIFIED for the result callback: `pg_failure_code`, `pg_failure_description` and `pg_auth_code`. They are documented only in `get_status3` (S7) and the frame failure redirect (S3), not in the S4 field list. Treat them as optional.

Reply semantics (S4, L2):
- `ok`: accepted.
- `rejected`: refuse the payment. This is allowed **only if the request had `pg_can_reject=1`**; otherwise the payment counts as completed whatever you answer. `pg_description` is shown to the buyer, and on reject the buyer goes to the Failure URL.
- `error`: the merchant could not interpret the data.

Retries (S4, L2, L6):
- If the merchant is unreachable or answers non-200, FP retries **every 30 minutes for 2 hours**, even after `pg_lifetime` expires. The RU legacy page in one place says "status 500" instead of "not 200".
- After a failed first attempt the payment is not cancelled, and later calls **do not allow refusing**.
- The merchant must expect repeated calls for the same payment and **must answer repeats identically** to the first answer.

Observed in the official plugin (P3): it replies with plain text `Request was processed.` and HTTP 200, not XML, and it accepts JSON or form bodies (it checks whether the body starts with `{`). UNVERIFIED whether FP validates the reply XML or signature, and whether it ever sends JSON. **Implement the documented signed XML reply anyway.**

Source IP ranges for FP callbacks: **none published** in any official source I found. UNVERIFIED. Rely on the signature plus `get_status3` confirmation (§9).

### 4.3 Success / Failure redirect (browser)
- The redirect uses `pg_success_url_method` or `pg_failure_url_method`. With GET, `pg_order_id`, `pg_payment_id` and your custom params are appended to any existing query string (S6, L2).
- Success carries `pg_order_id`, `pg_payment_id`, `pg_salt` and `pg_sig`, signed with the script name equal to the last path segment of `pg_success_url` (S3).
- Failure carries `pg_order_id`, `pg_failure_code`, `pg_failure_description` and your params. **These are not signed** (S3). L2 lists `pg_error_code` and `pg_error_description` for the failure URL.
- **Never fulfil an order from the redirect alone.** Result URL plus status is the source of truth (S6, L2).

---

## 5. Payment status: `get_status3.php`

`POST https://api.freedompay.kz/get_status3.php`, signed with the script `get_status3.php`, which S7 and my vector confirm.
- Doc defect: the legacy L3 curl comment signs with `get_status.php` and includes `pg_order_id`, while its PHP code uses `get_status3.php`. Follow S7.

Request (S7):

| Field | Req | Notes |
|---|---|---|
| `pg_merchant_id` | yes | |
| `pg_payment_id` | one of | Takes precedence (L3). In JSON it must be a number (S7). |
| `pg_order_id` | one of | Returns the **latest** payment with that order id (S7). Use it when the `init_payment` response was lost. |
| `pg_salt`, `pg_sig` | yes | |

Response fields (S7):
- Always present: `pg_status` (ok/error), `pg_payment_id`, `pg_payment_status`, `pg_currency`, `pg_amount`, `pg_clearing_amount`, `pg_captured`, `pg_can_reject`, `pg_payment_method` (`none` if not chosen yet), `pg_create_date`.
- `pg_create_date` is UTC `YYYY-MM-DDThh:mm:ssZ` in S7, but `YYYY-MM-DD HH:MM:SS` in the L3 example.
- Optional: `pg_testing_mode` (only for test payments), `pg_refund_amount` (negative, 2 decimals, e.g. `-20.00`), `pg_revoked_amount` (negative), `pg_payment_system`, `pg_accepted_payment_systems`, `pg_reference` (RRN), `pg_card_pan`, `pg_card_name`, `pg_auth_code`, `pg_card_token`, `pg_card_id`, `pg_user_phone`, `pg_user_email`, `pg_failure_code`, `pg_failure_description`, `pg_recurring_profile_id`, `pg_recurring_profile_expiry_date`, and nested lists:
  - `pg_refund_payments/pg_refund_payment[]` with `pg_payment_id`, `pg_payment_status` (success/process/error), `pg_amount` (negative), `pg_payment_date`, `pg_reference`, and `pg_failure_*` on decline.
  - `pg_revoked_payments/pg_revoked_payment[]` with `pg_payment_id` and `pg_payment_status`.
- **Element order in the real XML is not alphabetical**, e.g. `pg_salt` appears mid-document (S7 examples). The verifier must sort and must not rely on document order. Nested lists must be flattened per §2.1.

Payment statuses (`pg_payment_status`) (S7, S11):

| Status | Meaning | Final? |
|---|---|---|
| `new` | created, the client has not paid | no |
| `waiting` | waiting for the client | no |
| `process` | processing, including 3DS | no |
| `success` | authorised. **Cancelled or refunded payments KEEP `success`**: inspect `pg_captured`, `pg_refund_amount`, `pg_revoked_amount` and the lists. | yes |
| `error` | declined; see `pg_failure_code` | yes |

Legacy statuses (`pg_transaction_status`: `partial` (new), `pending`, `ok`, `failed`, `incomplete` (lifetime expired)) appear only for the card/direct saved-card method (L6) and old `get_status.php` usage (P4). Do not use them with `get_status3`.

Errors (S7):
- `1200`: neither id passed.
- `11068`: not found, or the payment belongs to another merchant.
- `9999`: string `pg_payment_id` in JSON, or an internal error.
- Invalid signature: **`1100` on `get_status*.php`** (X: "Некорректная подпись запроса"), not 9998.

Example declined (S7, abbreviated):
```xml
<response><pg_status>ok</pg_status><pg_payment_id>1022123803892</pg_payment_id><pg_can_reject>0</pg_can_reject>
<pg_testing_mode>1</pg_testing_mode><pg_currency>KZT</pg_currency><pg_amount>100</pg_amount>
<pg_payment_method>bankcard</pg_payment_method><pg_captured>0</pg_captured><pg_create_date>2026-10-22T17:48:38Z</pg_create_date>
<pg_salt>…</pg_salt><pg_sig>…</pg_sig><pg_payment_status>error</pg_payment_status><pg_reference>261022174839</pg_reference>
<pg_clearing_amount>0</pg_clearing_amount><pg_failure_code>99999</pg_failure_code>
<pg_failure_description>Неизвестная ошибка платежной системы</pg_failure_description></response>
```

---

## 6. Capture, cancel and refund

### 6.1 Capture: `do_capture.php` (two-step only)
- Request (S10): `pg_merchant_id`, `pg_payment_id`, optional `pg_clearing_amount` (≤ the payment amount, 2 decimals, extra digits dropped; omitted or 0 means the full amount), `pg_salt`, `pg_sig`. L3 marks `pg_clearing_amount` required.
- Response (signed): `pg_status=ok`, `pg_amount`, `pg_clearing_amount`, `pg_salt`, `pg_sig`.
- **`ok` with `pg_clearing_amount=0` means nothing was captured.** Check the status.
- Only one clearing per payment; the remainder is released. A repeat returns the earlier captured amount.
- If neither capture nor cancel happens within 5 days (configurable; L3 says 1 to 5 days), FP auto-captures or auto-cancels per the merchant setting. **Test payments are not auto-processed** (S10, S11).
- Errors: `340` (not found, unpaid or not a card payment), `1100` (bad signature).

### 6.2 Cancel: `/cancel` (or `cancel.php`), full amount only
- Request (S9): `pg_merchant_id`, `pg_payment_id`, optional `pg_idempotency_key`, optional `pg_receipt_positions[...]`, `pg_salt`, `pg_sig`.
- Semantics:
  - Not-yet-captured two-step payment: the hold is released (reversal).
  - Captured payment: a full refund.
  - After a **partial** clearing, cancel is impossible; use refund instead.
  - Legacy L3 described `cancel.php` as cancelling an *unpaid invoice*. The current S9 semantics supersede that.
- Response (signed): `pg_status` (`ok`/`error`), `pg_cancel_payment_id`, `pg_failure_code`/`pg_failure_description` on decline, `pg_salt`, `pg_sig`.
- Request-level errors (unsigned): `94031`, `1100`, `340`, `9994` (disabled), `91021`/`91031` (refund or cancel already in progress).
- Failure codes: `10033` (already cancelled), `90131` (not successful), `900811` (cannot refund in full).

### 6.3 Refund: `/revoke` (or `revoke.php`), full or partial
- Request (S8): `pg_merchant_id`, `pg_payment_id`, optional `pg_refund_amount` (0 to 99999999; omitted or 0 means **the whole remaining amount**), optional `pg_idempotency_key` (a repeat does not refund again), optional `pg_receipt_positions[...]`, `pg_salt`, `pg_sig`.
- Semantics:
  - Partial refunds can repeat until the total equals the payment amount (S8, L3).
  - For a two-step payment that is not captured, `revoke` **captures the full amount first, then refunds**. Use `cancel` to release a hold instead (S8).
- Response (signed): `pg_status` (`ok` = refunded, `error` = declined), `pg_revoke_payment_id`, `pg_failure_code`, `pg_failure_description`, `pg_salt`, `pg_sig`.
  ```xml
  <response><pg_status>ok</pg_status><pg_revoke_payment_id>1023122203652</pg_revoke_payment_id><pg_salt>bMhAv91iYM9vq7sg</pg_salt><pg_sig>5aaac59d657cc4b381367cef68d99a16</pg_sig></response>
  ```
- Request-level errors (unsigned):
  - `94031`: bad param, negative amount or unknown payment.
  - `1100`: bad signature per S8; the live probe returned 9998 for an unknown merchant (X).
  - `340`: another merchant's payment.
  - `110691`: payment not successful.
  - `9014`: two-step payment not capturable, or cancelled.
  - `9994`: refunds disabled.
  - `91021`: refund already in progress.
- Failure code `900811`: amount greater than the refundable remainder, or already fully refunded.
- **Status after a refund:** `pg_payment_status` stays `success`. Read `pg_refund_amount` (negative cumulative) and `pg_refund_payments` (S7).
- Time window: no explicit rule is documented. Error `11054` "more than 180 days have passed since this transaction" exists (L4), which suggests a 180-day limit. UNVERIFIED as a contractual rule.

---

## 7. 3-D Secure, test mode, test data
- 3DS happens entirely on the FP payment page or frame: FP redirects the client to the issuer and completes authorisation (S2, S3 sequence diagrams).
  - The merchant sees `pg_payment_status=process` during 3DS (S7), then the Result URL.
  - 3DS failure codes include `10004`, `11037`, `11049`, `11053`, `8889` (L4).
- `pg_3ds_challenge=1` (old L2) requests a challenge; the issuer may ignore it.
- `pg_testing_mode`: 1 = test transaction (S2, L1). Result callbacks and `get_status3` carry `pg_testing_mode=1` for test payments (S4, S7).
- Legacy (L1): test transactions are not progressed automatically; you drive them with test buttons in the admin panel. The current S1 card table implies real simulated processing. UNVERIFIED which behaviour a test merchant gets.
- Test cards (S1; expiry 12/30 for all; CVV not stated in S1, the RU legacy page shows `123`):
  - Purchase:
    - Success, capture and refund work: `4716047261941981` (no 3DS).
    - Success with 3DS: `4916307416334310`.
    - Cancel-before-capture works: `4939770956154989`.
    - All operations work: UnionPay `6224466455690681278`, `623275279933273424`, `62528733472390953`.
  - Decline:
    - `5335215945367703` gives 99999.
    - `4916109830832246` gives 100066.
    - `5548398681700148` gives 10009.
    - `5475102935853613` gives 11036.
    - `5555555555555557` gives 11024.
    - `4444444444444422` gives 10001.
    - `4444444411111111` gives 10022.
    - `4444444499999999` gives 10018.
    - `5484458131482832` gives 10004.
  - Payment frame: `4111111111111111` success without 3DS, `4916307416334310` success with 3DS, `5335215945367703` declined (S3).
- 3DS test password `12345678` comes from legacy L1 (with an outdated 2024/12 card list). UNVERIFIED for the current cards.
- Cardholder name must be at least 2 Latin words (L1).
- Mobile test phones: `+77017777777`, `+77027777777`, `+77037777777`, `+77047777777`, OTP `111111` (S1, L1).

---

## 8. Fiscalisation (OFD receipts)
- `pg_receipt_positions[i][...]` on `init_payment`, `cancel` and `revoke` (S2, S8, S9). Fields:
  - `count` (number, required per position)
  - `name` (required)
  - `price` per unit (required)
  - `tax_type`
  - `unit_code` (e.g. 796)
  - `gtin`
  - `ntin` (KZ national catalogue)
  - `mark_list[]` (marking codes; one per unit, count must match)
- **`tax_type` enum conflict:**
  - Current S2/S8/S9: `0` without tax, `3` VAT 16/116, `7` VAT 10/110, `11` VAT 5/105. Omitted means the merchant fiscal setting.
  - Legacy L2/L3: 0 none, 1 VAT 0%, 2 12%, 3 12/112, 4 18%, 5 18/118, 6 10%, 7 10/110, 8 20%, 9 20/120.
  - UNVERIFIED which applies to our merchant; confirm with the manager.
- Alternative structure: the official WP plugin (P3) sends `pg_receipt` with `receipt_format=kz_1_0`, `customer.email` and `positions[]` holding `quantity`, `name`, `price`, `vat_code` (`vat_0`, `vat_12`, …) and `discount`. This is not documented on the docs site. UNVERIFIED.
- Nested receipt params take part in the signature via the flattening of §2.1.

---

## 9. Security notes and recommended verification
- MD5 with the secret appended (not HMAC) is a weak MAC. It is what the protocol mandates (S1, L1).
  - Never trust a callback on its signature alone. Re-confirm with a signed `get_status3.php` (outbound, over TLS, to a pinned host) before fulfilment. S6 and L2 recommend Result URL plus status over the redirect, and S1 recommends status queries whenever the outcome is unknown.
  - Check `pg_amount` and `pg_currency` against the stored order, and check that `pg_payment_id` matches the one from `init_payment`.
  - Use constant-time comparison.
  - Reject responses without `pg_sig` as unconfirmed (S1).
  - Treat the failure redirect as untrusted (unsigned, S3).
  - Make Result processing idempotent and answer repeats identically (S4).
  - Use `pg_idempotency_key` on init, cancel and refund (S2, S8, S9).
  - Never log the secret key.
- Field values containing `;` are joined raw, so field boundaries are ambiguous. Keep merchant-controlled values free of `;` (my analysis).
- Callback URLs must be public without auth (S4, S5). No FP source IP list is published (UNVERIFIED), so an IP allow-list cannot be relied on.
- Separate keys: the payment key and the payout key (S1).

## 10. Error codes relevant to the emulator
- **Generic (S1):**
  - `9998`: missing or invalid signature, or unknown merchant; unsigned.
  - `1100`: `pg_merchant_id` not passed.
  - `94031`: missing or invalid parameter.
- **Observed (X):**
  - Empty POST: `1100` "<ip> not in the trusted list".
  - Bogus merchant with a bad signature on `init_payment`, `revoke`, `cancel`, `do_capture.php`: `9998`.
  - The same on `get_status*.php`: `1100`.
- **Legacy L1** says the unsigned "merchant not identified" code is `101`, and L5 says `9998`. 9998 is what the live API returns.
- **Directory (L4):**
  - Request and configuration errors:
    - 9992: method not enabled
    - 9993: URL not specified
    - 9994: action disabled
    - 9995: payment in test mode
    - 9996: contract
    - 9997: invalid merchant id
    - 9998: invalid signature
    - 9999: system error
  - Payment declines:
    - 10000: service unavailable
    - 10001: contact issuer
    - 10004: 3DS
    - 10005: card data
    - 10009: insufficient funds
    - 10017: card expired
    - 10018: lifetime expired
    - 10020: refund exceeds amount
  - Cancel, refund and clearing errors:
    - 10033: already cancelled
    - 10034: refund needs clearing
    - 10035: cannot clear an unsuccessful payment
    - 10036: already cleared
    - 11017: already cancelled
    - 11018: already refunded
    - 11054: older than 180 days
    - 11068: payment not found
    - 11072: cancel impossible, clearing was done
    - 11074: clearing amount exceeded
    - 11090: clearing after cancel
  - Order id: 9908 and 9991 (duplicate order id).
  - Other: 99999 unknown payment-system error. L4 has the full list.

## 11. Protocol versions: differences that matter
| Aspect | Legacy (freedompay.kz/docs-en, PayBox) | Current (docs.freedompay.kz) |
|---|---|---|
| Paths | `*.php` (`revoke.php`, `cancel.php`) | `/init_payment`, `/revoke`, `/cancel`, plus `get_status3.php`, `do_capture.php`. Both styles are live (X); the signed script name must match the path. |
| Status API | `get_status.php` (`pg_transaction_status`) | `get_status3.php` (`pg_payment_status` new/waiting/process/success/error) |
| `pg_order_id` | required | optional (but recommended) |
| `pg_lifetime` min | 300 s | 60 s |
| tax_type | 0–9 (VAT 12/18/10/20) | 0, 3 (16/116), 7, 11 |
| Unsigned error code | 101 (L1) / 9998 (L5) | 9998 / 1100 / 94031 |
| JSON body | not mentioned | supported, all values as strings |
| `cancel` semantics | cancel an unpaid invoice | full reversal or refund of a successful payment |
| Idempotency | none | `pg_idempotency_key` |

## 12. Open questions for the merchant contract / manager
1. Test environment: which base URL for a test-mode merchant (`api.` or `test-api.`)? Will we get a sandbox merchant id and key? Are test payments auto-processed or driven from the admin panel?
2. Must our server IPs be registered? The live API answered "not in the trusted list" (1100) to an anonymous POST.
3. FP outbound callback IP ranges, the check/result timeout, and the exact retry schedule. The docs say every 30 minutes for 2 hours; is it non-200 or 5xx only?
4. Does FP verify the signature of our check/result XML reply? Must the reply echo the request `pg_salt`?
5. Is Check URL enabled for us? (Needed to reject sold-out seats before charge; otherwise use `pg_can_reject` plus `rejected` on result, which works only for `pg_can_reject=1` and only on the first delivery.)
6. Is `pg_order_id` uniqueness enforcement enabled on our merchant?
7. One-step vs two-step (`pg_auto_clearing`) default, and the auto-capture/cancel period.
8. Refund time window (180 days?), partial-refund limits, and whether refunds are enabled (`9994`).
9. Fiscalisation: which `tax_type` enum, `pg_receipt_positions` vs `pg_receipt` (`kz_1_0`), and whether FP issues the OFD receipt for us.
10. Time zone of `pg_payment_date` in callbacks. (`get_status3` dates are UTC with `Z`.)
11. Allowed currencies for our merchant (KZT only?) and amount limits.
12. Whether `pg_failure_code`/`pg_failure_description` are sent to the Result URL on `pg_result=0`.
