"""Error and failure codes (spec sections 5, 6 and 10).

Two kinds exist in the protocol:

* **request errors** (``pg_error_code``): the call was refused before any
  business processing. Answered as an *unsigned* ``<response>`` with
  ``pg_status=error`` and HTTP 200;
* **failure codes** (``pg_failure_code``): a business operation was attempted
  and declined (card declined, refund over the remainder, ...). They appear in
  signed answers, in ``get_status3.php`` and in the failure redirect.
"""

from __future__ import annotations

# Request errors.
MERCHANT_ID_MISSING = '1100'  # also: bad signature on get_status*.php (X)
BAD_SIGNATURE = '9998'  # also: unknown merchant (S1, X)
INVALID_PARAMETER = '94031'
STATUS_ID_MISSING = '1200'
PAYMENT_NOT_FOUND = '11068'
CAPTURE_NOT_POSSIBLE = '340'  # not found, unpaid or other merchant's payment
SYSTEM_ERROR = '9999'
ACTION_DISABLED = '9994'
DUPLICATE_ORDER_ID = '9908'
REFUND_IN_PROGRESS = '91021'
CANCEL_IN_PROGRESS = '91031'
REFUND_NOT_SUCCESSFUL = '110691'
REFUND_NOT_CAPTURABLE = '9014'
CLEARING_AMOUNT_EXCEEDED = '11074'
TOO_OLD = '11054'

REQUEST_ERROR_TEXT = {
    MERCHANT_ID_MISSING: 'Merchant is not identified: pg_merchant_id is required',
    # Verbatim text observed on the live API (spec section 1.2).
    BAD_SIGNATURE: 'Некорректная подпись запроса',
    INVALID_PARAMETER: 'Invalid or missing parameter',
    STATUS_ID_MISSING: 'Either pg_payment_id or pg_order_id is required',
    PAYMENT_NOT_FOUND: 'Payment not found',
    CAPTURE_NOT_POSSIBLE: 'Payment not found, not paid or not available for this operation',
    SYSTEM_ERROR: 'System error',
    ACTION_DISABLED: 'This action is disabled for the merchant',
    DUPLICATE_ORDER_ID: 'Payment with given order_id already exists',
    REFUND_IN_PROGRESS: 'A refund of this payment is already in progress',
    CANCEL_IN_PROGRESS: 'A cancellation of this payment is already in progress',
    REFUND_NOT_SUCCESSFUL: 'The payment is not successful',
    REFUND_NOT_CAPTURABLE: 'The two-step payment cannot be captured or was cancelled',
    CLEARING_AMOUNT_EXCEEDED: 'Clearing amount exceeds the payment amount',
    TOO_OLD: 'More than 180 days have passed since this transaction',
}

# Failure codes.
UNKNOWN_PS_ERROR = '99999'
CONTACT_ISSUER = '10001'
THREE_DS_FAILED = '10004'
CARD_DATA = '10005'
INSUFFICIENT_FUNDS = '10009'
CARD_EXPIRED = '10017'
LIFETIME_EXPIRED = '10018'
ALREADY_CANCELLED = '10033'
NOT_SUCCESSFUL = '90131'
CANNOT_REFUND = '900811'

FAILURE_TEXT = {
    UNKNOWN_PS_ERROR: 'Неизвестная ошибка платежной системы',
    CONTACT_ISSUER: 'Declined: contact the card issuer',
    THREE_DS_FAILED: '3-D Secure authentication failed',
    CARD_DATA: 'Invalid card data',
    INSUFFICIENT_FUNDS: 'Insufficient funds',
    CARD_EXPIRED: 'The card has expired',
    LIFETIME_EXPIRED: 'The payment lifetime has expired',
    '10022': 'Declined by the issuer',
    '11024': 'Declined by the issuer',
    '11036': 'Declined by the issuer',
    '100066': 'Declined by the issuer',
    ALREADY_CANCELLED: 'The payment is already cancelled',
    NOT_SUCCESSFUL: 'The payment is not successful',
    CANNOT_REFUND: 'The amount cannot be refunded: it exceeds the refundable remainder',
}


def failure_text(code: str) -> str:
    return FAILURE_TEXT.get(code, 'Payment declined')


class ApiError(Exception):
    """A request error answered as an unsigned ``<response>``."""

    def __init__(self, code: str, description: str | None = None) -> None:
        self.code = code
        self.description = description or REQUEST_ERROR_TEXT.get(code, 'Request error')
        super().__init__(f'{code}: {self.description}')


def invalid(param: str, reason: str = 'invalid') -> ApiError:
    return ApiError(INVALID_PARAMETER, f'{param}: {reason}')
