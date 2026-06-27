"""Server-rendered, print-ready invoice for a registration's payment.

Returns a self-contained HTML page (no external assets) styled to print
cleanly to PDF via the browser's "Save as PDF". Keeping it server-side means
the numbers come straight from the billing module — no client-side drift.

Visual language: Ember (warm paper / ink / coral, ticket-stub perforation,
mono kicker labels). The page is opened from a blob: URL, so brand fonts
can't be fetched — the font stacks degrade gracefully to system fonts.
"""
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import escape

INK = '#1A1714'
MUTED = '#6B6259'
PAPER = '#FAF7F2'
BORDER = '#ECE6DD'
BORDER_STRONG = '#DCD3C6'
EMBER = '#E8552D'
EMBER_CTA = '#C2410C'

_PILL_STYLES = {
    'completed': 'background:#E8F2EF;color:#235850;',   # pine — paid
    'refunded':  'background:#F2ECE3;color:#3A332C;',   # warm neutral
}
_PILL_DUE = 'background:#FEF3C7;color:#B45309;'         # warm amber — pending


def _row(label, value, bold=False, muted=False):
    weight = 'font-weight:600;' if bold else ''
    color = f'color:{MUTED};' if muted else f'color:{INK};'
    return (
        f'<tr><td style="padding:9px 0;{color}">{label}</td>'
        f'<td style="padding:9px 0;text-align:right;font-variant-numeric:tabular-nums;{weight}{color}">{value}</td></tr>'
    )


