import { Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event } from '../../models/models';
import { DialogDirective } from '../../directives/dialog.directive';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

/** Small dialog where an attendee asks the organizer to refund their ticket. */
@Component({
  selector: 'app-refund-request-modal',
  standalone: true,
  imports: [DialogDirective, CommonModule, FormsModule, TranslocoPipe],
  template: `
    <div
      class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 animate-fade-in"
    >
      <div
        class="card w-full max-w-md p-6 animate-slide-up"
        appDialog
        dismissOnBackdrop
        (dismiss)="closed.emit()"
      >
        <h3 class="text-lg font-bold text-foreground mb-1">
          {{ 'eventDetail.requestARefund' | transloco }}
        </h3>
        <p class="text-sm text-muted-foreground mb-4">
          {{ 'refundRequest.theOrganizerWillReview' | transloco }}
        </p>
        <label
          for="refund-request-modal-reason"
          class="block text-sm font-medium text-foreground mb-1.5"
          >{{ 'myRegistrations.reason' | transloco }}
          <span class="text-muted-foreground font-normal">{{
            'checkout.optional' | transloco
          }}</span></label
        >
        <textarea
          id="refund-request-modal-reason"
          [(ngModel)]="reason"
          rows="3"
          [placeholder]="'myRegistrations.whyAreYouRequesting' | transloco"
          class="input resize-none w-full mb-4"
        ></textarea>
        <div class="flex gap-2">
          <button (click)="closed.emit()" class="btn btn-secondary flex-1">
            {{ 'common.cancel' | transloco }}
          </button>
          <button (click)="submit()" [disabled]="submitting" class="btn btn-primary flex-1">
            {{
              (submitting ? 'eventDetail.submitting' : 'myRegistrations.submitRequest') | transloco
            }}
          </button>
        </div>
      </div>
    </div>
  `,
})
export class RefundRequestModalComponent {
  private i18n = inject(LanguageService);
  private eventService = inject(EventService);
  private toastService = inject(ToastService);

  @Input({ required: true }) event!: Event;
  @Output() readonly closed = new EventEmitter<void>();
  /** Fires after the request is accepted by the API. */
  @Output() readonly submitted = new EventEmitter<void>();

  reason = '';
  submitting = false;

  submit(): void {
    this.submitting = true;
    this.eventService.requestRefund(this.event.id, this.reason).subscribe({
      next: () => {
        this.submitting = false;
        this.toastService.success(this.i18n.t('myRegistrations.refundRequestSubmittedThe'));
        this.submitted.emit();
      },
      error: (err) => {
        this.submitting = false;
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('refundRequest.couldNotSubmitRefund'), 'error'),
        );
      },
    });
  }
}
