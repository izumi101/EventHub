import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { PaymentQrComponent } from './payment-qr.component';
import { PaymentService } from '../../services/payment.service';
import { CheckoutSessionResponse, PaymentStatus, PaymentStatusResponse } from '../../models/models';

const CHECKOUT: CheckoutSessionResponse = {
  checkout_url: 'http://localhost:18080/pay.html?customer=abc',
  session_id: '1030000000001',
  provider: 'freedompay',
  payment_id: 7,
  qr_code: 'data:image/png;base64,iVBORw0KGgo=',
  amount: '5000.00',
  currency: 'KZT',
};

function status(
  value: PaymentStatus,
  registration: PaymentStatusResponse['registration_status'] = 'pending',
): PaymentStatusResponse {
  return {
    payment_id: 7,
    provider: 'freedompay',
    status: value,
    registration_id: 3,
    registration_status: registration,
    event_id: 1,
    event_title: 'Gig',
    amount: '5000.00',
    currency: 'KZT',
  };
}

function render(answers: PaymentStatusResponse[]) {
  const getPaymentStatus = vi.fn(() => of(answers.length > 1 ? answers.shift()! : answers[0]));
  TestBed.configureTestingModule({
    imports: [PaymentQrComponent],
    providers: [provideRouter([]), { provide: PaymentService, useValue: { getPaymentStatus } }],
  });
  const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  const fixture = TestBed.createComponent(PaymentQrComponent);
  fixture.componentRef.setInput('checkout', CHECKOUT);
  fixture.detectChanges();
  const element = fixture.nativeElement as HTMLElement;
  const tick = (ms: number) => {
    vi.advanceTimersByTime(ms);
    fixture.detectChanges();
  };
  return { fixture, element, getPaymentStatus, navigate, tick };
}

describe('PaymentQrComponent', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('renders an accessible dialog with the QR code and the amount', () => {
    const { element, tick } = render([status('pending')]);
    tick(0);
    const dialog = element.querySelector('[role="dialog"]')!;
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const img = element.querySelector('img')!;
    expect(img.getAttribute('src')).toBe(CHECKOUT.qr_code);
    expect(img.getAttribute('alt')).toContain('QR code');
    expect(img.getAttribute('alt')).toContain('5,000.00');
    expect(element.textContent).toContain('Scan with your phone to pay');
    expect(element.querySelector('[data-testid="qr-amount"]')!.textContent).toContain('5,000.00');
    expect(element.querySelector('[data-testid="qr-status"]')!.textContent).toContain(
      'Waiting for the payment',
    );
    expect(element.textContent).toContain('Pay on this device');
  });

  it('polls every 2 seconds and opens the success page once paid', () => {
    const { element, getPaymentStatus, navigate, tick } = render([
      status('pending'),
      status('pending'),
      status('completed', 'confirmed'),
    ]);
    tick(0);
    expect(getPaymentStatus).toHaveBeenCalledWith(7);
    tick(2000);
    expect(navigate).not.toHaveBeenCalled();
    tick(2000);
    expect(navigate).toHaveBeenCalledWith(['/payment/success'], {
      queryParams: { provider: 'freedompay', payment: 7 },
    });
    expect(element.querySelector('[data-testid="qr-status"]')!.textContent).toContain(
      'Payment received',
    );
    // Stopped on the final state.
    const calls = getPaymentStatus.mock.calls.length;
    tick(10_000);
    expect(getPaymentStatus.mock.calls.length).toBe(calls);
  });

  it('stops on a declined payment and says so', () => {
    const { element, getPaymentStatus, navigate, tick } = render([status('failed')]);
    tick(0);
    expect(element.querySelector('[data-testid="qr-status"]')!.textContent).toContain(
      'did not go through',
    );
    tick(10_000);
    expect(getPaymentStatus).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('stops polling when destroyed', () => {
    const { fixture, getPaymentStatus, tick } = render([status('pending')]);
    tick(2000);
    fixture.destroy();
    const calls = getPaymentStatus.mock.calls.length;
    vi.advanceTimersByTime(20_000);
    expect(getPaymentStatus.mock.calls.length).toBe(calls);
  });

  it('stops polling and reports when the dialog is closed', () => {
    const { fixture, element, getPaymentStatus, tick } = render([status('pending')]);
    const closed = vi.fn();
    fixture.componentInstance.closed.subscribe(closed);
    tick(0);
    const close = Array.from(element.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Close'),
    )!;
    close.click();
    expect(closed).toHaveBeenCalledTimes(1);
    const calls = getPaymentStatus.mock.calls.length;
    tick(20_000);
    expect(getPaymentStatus.mock.calls.length).toBe(calls);
  });

  it('gives up after 10 minutes and offers a manual check', () => {
    const { element, getPaymentStatus, tick } = render([status('pending')]);
    tick(10 * 60 * 1000);
    expect(element.querySelector('[data-testid="qr-status"]')!.textContent).toContain(
      'stopped checking',
    );
    const calls = getPaymentStatus.mock.calls.length;
    const check = Array.from(element.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Check payment status'),
    )!;
    check.click();
    tick(0);
    expect(getPaymentStatus.mock.calls.length).toBe(calls + 1);
  });

  it('"Pay on this device" goes to the payment page', () => {
    const { fixture, element } = render([status('pending')]);
    const redirect = vi
      .spyOn(
        fixture.componentInstance as unknown as { redirect: (url: string) => void },
        'redirect',
      )
      .mockImplementation(() => undefined);
    const pay = Array.from(element.querySelectorAll('button')).find((b) =>
      b.textContent.includes('Pay on this device'),
    )!;
    pay.click();
    expect(redirect).toHaveBeenCalledWith(CHECKOUT.checkout_url);
  });
});