def invoice_html(registration) -> str:
    from events.billing import price_breakdown

    event = registration.event
    user = registration.user
    payment = getattr(registration, 'payment', None)
    bd = price_breakdown(registration) if (event and not event.is_free or registration.ticket_type_id) else None

    cur = (bd or {}).get('currency', 'USD')
    sym = {'USD': '$', 'EUR': '€', 'GBP': '£', 'KZT': '₸'}.get(cur, '')

    full_name = escape(f'{user.first_name} {user.last_name}'.strip() or user.username)
    email = escape(user.email or '')
    event_title = escape(event.title)
    event_location = escape(event.location)
    inv_no = f'INV-{event.id:04d}-{registration.id:05d}'
    issued = timezone.now().strftime('%B %d, %Y')
    status = (payment.status if payment else 'pending').upper()
    pill = _PILL_STYLES.get(status.lower(), _PILL_DUE)

    tier = escape(registration.ticket_type.name if registration.ticket_type_id else (
        f'Seat Row {registration.seat.row} / {registration.seat.col}' if registration.seat_id else 'General admission'
    ))

    rows = ''
    if bd:
        rows += _row(f'{event_title} — {tier}', f'{sym}{bd["subtotal"]}')
        if float(bd['tax']) > 0:
            rows += _row(f'Tax ({bd["tax_percent"]}%)', f'{sym}{bd["tax"]}', muted=True)
        if float(bd['fee']) > 0:
            rows += _row(f'Service fee ({bd["fee_percent"]}%)', f'{sym}{bd["fee"]}', muted=True)
        if registration.promo_code_id:
            rows += _row(f'Promo {escape(registration.promo_code.code)}', 'applied', muted=True)
    total = (bd or {}).get('total', payment.amount if payment else '0.00')

    refund_note = ''
    if payment and float(payment.refunded_amount or 0) > 0:
        refund_note = (
            f'<p style="margin:16px 0 0;display:inline-block;padding:6px 12px;border-radius:8px;'
            f'background:#FDECEA;color:#B42318;font-size:13px;font-weight:600;">'
            f'Refunded: {sym}{payment.refunded_amount}</p>'
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{inv_no}</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Satoshi',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         margin:0; background:{PAPER}; color:{INK}; }}
  .display {{ font-family:'Clash Display','Satoshi',-apple-system,'Segoe UI',sans-serif; }}
  .kicker {{ font-family:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,monospace;
             font-size:11px; font-weight:600; letter-spacing:.14em; text-transform:uppercase; }}
  .sheet {{ position:relative; max-width:720px; margin:32px auto 48px; background:#fff;
            border:1px solid {BORDER}; border-radius:20px; padding:48px; overflow:hidden;
            box-shadow:0 4px 24px rgba(26,23,20,.07); }}
  .top {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:40px; }}
  .brand {{ display:flex; align-items:center; gap:10px; }}
  .logo {{ width:40px; height:40px; border-radius:12px; background:{EMBER}; }}
  .brand b {{ font-size:20px; letter-spacing:-.01em; }}
  .pill {{ display:inline-block; padding:5px 12px; border-radius:999px; font-size:12px;
           font-weight:700; letter-spacing:.06em; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  .total-row td {{ border-top:2px solid {INK}; padding-top:18px; font-size:19px; font-weight:700; }}
  .total-row td:last-child {{ color:{EMBER_CTA}; }}
  .meta {{ font-size:13px; color:{MUTED}; line-height:1.7; }}
  .mono {{ font-family:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,monospace; font-size:12px; }}
  /* Ticket-stub tear line with edge notches */
  .tear {{ position:relative; margin:32px -48px; border-top:2px dashed {BORDER_STRONG}; }}
  .tear i {{ position:absolute; top:-9px; width:18px; height:18px; border-radius:50%;
             background:{PAPER}; border:1px solid {BORDER}; }}
  .tear i.l {{ left:-10px; }} .tear i.r {{ right:-10px; }}
  .actions {{ max-width:720px; margin:24px auto 0; text-align:center; }}
  .btn {{ background:{EMBER_CTA}; color:#fff; border:none; padding:12px 28px; border-radius:12px;
          font-size:15px; font-weight:600; cursor:pointer; font-family:inherit; }}
  .btn:hover {{ background:#9A3412; }}
  @media print {{ .actions {{ display:none; }} body {{ background:#fff; }}
                  .sheet {{ box-shadow:none; border:none; margin:0; max-width:100%; }} }}
</style></head>
<body>
  <div class="actions">
    <button class="btn" onclick="window.print()">Save as PDF / Print</button>
  </div>
  <div class="sheet">
    <div class="top">
      <div>
        <div class="brand"><div class="logo"></div><b class="display">EventHub</b></div>
        <p class="kicker" style="color:{EMBER}; margin:24px 0 4px;">Invoice</p>
        <p class="display" style="font-size:22px; font-weight:600; margin:0;">{inv_no}</p>
        <p class="meta" style="margin:4px 0 0;">Issued {issued}</p>
      </div>
      <div style="text-align:right;">
        <span class="pill" style="{pill}">{status}</span>
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; gap:24px; margin-bottom:8px;">
      <div class="meta">
        <p class="kicker" style="color:{MUTED}; margin:0 0 6px;">Billed to</p>
        <span style="color:{INK}; font-weight:600;">{full_name}</span><br>{email}
      </div>
      <div class="meta" style="text-align:right;">
        <p class="kicker" style="color:{MUTED}; margin:0 0 6px;">Event</p>
        <span style="color:{INK}; font-weight:600;">{event_title}</span><br>
        {event.date.strftime('%b %d, %Y')}<br>{event_location}
      </div>
    </div>

    <div class="tear"><i class="l"></i><i class="r"></i></div>

    <table>
      {rows}
      <tr class="total-row"><td class="display">Total</td><td style="text-align:right;">{sym}{total}</td></tr>
    </table>
    {refund_note}

    <p class="meta" style="margin-top:40px; border-top:1px solid {BORDER}; padding-top:20px;">
      <span class="mono">Ticket ID: {registration.ticket_uuid}</span><br>
      Thank you for your purchase. This invoice was generated by EventHub.
    </p>
  </div>
</body></html>"""


def invoice_response(registration) -> HttpResponse:
    return HttpResponse(invoice_html(registration), content_type='text/html')
