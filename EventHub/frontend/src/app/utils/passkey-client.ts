import { Injectable, inject } from '@angular/core';
import {
  WebAuthnAbortService,
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser';
import type { WebAuthnJson } from '../services/mfa.service';
import { LanguageService } from '../i18n/language.service';

/**
 * The browser side of passkeys (@simplewebauthn/browser), behind a service so
 * components can be tested without a WebAuthn-capable browser.
 */
@Injectable({ providedIn: 'root' })
export class PasskeyClient {
  private readonly lang = inject(LanguageService);

  /** Passkeys need WebAuthn and a secure context (https or http://localhost). */
  get supported(): boolean {
    return typeof window !== 'undefined' && window.isSecureContext && browserSupportsWebAuthn();
  }

  /** Ask the browser for an assertion with the server's options JSON. */
  async assert(options: WebAuthnJson): Promise<WebAuthnJson> {
    const response = await startAuthentication({
      optionsJSON: options as unknown as PublicKeyCredentialRequestOptionsJSON,
    });
    return response as unknown as WebAuthnJson;
  }

  /** Ask the browser to create a passkey with the server's options JSON. */
  async create(options: WebAuthnJson): Promise<WebAuthnJson> {
    const response = await startRegistration({
      optionsJSON: options as unknown as PublicKeyCredentialCreationOptionsJSON,
    });
    return response as unknown as WebAuthnJson;
  }

  /** Abort a pending browser prompt (e.g. when the dialog is closed). */
  cancel(): void {
    WebAuthnAbortService.cancelCeremony();
  }

  /** A message for a failed or cancelled browser prompt. */
  errorMessage(err: unknown): string {
    const name = err instanceof Error ? err.name : '';
    if (name === 'NotAllowedError' || name === 'AbortError') {
      return this.lang.t('mfa.passkeyError.closed');
    }
    if (name === 'InvalidStateError') {
      return this.lang.t('mfa.passkeyError.alreadyRegistered');
    }
    if (name === 'SecurityError') {
      return this.lang.t('mfa.passkeyError.insecure');
    }
    return this.lang.t('mfa.passkeyError.generic');
  }
}
