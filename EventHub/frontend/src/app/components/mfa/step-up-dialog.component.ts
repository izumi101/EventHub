import { Component, inject } from '@angular/core';
import { DialogDirective } from '../../directives/dialog.directive';
import { MfaService } from '../../services/mfa.service';
import { StepUpService } from '../../services/step-up.service';
import { PasskeyClient } from '../../utils/passkey-client';
import { MfaVerifier, MfaVerifyComponent } from './mfa-verify.component';

/**
 * "Confirm it's you" before a sensitive action. Opened by the step-up
 * interceptor; verifying a factor stores a fresh access token
 * (MfaService.stepUp) and lets the interceptor retry the original request.
 */
@Component({
  selector: 'app-step-up-dialog',
  standalone: true,
  imports: [DialogDirective, MfaVerifyComponent],
  template: `
    @if (stepUp.request(); as req) {
      <div class="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-black/40">
        <div
          class="relative card w-full max-w-sm p-6 shadow-lg animate-scale-in max-h-[90dvh] overflow-y-auto"
          appDialog
          (dismiss)="cancel()"
        >
          <h2 class="text-base font-semibold text-foreground mb-1">Confirm it's you</h2>
          <p class="text-sm text-muted-foreground mb-5">
            This action is protected. Verify with a second factor to continue.
          </p>
          <app-mfa-verify
            [methods]="req.methods"
            [verifier]="verifier"
            submitLabel="Confirm"
            (verified)="stepUp.resolve(true)"
          />
          <div class="mt-4 flex justify-end">
            <button type="button" class="btn btn-ghost btn-sm" (click)="cancel()">Cancel</button>
          </div>
        </div>
      </div>
    }
  `,
})
export class StepUpDialogComponent {
  protected readonly stepUp = inject(StepUpService);
  private readonly mfa = inject(MfaService);
  private readonly passkeys = inject(PasskeyClient);

  protected readonly verifier: MfaVerifier = {
    sendEmailCode: () => this.mfa.sendEmailCode('step_up'),
    passkeyOptions: () => this.mfa.stepUpPasskeyOptions(),
    verify: (proof) => this.mfa.stepUp(proof),
  };

  cancel(): void {
    this.passkeys.cancel();
    this.stepUp.resolve(false);
  }
}
