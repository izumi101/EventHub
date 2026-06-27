import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { CheckoutSessionResponse, PaymentVerificationResponse } from '../models/models';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class PaymentService {
  private apiUrl = `${environment.apiUrl}/payments`;

  constructor(private http: HttpClient) {}

  createCheckoutSession(registrationId: number): Observable<CheckoutSessionResponse> {
    return this.http.post<CheckoutSessionResponse>(
      `${this.apiUrl}/create-checkout/${registrationId}/`, {}
    );
  }

  verifyPayment(sessionId: string): Observable<PaymentVerificationResponse> {
    return this.http.get<PaymentVerificationResponse>(
      `${this.apiUrl}/verify/`, { params: { session_id: sessionId } }
    );
  }
}
