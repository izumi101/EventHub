import { Component, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

/**
 * Shows freshly generated recovery codes once, with copy and download, and
 * asks the user to confirm they saved them before continuing.
 */
@Component({
  selector: 'app-recovery-codes',
  standalone: true,
  imports: [FormsModule, TranslocoPipe],
  template: `
    <div class="space-y-4">
      <div class="note note-warning">
        {{ 'mfa.recovery.warning' | transloco }}
      </div>

      <ul
        class="grid grid-cols-1 min-[360px]:grid-cols-2 gap-2 font-mono text-sm text-foreground"
        [attr.aria-label]="'mfa.recovery.listLabel' | transloco"
      >
        @for (code of codes(); track code) {
          <li class="rounded-md border border-border bg-muted px-3 py-2 text-center select-all">
            {{ code }}
          </li>
        }
      </ul>

      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn btn-secondary btn-sm" (click)="copy()">
          {{ copied() ? ('common.copied' | transloco) : ('mfa.recovery.copy' | transloco) }}
        </button>
        <button type="button" class="btn btn-secondary btn-sm" (click)="download()">
          {{ 'mfa.recovery.download' | transloco }}
        </button>
      </div>
      <p class="sr-only" aria-live="polite">
        {{ copied() ? ('mfa.recovery.copiedAnnounce' | transloco) : '' }}
      </p>

      <label class="flex items-start gap-2 text-sm text-foreground">
        <input type="checkbox" class="mt-1" [(ngModel)]="saved" name="saved" />
        {{ 'mfa.recovery.saved' | transloco }}
      </label>

      <button
        type="button"
        class="btn btn-primary btn-full"
        [disabled]="!saved"
        (click)="done.emit()"
      >
        {{ continueLabel() || ('common.continue' | transloco) }}
      </button>
    </div>
  `,
})
export class RecoveryCodesComponent {
  readonly codes = input.required<string[]>();
  /** Button text; empty means the default "Continue". */
  readonly continueLabel = input('');
  readonly done = output();

  private readonly lang = inject(LanguageService);

  readonly copied = signal(false);
  saved = false;

  private get text(): string {
    return (
      this.lang.t('mfa.recovery.fileTitle') +
      '\n' +
      this.lang.t('mfa.recovery.fileNote') +
      '\n\n' +
      this.codes().join('\n') +
      '\n'
    );
  }

  copy(): void {
    // Undefined outside a secure context (e.g. the plain-HTTP LAN demo).
    const clipboard = navigator.clipboard as Clipboard | undefined;
    if (!clipboard) return;
    clipboard.writeText(this.text).then(
      () => this.copied.set(true),
      () => this.copied.set(false),
    );
  }

  download(): void {
    const url = URL.createObjectURL(new Blob([this.text], { type: 'text/plain' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'eventhub-recovery-codes.txt';
    link.click();
    URL.revokeObjectURL(url);
  }
}
