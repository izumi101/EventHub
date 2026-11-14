import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, tap } from 'rxjs';
import type { components } from '../api/openapi';
import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';
import { AuthResponse } from '../models/models';
import { apiErrorBody } from '../api/api-error';

type Schemas = components['schemas'];

export type MfaMethod = Schemas['MFAMethodEnum'];
export type MfaStatus = Schemas['MFAStatus'];
export type Passkey = Schemas['Passkey'];
export type FactorAdded = Schemas['FactorAdded'];
export type TotpSetup = Schemas['TOTPSetupResult'];
export type EmailCodeSent = Schemas['EmailCodeSent'];
export type StepUpResult = Schemas['StepUpResult'];
export type EmailCodePurpose = Schemas['EmailSendRequestRequest']['purpose'];

/** WebAuthn options / responses travel as JSON objects (@simplewebauthn/browser). */
export type WebAuthnJson = Record<string, unknown>;

/** One proof of a second factor: a code, or a passkey assertion. */
export type FactorProof =
  | { method: 'totp' | 'email' | 'recovery_code'; code: string }
  | { method: 'webauthn'; credential: WebAuthnJson };

/** A failed HTTP call (as opposed to e.g. a browser WebAuthn error). */
export function isApiError(err: unknown): boolean {
  return typeof err === 'object' && err !== null && 'status' in err && 'error' in err;
}

/** Translation keys of the method names (translate with the `transloco` pipe). */
export const METHOD_LABEL_KEYS: Record<MfaMethod, string> = {
  totp: 'mfa.method.totp',
  webauthn: 'mfa.method.webauthn',
  email: 'mfa.method.email',
  recovery_code: 'mfa.method.recovery_code',
};

/** The stable `code` of a refused call (mfa_invalid, mfa_locked, ...). */
export function mfaErrorCode(err: unknown): string | undefined {
  const code = apiErrorBody(err)?.['code'];
  return typeof code === 'string' ? code : undefined;
}

/** Seconds to wait, from a 429 (`retry_after`). */
export function mfaRetryAfter(err: unknown): number | undefined {
  const value = apiErrorBody(err)?.['retry_after'];
  return typeof value === 'number' && value > 0 ? value : undefined;
}

/**
 * Two-factor authentication API (docs/adr/0002-two-factor-authentication.md).
 *
 * Setup calls take an optional `enrollmentToken`: a user who must enroll gets
 * one at login instead of a session, and it is sent as their bearer token
 * (the auth interceptor leaves requests with their own Authorization alone).
 */
@Injectable({ providedIn: 'root' })
export class MfaService {
  private http = inject(HttpClient);
  private auth = inject(AuthService);
  private api = `${environment.apiUrl}/auth/mfa`;

  private options(enrollmentToken?: string | null): { headers?: HttpHeaders } {
    return enrollmentToken
      ? { headers: new HttpHeaders({ Authorization: `Bearer ${enrollmentToken}` }) }
      : {};
  }

  // ---- Sign-in, second step ---- //

  loginVerify(challengeToken: string, proof: FactorProof): Observable<AuthResponse> {
    return this.http
      .post<AuthResponse>(`${this.api}/login/verify/`, {
        challenge_token: challengeToken,
        ...proof,
      })
      .pipe(tap((res) => this.auth.completeLogin(res)));
  }

  loginSendEmailCode(challengeToken: string): Observable<EmailCodeSent> {
    return this.http.post<EmailCodeSent>(`${this.api}/login/email/send/`, {
      challenge_token: challengeToken,
    });
  }

  loginPasskeyOptions(challengeToken: string): Observable<WebAuthnJson> {
    return this.http.post<WebAuthnJson>(`${this.api}/login/webauthn/options/`, {
      challenge_token: challengeToken,
    });
  }

  // ---- Status and setup ---- //

  status(): Observable<MfaStatus> {
    return this.http.get<MfaStatus>(`${this.api}/status/`);
  }

  totpSetup(enrollmentToken?: string | null): Observable<TotpSetup> {
    return this.http.post<TotpSetup>(
      `${this.api}/totp/setup/`,
      null,
      this.options(enrollmentToken),
    );
  }

  totpConfirm(code: string, enrollmentToken?: string | null): Observable<FactorAdded> {
    return this.http
      .post<FactorAdded>(`${this.api}/totp/confirm/`, { code }, this.options(enrollmentToken))
      .pipe(tap((res) => this.storeFirstFactorSession(res)));
  }

  totpRemove(): Observable<MfaStatus> {
    return this.http.delete<MfaStatus>(`${this.api}/totp/`);
  }

  sendEmailCode(
    purpose: EmailCodePurpose,
    enrollmentToken?: string | null,
  ): Observable<EmailCodeSent> {
    return this.http.post<EmailCodeSent>(
      `${this.api}/email/send/`,
      { purpose },
      this.options(enrollmentToken),
    );
  }

  emailEnable(code: string, enrollmentToken?: string | null): Observable<FactorAdded> {
    return this.http
      .post<FactorAdded>(`${this.api}/email/enable/`, { code }, this.options(enrollmentToken))
      .pipe(tap((res) => this.storeFirstFactorSession(res)));
  }

  emailDisable(): Observable<MfaStatus> {
    return this.http.post<MfaStatus>(`${this.api}/email/disable/`, null);
  }

  passkeyRegisterOptions(name: string, enrollmentToken?: string | null): Observable<WebAuthnJson> {
    return this.http.post<WebAuthnJson>(
      `${this.api}/webauthn/register/options/`,
      { name },
      this.options(enrollmentToken),
    );
  }

  passkeyRegisterVerify(
    credential: WebAuthnJson,
    name: string,
    enrollmentToken?: string | null,
  ): Observable<FactorAdded> {
    return this.http
      .post<FactorAdded>(
        `${this.api}/webauthn/register/verify/`,
        { credential, name },
        this.options(enrollmentToken),
      )
      .pipe(tap((res) => this.storeFirstFactorSession(res)));
  }

  passkeyRename(id: number, name: string): Observable<MfaStatus> {
    return this.http.patch<MfaStatus>(`${this.api}/webauthn/credentials/${id}/`, { name });
  }

  passkeyRemove(id: number): Observable<MfaStatus> {
    return this.http.delete<MfaStatus>(`${this.api}/webauthn/credentials/${id}/`);
  }

  regenerateRecoveryCodes(): Observable<{ recovery_codes: string[] }> {
    return this.http.post<{ recovery_codes: string[] }>(
      `${this.api}/recovery-codes/regenerate/`,
      null,
    );
  }

  disableAll(): Observable<MfaStatus> {
    return this.http.post<MfaStatus>(`${this.api}/disable/`, null);
  }

  // ---- Step-up ---- //

  stepUp(proof: FactorProof): Observable<StepUpResult> {
    return this.http
      .post<StepUpResult>(`${this.api}/step-up/`, proof)
      .pipe(tap((res) => this.auth.setAccessToken(res.access)));
  }

  stepUpPasskeyOptions(): Observable<WebAuthnJson> {
    return this.http.post<WebAuthnJson>(`${this.api}/step-up/webauthn/options/`, null);
  }

  /** The first factor of an account comes with a new session (other sessions
   *  are signed out by the backend): keep it. */
  private storeFirstFactorSession(res: FactorAdded): void {
    if (res.tokens && res.user) {
      this.auth.completeLogin({ tokens: res.tokens, user: res.user });
    }
  }
}
