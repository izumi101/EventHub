import { Component, Input, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { EventService, type Review } from '../../services/event.service';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { Event, Registration } from '../../models/models';
import { apiErrorMessage } from '../../api/api-error';

/** Reviews block on the event page: list, average rating and the
 *  "write a review" form (confirmed attendees, after the event starts). */
@Component({
  selector: 'app-event-reviews',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Reviews
          @if (reviews.length > 0) {
            <span class="ml-2 text-foreground normal-case font-bold">
              {{ avgRating | number: '1.1-1' }} ★ ({{ reviews.length }})
            </span>
          }
        </h2>
        @if (canReview) {
          <button (click)="showReviewForm = !showReviewForm" class="btn btn-sm btn-secondary">
            Write a review
          </button>
        }
      </div>

      <!-- Review form -->
      @if (showReviewForm) {
        <div class="card p-4 mb-4">
          <div class="flex gap-1 mb-3">
            @for (star of [1, 2, 3, 4, 5]; track star) {
              <button
                (click)="reviewRating = star"
                class="text-2xl transition-transform hover:scale-110"
                [class]="star <= reviewRating ? 'text-amber-400' : 'text-muted'"
              >
                ★
              </button>
            }
          </div>
          <textarea
            [(ngModel)]="reviewComment"
            placeholder="Share your experience..."
            rows="3"
            class="input resize-none mb-3"
          ></textarea>
          <div class="flex gap-2">
            <button
              (click)="submitReview()"
              [disabled]="!reviewRating || submittingReview"
              class="btn btn-sm btn-primary"
            >
              {{ submittingReview ? 'Posting...' : 'Post review' }}
            </button>
            <button (click)="showReviewForm = false" class="btn btn-sm btn-secondary">
              Cancel
            </button>
          </div>
        </div>
      }

      <!-- Reviews list -->
      @if (reviews.length === 0) {
        <p class="text-sm text-muted-foreground py-4">No reviews yet. Be the first!</p>
      } @else {
        <div class="space-y-4">
          @for (review of reviews; track review.id) {
            <div class="flex gap-3">
              <div
                class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0"
              >
                {{ review.username.charAt(0).toUpperCase() }}
              </div>
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-sm font-semibold text-foreground">{{ review.username }}</span>
                  <span class="text-amber-400 text-sm"
                    >{{ '★'.repeat(review.rating) }}{{ '☆'.repeat(5 - review.rating) }}</span
                  >
                  <span class="text-xs text-muted-foreground">{{
                    review.created_at | date: 'MMM d, y'
                  }}</span>
                </div>
                @if (review.comment) {
                  <p class="text-sm text-foreground/80">{{ review.comment }}</p>
                }
              </div>
            </div>
          }
        </div>
      }
    </div>
  `,
})
export class EventReviewsComponent implements OnInit {
  private eventService = inject(EventService);
  private authService = inject(AuthService);
  private toastService = inject(ToastService);

  @Input({ required: true }) event!: Event;
  /** The viewer's registration — review rights need a confirmed ticket. */
  @Input() myRegistration: Registration | null = null;

  reviews: Review[] = [];
  myReview: Review | null = null;
  showReviewForm = false;
  reviewRating = 0;
  reviewComment = '';
  submittingReview = false;
  /** Set once this visitor's review is accepted, before the reload brings it in. */
  private reviewPosted = false;

  ngOnInit(): void {
    this.loadReviews();
  }

  private loadReviews(): void {
    this.eventService.getEventReviews(this.event.id).subscribe({
      next: (list) => {
        this.reviews = list;
        if (this.authService.currentUser) {
          this.myReview =
            list.find((r) => r.username === this.authService.currentUser?.username) ?? null;
        }
      },
      error: () => {
        // The block shows "No reviews yet"; reviews are not essential to the page.
      },
    });
  }

  get avgRating(): number {
    if (!this.reviews.length) return 0;
    return this.reviews.reduce((s, r) => s + r.rating, 0) / this.reviews.length;
  }

  /** Reviews: confirmed attendees only, and only once the event started. */
  get canReview(): boolean {
    if (!this.authService.isLoggedIn || this.myReview || this.reviewPosted) return false;
    if (this.myRegistration?.status !== 'confirmed') return false;
    return new Date(this.event.date).getTime() <= Date.now();
  }

  submitReview(): void {
    if (!this.reviewRating) return;
    this.submittingReview = true;
    this.eventService.createReview(this.event.id, this.reviewRating, this.reviewComment).subscribe({
      next: () => {
        this.reviewPosted = true;
        // The create endpoint echoes only rating + comment (ReviewCreate), not a
        // full Review with id/author/date, so reload the list to show it.
        this.loadReviews();
        this.showReviewForm = false;
        this.reviewRating = 0;
        this.reviewComment = '';
        this.submittingReview = false;
        this.toastService.success('Review posted!');
      },
      error: (err) => {
        this.toastService.error(apiErrorMessage(err, 'Failed to post review', 'non_field_errors'));
        this.submittingReview = false;
      },
    });
  }
}
