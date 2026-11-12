import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { MyRegistrationsComponent } from './my-registrations.component';
import { EventService } from '../../services/event.service';
import { PaymentService } from '../../services/payment.service';
import { ToastService } from '../../services/toast.service';
import type { Registration } from '../../models/models';

const reg = (over: Record<string, unknown> = {}): Registration =>
  ({
    id: 11,
    status: 'confirmed',
    ticket_uuid: 'uuid-11',
    event: { id: 5, title: 'Gig', currency: 'KZT', date: '2027-01-01T00:00:00Z' },
    payment: { net_amount: '5000.00', is_refundable: true },
    ...over,
  }) as unknown as Registration;

function setup() {
  const eventService = {
    getMyRegistrations: vi.fn(() => of({ results: [] })),
    requestRefund: vi.fn(),
    getInvoiceBlob: vi.fn(),
  };
  const paymentService = { createCheckoutSession: vi.fn() };
  TestBed.configureTestingModule({
    imports: [MyRegistrationsComponent],
    providers: [
      { provide: EventService, useValue: eventService },
      { provide: PaymentService, useValue: paymentService },
    ],
  });
  const cmp = TestBed.createComponent(MyRegistrationsComponent).componentInstance;
  const toasts = () => TestBed.inject(ToastService).toasts();
  return { cmp, eventService, paymentService, toasts };
}

describe('MyRegistrationsComponent payment actions', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('sends the refund reason for the registration event, closes the modal and reloads', () => {
    const s = setup();
    s.eventService.requestRefund.mockReturnValue(of({ id: 1, status: 'pending' }));
    s.cmp.openRefund(reg());
    s.cmp.refundReason = 'double booked';

    s.cmp.submitRefundRequest();

    expect(s.eventService.requestRefund).toHaveBeenCalledWith(5, 'double booked');
    expect(s.cmp.refundReg).toBeNull();
    expect(s.cmp.submittingRefund).toBe(false);
    expect(
      s.toasts().some((t) => t.type === 'success' && t.message.includes('Refund request')),
    ).toBe(true);
    expect(s.eventService.getMyRegistrations).toHaveBeenCalledTimes(1); // list refreshed → shows "Refund pending"
  });

  it('keeps the modal open and shows the backend message when the refund request is refused', () => {
    const s = setup();
    s.eventService.requestRefund.mockReturnValue(
      throwError(() => ({ status: 400, error: { error: 'Refund already requested' } })),
    );
    const r = reg();
    s.cmp.openRefund(r);

    s.cmp.submitRefundRequest();

    expect(s.cmp.refundReg).toBe(r);
    expect(s.cmp.submittingRefund).toBe(false);
    expect(s.toasts().map((t) => t.message)).toContain('Refund already requested');
    expect(s.eventService.getMyRegistrations).not.toHaveBeenCalled();
  });

  it('does not send a refund request when no registration is selected', () => {
    const s = setup();
    s.cmp.submitRefundRequest();
    expect(s.eventService.requestRefund).not.toHaveBeenCalled();
  });

  it('offers refunds only for confirmed registrations with a refundable payment', () => {
    const { cmp } = setup();
    expect(cmp.isPaidConfirmed(reg())).toBe(true);
    expect(cmp.isPaidConfirmed(reg({ payment: { is_refundable: false } }))).toBe(false);
    expect(cmp.isPaidConfirmed(reg({ payment: null }))).toBe(false);
    expect(cmp.isPaidConfirmed(reg({ status: 'pending' }))).toBe(false);
  });

  it('opens the downloaded invoice from a blob URL and revokes it after a minute', () => {
    vi.useFakeTimers();
    const s = setup();
    const blob = new Blob(['%PDF'], { type: 'application/pdf' });
    s.eventService.getInvoiceBlob.mockReturnValue(of(blob));
    const create = vi.fn(() => 'blob:invoice-1');
    const revoke = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    s.cmp.openInvoice(reg());

    expect(s.eventService.getInvoiceBlob).toHaveBeenCalledWith(11);
    expect(create).toHaveBeenCalledWith(blob);
    expect(open).toHaveBeenCalledWith('blob:invoice-1', '_blank');
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(60_000);
    expect(revoke).toHaveBeenCalledWith('blob:invoice-1');
  });

  it('shows a toast and opens nothing when the invoice download fails', () => {
    const s = setup();
    s.eventService.getInvoiceBlob.mockReturnValue(throwError(() => ({ status: 404 })));
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    s.cmp.openInvoice(reg());

    expect(open).not.toHaveBeenCalled();
    expect(s.toasts().map((t) => t.message)).toContain('Could not load the invoice.');
  });

  it('completePayment redirects to the gateway for the registration', () => {
    const s = setup();
    const loc = { href: 'http://localhost/my-registrations', origin: 'http://localhost' };
    vi.stubGlobal('location', loc);
    s.paymentService.createCheckoutSession.mockReturnValue(
      of({ checkout_url: 'https://pay.example/c/9' }),
    );

    s.cmp.completePayment(reg({ status: 'pending' }), { stopPropagation: vi.fn() } as never);

    expect(s.paymentService.createCheckoutSession).toHaveBeenCalledWith(11);
    expect(s.cmp.payingId).toBe(11);
    expect(loc.href).toBe('https://pay.example/c/9');
  });

  it('completePayment clears the busy state, toasts and reloads when the hold has expired', () => {
    const s = setup();
    const loc = { href: 'http://localhost/my-registrations', origin: 'http://localhost' };
    vi.stubGlobal('location', loc);
    s.paymentService.createCheckoutSession.mockReturnValue(
      throwError(() => ({ status: 400, error: { error: 'Hold expired' } })),
    );

    s.cmp.completePayment(reg({ status: 'pending' }), { stopPropagation: vi.fn() } as never);

    expect(s.cmp.payingId).toBeNull();
    expect(loc.href).toBe('http://localhost/my-registrations');
    expect(s.toasts().map((t) => t.message)).toContain(
      'Could not start payment. Your seat hold may have expired.',
    );
    expect(s.eventService.getMyRegistrations).toHaveBeenCalledTimes(1);
  });
});
