import { Component, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

/**
 * Shows freshly generated recovery codes once, with copy and download, and
 * asks the user to confirm they saved them before continuing.
 */
@Component({
  selector: 'app-recovery-codes',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="space-y-4">
      <div class="note note-warning">
        Save these recovery codes somewhere safe (a password manager or printed). Each one signs you
        in once if you lose your phone or email access. They will not be shown again.
      </div>

      <ul
        class="grid grid-cols-1 min-[360px]:grid-cols-2 gap-2 font-mono text-sm text-foreground"
        aria-label="Recovery codes"
      >
        @for (code of codes(); track code) {
          <li class="rounded-md border border-border bg-muted px-3 py-2 text-center select-all">
            {{ code }}
          </li>
        }
      </ul>

      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn btn-secondary btn-sm" (click)="copy()">
          {{ copied() ? 'Copied' : 'Copy codes' }}
        </button>
        <button type="button" class="btn btn-secondary btn-sm" (click)="download()">
          Download .txt
        </button>
      </div>
      <p class="sr-only" aria-live="polite">{{ copied() ? 'Recovery codes copied.' : '' }}</p>

      <label class="flex items-start gap-2 text-sm text-foreground">
        <input type="checkbox" class="mt-1" [(ngModel)]="saved" name="saved" />
        I saved my recovery codes.
      </label>

      <button
        type="button"
        class="btn btn-primary btn-full"
        [disabled]="!saved"
        (click)="done.emit()"
      >
        {{ continueLabel() }}
      </button>
    </div>
  `,
})
export class RecoveryCodesComponent {
  readonly codes = input.required<string[]>();
  readonly continueLabel = input('Continue');
  readonly done = output();

  readonly copied = signal(false);
  saved = false;

  private get text(): string {
    return (
      'EventHub recovery codes\n' +
      'Each code works once. Keep them private.\n\n' +
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
