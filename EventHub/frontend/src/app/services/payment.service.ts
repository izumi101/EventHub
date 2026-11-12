import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  CheckoutSessionResponse,
  PaymentStatusResponse,
  PaymentVerificationResponse,
} from '../models/models';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class PaymentService {
  private http = inject(HttpClient);

  private apiUrl = `${environment.apiUrl}/payments`;

  createCheckoutSession(registrationId: number): Observable<CheckoutSessionResponse> {
    return this.http.post<CheckoutSessionResponse>(
      `${this.apiUrl}/create-checkout/${registrationId}/`,
      {},
    );
  }

  verifyPayment(sessionId: string): Observable<PaymentVerificationResponse> {
    return this.http.get<PaymentVerificationResponse>(`${this.apiUrl}/verify/`, {
      params: { session_id: sessionId },
    });
  }

  /** Provider-neutral state of one of the buyer's payments (owner only). */
  getPaymentStatus(paymentId: number): Observable<PaymentStatusResponse> {
    return this.http.get<PaymentStatusResponse>(`${this.apiUrl}/status/${paymentId}/`);
  }
}
