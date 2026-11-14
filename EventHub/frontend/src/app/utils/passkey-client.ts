import { Injectable } from '@angular/core';
import {
  WebAuthnAbortService,
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser';
import type { WebAuthnJson } from '../services/mfa.service';

/**
 * The browser side of passkeys (@simplewebauthn/browser), behind a service so
 * components can be tested without a WebAuthn-capable browser.
 */
@Injectable({ providedIn: 'root' })
export class PasskeyClient {
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
      return 'The passkey prompt was closed or timed out. Try again.';
    }
    if (name === 'InvalidStateError') {
      return 'This passkey is already registered on your account.';
    }
    if (name === 'SecurityError') {
      return 'Passkeys need a secure connection (https or localhost).';
    }
    return 'The passkey could not be used. Try again or choose another method.';
  }
}
