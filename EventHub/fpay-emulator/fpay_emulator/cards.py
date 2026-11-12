"""Test cards (spec section 7) and payment scenarios.

A full card number never leaves this module: callers get the masked PAN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import errors

SUCCESS = 'success'
DECLINE = 'decline'
THREE_DS_SUCCESS = '3ds_success'
THREE_DS_FAIL = '3ds_fail'
HANG = 'hang'
ABANDON = 'abandon'
SCENARIOS = (SUCCESS, DECLINE, THREE_DS_SUCCESS, THREE_DS_FAIL, HANG, ABANDON)

DEFAULT_CARD = '4716047261941981'

# Details that go with every test card (spec section 7): the expiry and CVV
# the documentation lists, and a cardholder name that passes the owner check
# (at least two Latin words). Shown on the payment page next to the cards.
TEST_CARD_DETAILS = {
    'exp_month': '12',
    'exp_year': '30',
    'cvv': '123',
    'owner': 'TEST CARDHOLDER',
}


@dataclass(frozen=True)
class KnownCard:
    pan: str
    outcome: str  # 'success', '3ds' or 'decline'
    failure_code: str | None
    label: str


_CARDS = [
    KnownCard('4716047261941981', 'success', None, 'Success, capture and refund work (no 3-D Secure)'),
    KnownCard('4916307416334310', '3ds', None, 'Success with 3-D Secure'),
    KnownCard('4939770956154989', 'success', None, 'Success, cancel before capture works'),
    KnownCard('4111111111111111', 'success', None, 'Success (payment frame card)'),
    KnownCard('6224466455690681278', 'success', None, 'UnionPay, all operations work'),
    KnownCard('623275279933273424', 'success', None, 'UnionPay, all operations work'),
    KnownCard('62528733472390953', 'success', None, 'UnionPay, all operations work'),
    KnownCard('5335215945367703', 'decline', '99999', 'Declined: unknown payment system error'),
    KnownCard('4916109830832246', 'decline', '100066', 'Declined'),
    KnownCard('5548398681700148', 'decline', errors.INSUFFICIENT_FUNDS, 'Declined: insufficient funds'),
    KnownCard('5475102935853613', 'decline', '11036', 'Declined'),
    KnownCard('5555555555555557', 'decline', '11024', 'Declined'),
    KnownCard('4444444444444422', 'decline', errors.CONTACT_ISSUER, 'Declined: contact the issuer'),
    KnownCard('4444444411111111', 'decline', '10022', 'Declined'),
    KnownCard('4444444499999999', 'decline', errors.LIFETIME_EXPIRED, 'Declined: lifetime expired'),
    KnownCard('5484458131482832', 'decline', errors.THREE_DS_FAILED, 'Declined: 3-D Secure'),
]
TEST_CARDS = {card.pan: card for card in _CARDS}
_DIGITS = re.compile(r'^\d{12,19}$')


def normalise_pan(text: str) -> str:
    return re.sub(r'[\s-]', '', text or '')


def luhn_ok(pan: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(pan)):
        digit = int(ch)
        if i % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def valid_pan(pan: str) -> bool:
    return bool(_DIGITS.match(pan)) and (pan in TEST_CARDS or luhn_ok(pan))


def mask(pan: str) -> str:
    """``5483-18XX-XXXX-0293`` style: first six and last four digits (S4)."""
    masked = pan[:6] + 'X' * (len(pan) - 10) + pan[-4:]
    return '-'.join(masked[i : i + 4] for i in range(0, len(masked), 4))


def brand(pan: str) -> str:
    if pan.startswith('4'):
        return 'VI'
    if pan.startswith('62'):
        return 'UP'
    if pan[:1] in ('2', '5'):
        return 'MC'
    return 'XX'


def card_record(pan: str, exp_month: str, exp_year: str, owner: str) -> dict[str, str]:
    """What the gateway keeps about a card: never the full PAN or the CVV."""
    return {
        'pan': mask(pan),
        'brand': brand(pan),
        'exp': f'{exp_month}/{exp_year}',
        'owner': owner,
    }


def scenario_for_card(pan: str, testing: bool) -> tuple[str, str | None]:
    """Outcome of a card in test mode; any valid card succeeds outside test mode."""
    card = TEST_CARDS.get(pan)
    if card is None:
        return (DECLINE, errors.CARD_DATA) if testing else (SUCCESS, None)
    if card.outcome == '3ds':
        return THREE_DS_SUCCESS, None
    if card.outcome == 'decline':
        return DECLINE, card.failure_code
    return SUCCESS, None


def known_cards() -> list[KnownCard]:
    return list(_CARDS)
