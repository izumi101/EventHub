import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ModalService } from '../../../services/modal.service';

@Component({
  selector: 'app-confirm-modal',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (modalService.isOpen()) {
      <div
        class="fixed inset-0 z-[100] flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        [attr.aria-labelledby]="'modal-title'"
        (keydown.escape)="modalService.cancel()"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/40 animate-fade-in"
          (click)="modalService.cancel()"
        ></div>

        <!-- Panel -->
        <div class="relative card w-full max-w-sm p-6 shadow-lg animate-scale-in">
          <h2 id="modal-title" class="text-base font-semibold text-foreground mb-2">
            {{ modalService.config()?.title }}
          </h2>
          <p class="text-sm text-muted-foreground leading-relaxed mb-6">
            {{ modalService.config()?.message }}
          </p>

          <div class="flex gap-2 justify-end">
            <button
              (click)="modalService.cancel()"
              class="btn btn-secondary btn-sm"
            >
              {{ modalService.config()?.cancelText || 'Cancel' }}
            </button>
            <button
              (click)="modalService.confirm()"
              class="btn btn-sm"
              [class]="modalService.config()?.isDestructive
                ? 'bg-destructive text-destructive-foreground border-destructive hover:opacity-90'
                : 'btn-primary'"
            >
              {{ modalService.config()?.confirmText || 'Confirm' }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class ConfirmModalComponent {
  constructor(public modalService: ModalService) {}
}
