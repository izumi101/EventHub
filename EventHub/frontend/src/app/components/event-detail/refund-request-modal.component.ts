import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event } from '../../models/models';

/** Small dialog where an attendee asks the organizer to refund their ticket. */
@Component({
  selector: 'app-refund-request-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 animate-fade-in" (click)="closed.emit()">
      <div class="card w-full max-w-md p-6 animate-slide-up" (click)="$event.stopPropagation()">
        <h3 class="text-lg font-bold text-foreground mb-1">Request a refund</h3>
        <p class="text-sm text-muted-foreground mb-4">
          The organizer will review your request and approve or decline it. You'll be notified of their decision.
        </p>
        <label class="block text-sm font-medium text-foreground mb-1.5">Reason <span class="text-muted-foreground font-normal">(optional)</span></label>
        <textarea [(ngModel)]="reason" rows="3" placeholder="Why are you requesting a refund?" class="input resize-none w-full mb-4"></textarea>
        <div class="flex gap-2">
          <button (click)="closed.emit()" class="btn btn-secondary flex-1">Cancel</button>
          <button (click)="submit()" [disabled]="submitting" class="btn btn-primary flex-1">
            {{ submitting ? 'Submitting…' : 'Submit request' }}
          </button>
        </div>
      </div>
    </div>
  `,
})
export class RefundRequestModalComponent {
  @Input({ required: true }) event!: Event;
  @Output() closed = new EventEmitter<void>();
  /** Fires after the request is accepted by the API. */
  @Output() submitted = new EventEmitter<void>();

  reason = '';
  submitting = false;

  constructor(
    private eventService: EventService,
    private toastService: ToastService,
  ) {}

  submit(): void {
    this.submitting = true;
    this.eventService.requestRefund(this.event.id, this.reason).subscribe({
      next: () => {
        this.submitting = false;
        this.toastService.success('Refund request submitted — the organizer will review it.');
        this.submitted.emit();
      },
      error: err => {
        this.submitting = false;
        this.toastService.error(err.error?.error || 'Could not submit refund request.');
      },
    });
  }
}
