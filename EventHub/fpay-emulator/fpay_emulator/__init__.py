"""Freedom Pay Merchant API gateway emulator.

A standalone service that speaks the protocol described in
``EventHub/docs/payments/freedompay-protocol.md`` (the "spec"): request
signatures, ``init_payment``, the hosted payment page, Check/Result callbacks,
``get_status3.php``, capture, cancel and refund, plus a control API for tests.
"""

__version__ = '1.0.0'
