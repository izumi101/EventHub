import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PaymentService } from './payment.service';
import { BookingService } from './booking.service';
import { EventService } from './event.service';
import { environment } from '../../environments/environment';

const API = environment.apiUrl;

describe('payment HTTP services', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  describe('PaymentService', () => {
    it('creates a checkout session with POST and an empty body, and returns the gateway URL', () => {
      let url = '';
      TestBed.inject(PaymentService)
        .createCheckoutSession(42)
        .subscribe((res) => (url = res.checkout_url));

      const req = http.expectOne(`${API}/payments/create-checkout/42/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({});
      req.flush({ checkout_url: 'https://pay.example/session/abc', session_id: 'abc' });
      expect(url).toBe('https://pay.example/session/abc');
    });

    it('propagates a checkout failure (expired hold) with status and backend message', () => {
      let err: HttpErrorResponse | undefined;
      TestBed.inject(PaymentService)
        .createCheckoutSession(42)
        .subscribe({ error: (e: HttpErrorResponse) => (err = e) });

      http
        .expectOne(`${API}/payments/create-checkout/42/`)
        .flush({ error: 'Hold expired' }, { status: 400, statusText: 'Bad Request' });

      expect(err?.status).toBe(400);
      expect(err?.error).toEqual({ error: 'Hold expired' });
    });

    it('verifies a payment with GET and the session id as a query parameter', () => {
      let status = '';
      TestBed.inject(PaymentService)
        .verifyPayment('cs_test_1')
        .subscribe((res) => (status = res.status));

      const req = http.expectOne((r) => r.url === `${API}/payments/verify/`);
      expect(req.request.method).toBe('GET');
      expect(req.request.params.get('session_id')).toBe('cs_test_1');
      req.flush({ status: 'completed', event_title: 'Gig', amount: '5000.00', currency: 'KZT' });
      expect(status).toBe('completed');
    });

    it('URL-encodes a session id instead of splicing it into the path', () => {
      TestBed.inject(PaymentService).verifyPayment('a&b=c d').subscribe();
      const req = http.expectOne((r) => r.url === `${API}/payments/verify/`);
      expect(req.request.params.get('session_id')).toBe('a&b=c d');
      expect(req.request.urlWithParams).toContain('session_id=a%26b=c%20d');
      req.flush({});
    });
  });

  describe('BookingService (group booking payment)', () => {
    it('starts group checkout with POST /bookings/<id>/checkout/ and returns checkout_url', () => {
      let res: { checkout_url: string } | undefined;
      TestBed.inject(BookingService)
        .checkout('bk-1')
        .subscribe((r) => (res = r));

      const req = http.expectOne(`${API}/bookings/bk-1/checkout/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({});
      req.flush({ checkout_url: 'https://pay.example/g', mock: false });
      expect(res?.checkout_url).toBe('https://pay.example/g');
    });

    it('holds seats with the event id and seat ids; a 409 reaches the caller unchanged', () => {
      let err: HttpErrorResponse | undefined;
      TestBed.inject(BookingService)
        .create(7, [11, 12])
        .subscribe({ error: (e: HttpErrorResponse) => (err = e) });

      const req = http.expectOne(`${API}/bookings/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ event: 7, seat_ids: [11, 12] });
      req.flush({ error: 'Seat taken' }, { status: 409, statusText: 'Conflict' });
      expect(err?.status).toBe(409);
    });

    it('verifies a booking payment by session id and refunds with the reason (default empty)', () => {
      const svc = TestBed.inject(BookingService);
      svc.verify('cs_9').subscribe();
      const verify = http.expectOne((r) => r.url === `${API}/bookings/verify/`);
      expect(verify.request.method).toBe('GET');
      expect(verify.request.params.get('session_id')).toBe('cs_9');
      verify.flush({});

      svc.refund('bk-1', 'duplicate').subscribe();
      const withReason = http.expectOne(`${API}/bookings/bk-1/refund/`);
      expect(withReason.request.method).toBe('POST');
      expect(withReason.request.body).toEqual({ reason: 'duplicate' });
      withReason.flush({});

      svc.refund('bk-2').subscribe();
      expect(http.expectOne(`${API}/bookings/bk-2/refund/`).request.body).toEqual({ reason: '' });
    });
  });

  describe('EventService (registration refunds and invoice)', () => {
    it('sends a refund request to the event with only the reason', () => {
      TestBed.inject(EventService).requestRefund(5, 'cannot attend').subscribe();
      const req = http.expectOne(`${API}/events/5/request-refund/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ reason: 'cannot attend' });
      req.flush({ id: 1, status: 'pending' });
    });

    it('propagates a refused refund request (already used ticket) as an HTTP error', () => {
      let status = 0;
      TestBed.inject(EventService)
        .requestRefund(5, '')
        .subscribe({ error: (e: HttpErrorResponse) => (status = e.status) });
      http
        .expectOne(`${API}/events/5/request-refund/`)
        .flush({ error: 'Ticket used' }, { status: 400, statusText: 'Bad Request' });
      expect(status).toBe(400);
    });

    it('organizer refund posts the amount and reason to the payment refund endpoint', () => {
      TestBed.inject(EventService)
        .refundRegistration(9, { amount: '25.00', reason: 'partial' })
        .subscribe();
      const req = http.expectOne(`${API}/payments/refund/9/`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ amount: '25.00', reason: 'partial' });
      req.flush({});
    });

    it('downloads the invoice as a blob over an authenticated GET (no token in the URL)', () => {
      let blob: Blob | undefined;
      TestBed.inject(EventService)
        .getInvoiceBlob(9)
        .subscribe((b) => (blob = b));

      const req = http.expectOne(`${API}/payments/invoice/9/`);
      expect(req.request.method).toBe('GET');
      expect(req.request.responseType).toBe('blob');
      expect(req.request.urlWithParams).not.toMatch(/token|jwt/i);
      req.flush(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
      expect(blob?.type).toBe('application/pdf');
    });

    it('surfaces a 404 for a missing invoice to the subscriber', () => {
      let status = 0;
      TestBed.inject(EventService)
        .getInvoiceBlob(9)
        .subscribe({ error: (e: HttpErrorResponse) => (status = e.status) });
      http
        .expectOne(`${API}/payments/invoice/9/`)
        .flush(new Blob(['nope']), { status: 404, statusText: 'Not Found' });
      expect(status).toBe(404);
    });
  });
});
