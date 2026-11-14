import { Injectable, signal } from '@angular/core';
import { Observable, Subject, finalize, shareReplay, take } from 'rxjs';
import { MfaMethod } from './mfa.service';

export interface StepUpRequest {
  methods: MfaMethod[];
}

/**
 * Asks the user to prove a second factor again before a sensitive action
 * (403 `mfa_step_up_required`). The step-up dialog renders `request()`; the
 * interceptor waits on `confirm()`. Requests that need step-up at the same
 * time share one dialog.
 */
@Injectable({ providedIn: 'root' })
export class StepUpService {
  /** The open prompt, or null. */
  readonly request = signal<StepUpRequest | null>(null);

  private answer: Subject<boolean> | null = null;
  private pending$: Observable<boolean> | null = null;

  /** Emits once: true after a successful step-up (new token stored), false if cancelled. */
  confirm(methods: MfaMethod[]): Observable<boolean> {
    if (!this.pending$) {
      const answer = new Subject<boolean>();
      this.answer = answer;
      this.request.set({ methods });
      this.pending$ = answer.pipe(
        take(1),
        finalize(() => {
          this.pending$ = null;
          this.answer = null;
          this.request.set(null);
        }),
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    }
    return this.pending$;
  }

  /** Called by the dialog. */
  resolve(verified: boolean): void {
    this.answer?.next(verified);
    this.answer?.complete();
  }
}
