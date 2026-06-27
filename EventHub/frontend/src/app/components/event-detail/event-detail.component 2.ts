import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService, PromoQuote, EventQuestion, WaitlistStatus, TicketType } from '../../services/event.service';
import { PaymentService } from '../../services/payment.service';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { SeoService } from '../../services/seo.service';
import { Event, Registration, Seat, SeatMap } from '../../models/models';
import { SeatSelectorComponent } from '../seat-selector/seat-selector.component';
import {
  LucideAngularModule,
  Calendar,
  MapPin,
  Users,
  Tag,
  Globe,
  Link,
  Edit,
  CheckCircle,
  Clock,
  XCircle,
  Share2,
  ChevronLeft,
  Heart,
} from 'lucide-angular';

@Component({
  selector: 'app-event-detail',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, LucideAngularModule, SeatSelectorComponent],
  template: `
    <!-- Loading -->
    @if (loading) {
      <div class="page-root-white flex items-center justify-center">
        <div class="flex flex-col items-center gap-3 text-muted-foreground">
          <span class="spinner spinner-lg"></span>
          <p class="text-sm">Loading event...</p>
        </div>
      </div>
    }

    @if (!loading && !event) {
      <div class="page-root-white flex items-center justify-center">
        <div class="text-center">
          <p class="text-foreground font-semibold mb-2">Event not found</p>
          <a routerLink="/" class="btn btn-secondary btn-sm">Back to events</a>
        </div>
      </div>
    }

    @if (!loading && event) {
      <div class="page-root-white pb-16">

        <!-- ── Pending banner ── -->
        @if (event.status === 'pending') {
          <div class="bg-[color:var(--warning-50)] border-b border-transparent">
            <div class="container py-3 flex items-center gap-3">
              <lucide-icon [img]="icons.Clock" class="w-4 h-4 text-warning flex-shrink-0" aria-hidden="true"></lucide-icon>
              <p class="text-sm text-warning font-medium">
                This event is pending approval and is not yet visible to the public.
              </p>
              @if (isAdmin) {
                <div class="ml-auto flex gap-2">
                  <button (click)="approve()" class="btn btn-sm" style="background:#15803d;color:#fff;border-color:#15803d">
                    Approve
                  </button>
                  <button (click)="reject()" class="btn btn-sm btn-danger border border-transparent">
                    Reject
                  </button>
                </div>
              }
            </div>
          </div>
        }

        <!-- ── Editorial hero ── -->
        <div class="container mt-6">
          <!-- Breadcrumb -->
          <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-4" aria-label="Breadcrumb">
            <a routerLink="/" class="hover:text-foreground transition-colors flex items-center gap-1">
              <lucide-icon [img]="icons.ChevronLeft" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
              Events
            </a>
            <span>/</span>
            <span class="text-foreground font-medium truncate max-w-xs">{{ event.title }}</span>
          </nav>

          <div class="relative rounded-2xl overflow-hidden bg-muted border border-border" style="aspect-ratio:16/7;max-height:460px">
            @if (event.image && !imageError) {
              <img [src]="event.image" [alt]="event.title" class="w-full h-full object-cover" (error)="imageError = true" />
            } @else {
              <div class="w-full h-full flex items-center justify-center" style="background:linear-gradient(135deg,#F4D9CC,#E8B8A2 55%,#CBB6A6)">
                <span class="font-display text-7xl font-semibold text-white/70 select-none">
                  {{ event.title?.charAt(0)?.toUpperCase() || 'E' }}
                </span>
              </div>
            }
            <!-- scrim -->
            <div class="absolute inset-0 pointer-events-none" style="background:linear-gradient(to top, rgba(26,23,20,0.84), rgba(26,23,20,0.18) 48%, transparent 72%)"></div>
            <!-- overlay -->
            <div class="absolute bottom-0 left-0 right-0 p-5 sm:p-8">
              <p class="kicker mb-2" style="color:rgba(255,255,255,0.82)">
                {{ event.category?.name || 'Event' }} · {{ event.date | date:'EEE, MMM d' }}
              </p>
              <h1 class="font-display font-semibold text-white leading-[1.04] max-w-3xl" style="font-size:clamp(1.9rem,3.8vw,3rem)">
                {{ event.title }}
              </h1>
            </div>
          </div>
        </div>

        <!-- ── Content ── -->
        <div class="container mt-8">

          <div class="flex flex-col lg:flex-row gap-10">

            <!-- ── Left: main content ── -->
            <div class="flex-1 min-w-0">

              <!-- Organizer actions -->
              @if (isOwner) {
                <div class="flex gap-2 flex-wrap mb-5">
                  <a [routerLink]="['/edit-event', event.id]" class="btn btn-sm btn-outline flex items-center gap-1.5">
                    <lucide-icon [img]="icons.Edit" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                    Edit
                  </a>
                  <a [routerLink]="['/organizer/events', event.id, 'ticket-types']" class="btn btn-sm btn-outline flex items-center gap-1.5">
                    <lucide-icon [img]="icons.Tag" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                    Tickets
                  </a>
                  <a [routerLink]="['/organizer/events', event.id, 'attendees']" class="btn btn-sm btn-secondary">
                    Attendees
                  </a>
                </div>
              }

              <!-- Meta chips -->
              <div class="flex flex-wrap gap-2 mb-6">
                <span class="badge badge-{{ event.status }}">
                  {{ event.status | titlecase }}
                </span>
                @if (event.is_free) {
                  <span class="badge badge-free">Free</span>
                }
                @if (event.is_online) {
                  <span class="badge badge-online">Online</span>
                }
              </div>

              <!-- Key info grid -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon [img]="icons.Calendar" class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">Date & Time</p>
                    <p class="text-sm font-semibold text-foreground">{{ event.date | date:'EEEE, MMM d, y' }}</p>
                    <p class="text-xs text-muted-foreground">{{ event.date | date:'h:mm a' }}
                      @if (event.end_date) { – {{ event.end_date | date:'h:mm a' }} }
                    </p>
                  </div>
                </div>

                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon [img]="icons.MapPin" class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">Location</p>
                    <p class="text-sm font-semibold text-foreground">{{ event.location }}</p>
                    @if (event.address) {
                      <p class="text-xs text-muted-foreground">{{ event.address }}</p>
                    }
                  </div>
                </div>

                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon [img]="icons.Users" class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">Capacity</p>
                    <p class="text-sm font-semibold text-foreground">{{ event.available_spots }} spots left</p>
                    <p class="text-xs text-muted-foreground">{{ event.registered_count }} / {{ event.max_participants }} registered</p>
                  </div>
                </div>

                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon [img]="icons.Tag" class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">Category</p>
                    <p class="text-sm font-semibold text-foreground">{{ event.category?.name || '—' }}</p>
                  </div>
                </div>
              </div>

              <!-- Online link -->
              @if (event.is_online && event.online_link) {
                <div class="flex items-center gap-2 p-3 rounded-lg border border-border bg-muted/40 mb-6">
                  <lucide-icon [img]="icons.Link" class="w-4 h-4 text-primary flex-shrink-0" aria-hidden="true"></lucide-icon>
                  <a
                    [href]="event.online_link"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-sm text-primary font-medium hover:underline truncate"
                  >{{ event.online_link }}</a>
                </div>
              }

              <!-- Organizer -->
              <div class="mb-8">
                <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Organizer</h2>
                <div class="flex items-center gap-3">
                  <div class="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary flex-shrink-0">
                    {{ event.organizer?.username?.charAt(0)?.toUpperCase() || 'O' }}
                  </div>
                  <div>
                    <p class="text-sm font-semibold text-foreground">
                      {{ event.organizer?.first_name || event.organizer?.username }}
                      {{ event.organizer?.last_name }}
                    </p>
                    <p class="text-xs text-muted-foreground">@{{ event.organizer?.username }}</p>
                  </div>
                </div>
              </div>

              <!-- Description -->
              <div class="mb-8">
                <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">About this event</h2>
                <div class="prose-sm text-foreground leading-relaxed whitespace-pre-wrap text-sm">
                  {{ event.description }}
                </div>
              </div>

              <!-- Reviews -->
              <div>
                <div class="flex items-center justify-between mb-4">
                  <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                    Reviews
                    @if (reviews.length > 0) {
                      <span class="ml-2 text-foreground normal-case font-bold">
                        {{ avgRating | number:'1.1-1' }} ★ ({{ reviews.length }})
                      </span>
                    }
                  </h2>
                  @if (authService.isLoggedIn && !myReview) {
                    <button (click)="showReviewForm = !showReviewForm" class="btn btn-sm btn-secondary">
                      Write a review
                    </button>
                  }
                </div>

                <!-- Review form -->
                @if (showReviewForm) {
                  <div class="card p-4 mb-4">
                    <div class="flex gap-1 mb-3">
                      @for (star of [1,2,3,4,5]; track star) {
                        <button
                          (click)="reviewRating = star"
                          class="text-2xl transition-transform hover:scale-110"
                          [class]="star <= reviewRating ? 'text-amber-400' : 'text-muted'"
                        >★</button>
                      }
                    </div>
                    <textarea
                      [(ngModel)]="reviewComment"
                      placeholder="Share your experience..."
                      rows="3"
                      class="input resize-none mb-3"
                    ></textarea>
                    <div class="flex gap-2">
                      <button (click)="submitReview()" [disabled]="!reviewRating || submittingReview" class="btn btn-sm btn-primary">
                        {{ submittingReview ? 'Posting...' : 'Post review' }}
                      </button>
                      <button (click)="showReviewForm = false" class="btn btn-sm btn-secondary">Cancel</button>
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
                        <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0">
                          {{ review.username.charAt(0).toUpperCase() }}
                        </div>
                        <div class="flex-1">
                          <div class="flex items-center gap-2 mb-1">
                            <span class="text-sm font-semibold text-foreground">{{ review.username }}</span>
                            <span class="text-amber-400 text-sm">{{ '★'.repeat(review.rating) }}{{ '☆'.repeat(5 - review.rating) }}</span>
                            <span class="text-xs text-muted-foreground">{{ review.created_at | date:'MMM d, y' }}</span>
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

            </div>

            <!-- ── Right: booking sidebar ── -->
            <aside class="w-full lg:w-80 xl:w-96 flex-shrink-0">
              <div class="sticky top-20 space-y-3">

                <!-- ── Price card ── -->
                <div class="rounded-2xl overflow-hidden border border-border shadow-md bg-card">

                  <!-- Gradient top bar -->
                  <div class="h-1 w-full" [class]="priceBarClass()"></div>

                  <div class="p-5">
                    <!-- Price + demand badge -->
                    <div class="mb-1">
                      <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                        {{ event.has_ticket_types ? 'Tickets from' : 'Price' }}
                      </p>
                      <div class="flex items-center gap-3 flex-wrap">
                        <span class="text-3xl font-extrabold text-foreground tracking-tight leading-none">
                          @if (event.is_free) { Free
                          } @else if (event.has_ticket_types) {
                            {{ '$' + event.price_from }}
                          } @else if (pricingData && pricingData.multiplier !== 1.0) {
                            {{ '$' + pricingData.current_price }}
                          } @else {
                            {{ '$' + event.price }}
                          }
                        </span>
                        @if (!event.has_ticket_types && pricingData && !event.is_free && pricingData.base_price !== pricingData.current_price) {
                          <span class="text-sm text-muted-foreground line-through">{{ '$' + pricingData.base_price }}</span>
                        }
                        @if (!event.has_ticket_types && pricingData && !event.is_free) {
                          <span
                            class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border"
                            [class]="demandBadgeClass(pricingData.demand_level)"
                          >{{ pricingData.demand_level }}</span>
                        }
                      </div>
                      @if (event.has_ticket_types) {
                        <p class="text-xs text-muted-foreground mt-1">{{ event.ticket_types?.length }} ticket types available</p>
                      } @else if (!event.is_free) {
                        <p class="text-xs text-muted-foreground mt-1">per ticket</p>
                      }
                    </div>

                    <!-- Divider -->
                    <div class="border-t border-border my-4"></div>

                    <!-- Spots bar -->
                    @if (event.max_participants > 0) {
                      <div class="mb-5">
                        <div class="flex justify-between text-xs mb-1.5">
                          <span class="font-semibold text-foreground">{{ event.available_spots }} spots left</span>
                          <span class="text-muted-foreground">{{ event.registered_count }} / {{ event.max_participants }}</span>
                        </div>
                        <div class="h-1.5 bg-muted rounded-full overflow-hidden">
                          <div
                            class="h-full rounded-full transition-all duration-700"
                            [style.width.%]="spotsPercent"
                            [class]="spotsPercent > 80 ? 'bg-red-400' : spotsPercent > 50 ? 'bg-amber-400' : 'bg-[color:var(--pine-50)]0'"
                          ></div>
                        </div>
                      </div>
                    }

                    <!-- CTA area -->
                    @if (!authService.isLoggedIn) {
                      <a routerLink="/login" class="btn btn-primary btn-full btn-lg">
                        Sign in to register
                      </a>
                    } @else if (isOwner) {
                      <div class="text-center py-3 px-3 rounded-xl bg-muted">
                        <p class="text-sm text-muted-foreground">You're the organizer of this event</p>
                      </div>
                    } @else if (registrationStatus === 'confirmed') {
                      <!-- Already registered -->
                      <div class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--pine-50)] mb-4">
                        <lucide-icon [img]="icons.CheckCircle" class="w-5 h-5 text-[color:var(--pine-600)] flex-shrink-0" aria-hidden="true"></lucide-icon>
                        <div>
                          <p class="text-sm font-semibold text-[color:var(--pine-600)]">You're registered!</p>
                          <p class="text-xs text-[color:var(--pine-600)]">Ticket is in My Tickets</p>
                        </div>
                      </div>
                      <a routerLink="/my-registrations" class="btn btn-primary btn-full mb-2">
                        View my ticket →
                      </a>

                      <!-- Refund / cancel logic -->
                      @if (myRegistration?.refund_request?.status === 'pending') {
                        <div class="flex items-center gap-2 p-2.5 rounded-lg bg-[color:var(--warning-50)] border border-transparent text-warning text-xs">
                          <lucide-icon [img]="icons.Clock" class="w-4 h-4 flex-shrink-0"></lucide-icon>
                          Refund requested — awaiting organizer review.
                        </div>
                      } @else if (!isPaidTicket()) {
                        <!-- Free ticket → plain cancel -->
                        <button (click)="cancelRegistration()" [disabled]="cancelling"
                          class="btn btn-ghost btn-full btn-sm text-muted-foreground hover:text-destructive">
                          {{ cancelling ? 'Processing...' : 'Cancel registration' }}
                        </button>
                      } @else if (event.refundable === false) {
                        <!-- Paid, non-refundable -->
                        <p class="text-xs text-muted-foreground text-center px-2">
                          Tickets for this event are non-refundable.
                        </p>
                      } @else {
                        <!-- Paid, refundable → request refund -->
                        <button (click)="openRefundRequest()" [disabled]="requestingRefund"
                          class="btn btn-ghost btn-full btn-sm text-muted-foreground hover:text-destructive">
                          {{ requestingRefund ? 'Submitting…' : 'Request a refund' }}
                        </button>
                      }

                    } @else if (registrationStatus === 'pending') {
                      <div class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--warning-50)] mb-4">
                        <lucide-icon [img]="icons.Clock" class="w-5 h-5 text-warning flex-shrink-0" aria-hidden="true"></lucide-icon>
                        <div>
                          <p class="text-sm font-semibold text-warning">Payment incomplete</p>
                          <p class="text-xs text-warning">Seat held — complete payment to confirm</p>
                        </div>
                      </div>
                      <button (click)="resumePayment()" [disabled]="registering" class="btn btn-primary btn-full mb-2">
                        {{ registering ? 'Processing...' : 'Complete payment' }}
                      </button>
                      <button (click)="cancelRegistration()" [disabled]="cancelling" class="btn btn-ghost btn-full btn-sm text-muted-foreground hover:text-destructive">
                        {{ cancelling ? 'Cancelling...' : 'Release seat' }}
                      </button>

                    } @else if (registrationStatus === 'rejected') {
                      <div class="flex items-center gap-3 p-3.5 rounded-xl bg-[color:var(--destructive-50)] border border-transparent">
                        <lucide-icon [img]="icons.XCircle" class="w-5 h-5 text-[color:var(--destructive)] flex-shrink-0" aria-hidden="true"></lucide-icon>
                        <div>
                          @if (myRegistration?.refund_request?.status === 'rejected') {
                            <p class="text-sm font-bold text-[color:var(--destructive)]">Refund request declined</p>
                            <p class="text-xs text-[color:var(--destructive)]">
                              {{ myRegistration?.refund_request?.organizer_note || 'The organizer declined your refund.' }}
                            </p>
                          } @else {
                            <p class="text-sm font-bold text-[color:var(--destructive)]">Registration declined</p>
                            <p class="text-xs text-[color:var(--destructive)]">Contact the organizer for more info</p>
                          }
                        </div>
                      </div>

                    } @else if (event.available_spots === 0) {
                      <!-- Sold out → waitlist -->
                      @if (waitlist?.status === 'offered') {
                        <div class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--pine-50)] mb-3">
                          <lucide-icon [img]="icons.CheckCircle" class="w-5 h-5 text-[color:var(--pine-600)] flex-shrink-0"></lucide-icon>
                          <div>
                            <p class="text-sm font-bold text-[color:var(--pine-600)]">A spot opened up for you!</p>
                            <p class="text-xs text-[color:var(--pine-600)]">Grab it before it passes to the next person.</p>
                          </div>
                        </div>
                        <button (click)="openCheckout()" class="btn btn-primary btn-full btn-lg font-bold">
                          Claim my spot
                        </button>
                      } @else if (waitlist?.status === 'waiting') {
                        <div class="flex items-center gap-3 p-3 rounded-xl border border-ember/30 bg-ember/10 mb-3">
                          <lucide-icon [img]="icons.Clock" class="w-5 h-5 text-ember flex-shrink-0"></lucide-icon>
                          <div>
                            <p class="text-sm font-bold text-foreground">You're on the waitlist</p>
                            <p class="text-xs text-ember">Position #{{ waitlist?.position }} · we'll notify you when a spot frees up.</p>
                          </div>
                        </div>
                        <button (click)="leaveWaitlist()" [disabled]="waitlisting" class="btn btn-ghost btn-full btn-sm text-muted-foreground">
                          Leave waitlist
                        </button>
                      } @else {
                        <button disabled class="btn btn-full btn-lg opacity-50 cursor-not-allowed bg-muted text-muted-foreground mb-2">
                          Sold out
                        </button>
                        @if (authService.isLoggedIn) {
                          <button (click)="joinWaitlist()" [disabled]="waitlisting" class="btn btn-secondary btn-full">
                            {{ waitlisting ? 'Joining…' : '🔔 Join the waitlist' }}
                          </button>
                        } @else {
                          <a routerLink="/login" class="btn btn-secondary btn-full">Sign in to join waitlist</a>
                        }
                      }
                    } @else {
                      <button
                        (click)="openCheckout()"
                        [disabled]="registering"
                        class="btn btn-primary btn-full btn-lg font-bold shadow-md hover:shadow-primary/30 transition-all"
                      >
                        @if (registering) {
                          <span class="spinner spinner-sm"></span> Processing...
                        } @else if (event.has_ticket_types) {
                          Choose tickets
                        } @else {
                          {{ event.is_free ? 'Register for free' : 'Get tickets — $' + event.price }}
                        }
                      </button>
                      @if (!event.is_free && !event.has_ticket_types) {
                        <a
                          [routerLink]="['/events', event.id, 'group']"
                          class="btn btn-secondary btn-full mt-2 flex items-center justify-center gap-2 text-sm"
                        >
                          <lucide-icon [img]="icons.Users" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                          Book seats for a group
                        </a>
                      }
                    }

                    <!-- Favorite + Share row -->
                    <div class="flex gap-2 mt-4 pt-4 border-t border-border">
                      @if (authService.isLoggedIn) {
                        <button
                          (click)="toggleFavorite()"
                          class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-colors border"
                          [class]="favorited ? 'border-transparent bg-[color:var(--destructive-50)] text-ember' : 'border-border hover:bg-muted text-muted-foreground'"
                        >
                          <lucide-icon [img]="icons.Heart" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                          {{ favorited ? 'Saved' : 'Save' }}
                        </button>
                      }
                      <button
                        (click)="shareEvent()"
                        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:bg-muted border border-border transition-colors"
                      >
                        <lucide-icon [img]="icons.Share2" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                        Share
                      </button>
                    </div>
                  </div>
                </div>

              </div>
            </aside>

          </div>
        </div>

        <!-- ── Checkout modal ── -->
        @if (showCheckout) {
          <div
            class="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4 animate-fade-in"
            (click)="showCheckout = false"
          >
            <div
              class="card w-full max-w-md shadow-lg animate-slide-up"
              (click)="$event.stopPropagation()"
            >
              <div class="flex items-center justify-between p-5 border-b border-border">
                <h2 class="text-base font-semibold text-foreground">Confirm registration</h2>
                <button
                  (click)="showCheckout = false"
                  class="btn btn-ghost btn-sm w-8 h-8 p-0 text-muted-foreground"
                  aria-label="Close"
                >✕</button>
              </div>

              <div class="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
                <!-- Summary -->
                <div class="p-3 rounded-lg bg-muted border border-border text-sm">
                  <div class="flex justify-between mb-1.5">
                    <span class="text-muted-foreground">Event</span>
                    <span class="font-medium text-foreground text-right max-w-[200px] truncate">{{ event.title }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-muted-foreground">Price</span>
                    <span class="font-semibold text-foreground">{{ event.is_free ? 'Free' : '$' + event.price }}</span>
                  </div>
                  @if (selectedSeat) {
                    <div class="flex justify-between border-t border-border pt-1.5 mt-1.5">
                      <span class="text-muted-foreground">Seat</span>
                      <span class="font-medium text-foreground">Row {{ selectedSeat.row }}, Seat {{ selectedSeat.col }}</span>
                    </div>
                  }
                  @if (selectedTicketType) {
                    <div class="flex justify-between border-t border-border pt-1.5 mt-1.5">
                      <span class="text-muted-foreground">Ticket</span>
                      <span class="font-medium text-foreground">{{ selectedTicketType.name }}</span>
                    </div>
                  }
                  @if (promoQuote) {
                    <div class="flex justify-between text-[color:var(--pine-600)] mt-1.5">
                      <span>Promo {{ promoQuote.code }}</span>
                      <span class="font-medium">−{{ '$' + promoQuote.savings }}</span>
                    </div>
                  }
                  @if (showFeeLines()) {
                    <div class="flex justify-between text-muted-foreground mt-1.5">
                      <span>Subtotal</span>
                      <span>{{ '$' + checkoutSubtotal }}</span>
                    </div>
                    @if (taxAmount > 0) {
                      <div class="flex justify-between text-muted-foreground">
                        <span>Tax ({{ event.tax_percent }}%)</span>
                        <span>{{ '$' + taxAmount.toFixed(2) }}</span>
                      </div>
                    }
                    @if (feeAmount > 0) {
                      <div class="flex justify-between text-muted-foreground">
                        <span>Service fee ({{ event.service_fee_percent }}%)</span>
                        <span>{{ '$' + feeAmount.toFixed(2) }}</span>
                      </div>
                    }
                  }
                  @if (selectedTicketType || promoQuote || showFeeLines()) {
                    <div class="flex justify-between border-t border-border pt-1.5 mt-1.5">
                      <span class="text-foreground font-semibold">Total</span>
                      <span class="text-foreground font-bold">{{ '$' + checkoutTotal }}</span>
                    </div>
                  }
                </div>

                <!-- Ticket tier selection -->
                @if (event.has_ticket_types) {
                  <div class="space-y-2">
                    <p class="text-sm font-semibold text-foreground">Choose your ticket</p>
                    @for (tt of event.ticket_types; track tt.id) {
                      <button
                        type="button"
                        (click)="selectTicketType(tt)"
                        [disabled]="tt.sale_state !== 'on_sale'"
                        class="w-full text-left p-3 rounded-xl border-2 transition-all"
                        [class]="selectedTicketType?.id === tt.id
                          ? 'border-primary bg-primary/5'
                          : tt.sale_state !== 'on_sale'
                            ? 'border-border opacity-50 cursor-not-allowed'
                            : 'border-border hover:border-primary/40'"
                      >
                        <div class="flex items-start justify-between gap-3">
                          <div class="min-w-0">
                            <div class="flex items-center gap-2">
                              <span class="font-semibold text-foreground">{{ tt.name }}</span>
                              @if (tt.kind === 'donation') { <span class="text-[10px] font-bold uppercase text-ember bg-ember/10 px-1.5 py-0.5 rounded">Donation</span> }
                            </div>
                            @if (tt.description) { <p class="text-xs text-muted-foreground mt-0.5">{{ tt.description }}</p> }
                            <p class="text-xs mt-1" [class]="tierAvailabilityClass(tt)">{{ tierAvailabilityLabel(tt) }}</p>
                          </div>
                          <div class="text-right flex-shrink-0">
                            <span class="font-bold text-foreground">
                              @if (tt.kind === 'free') { Free }
                              @else if (tt.kind === 'donation') { {{ '$' + tt.price }}+ }
                              @else { {{ '$' + tt.price }} }
                            </span>
                          </div>
                        </div>

                        <!-- Donation amount input -->
                        @if (selectedTicketType?.id === tt.id && tt.kind === 'donation') {
                          <div class="mt-3 flex items-center gap-2" (click)="$event.stopPropagation()">
                            <span class="text-muted-foreground">$</span>
                            <input type="number" [(ngModel)]="donationAmount" [min]="tt.price" step="1"
                              class="input flex-1" placeholder="Amount" />
                          </div>
                        }
                      </button>
                    }
                  </div>
                }

                <!-- Promo code (paid events) -->
                @if (showPromoField()) {
                  <div>
                    <label class="block text-sm font-medium text-foreground mb-1.5">Promo code</label>
                    @if (!promoQuote) {
                      <div class="flex gap-2">
                        <input
                          [(ngModel)]="promoInput"
                          (keyup.enter)="applyPromo()"
                          placeholder="Enter code"
                          class="input flex-1 uppercase"
                          [class.input-error]="promoError"
                        />
                        <button
                          (click)="applyPromo()"
                          [disabled]="!promoInput.trim() || checkingPromo"
                          class="btn btn-secondary"
                        >
                          {{ checkingPromo ? '…' : 'Apply' }}
                        </button>
                      </div>
                      @if (promoError) {
                        <p class="text-xs text-destructive mt-1">{{ promoError }}</p>
                      }
                    } @else {
                      <div class="flex items-center justify-between p-2.5 rounded-lg bg-[color:var(--pine-50)] border border-transparent">
                        <span class="text-sm font-medium text-[color:var(--pine-600)]">
                          ✓ {{ promoQuote.code }} applied — you save {{ '$' + promoQuote.savings }}
                        </span>
                        <button (click)="removePromo()" class="text-xs text-[color:var(--pine-600)] hover:underline">Remove</button>
                      </div>
                    }
                  </div>
                }

                <!-- Seat selector (only seat-map events, not ticket-typed) -->
                @if (!event.is_free && !event.has_ticket_types) {
                  <div class="border-t border-border pt-4">
                    @if (loadingSeatMap || !seatMap) {
                      <div class="flex flex-col items-center gap-2 py-6 text-muted-foreground">
                        <span class="spinner spinner-sm"></span>
                        <span class="text-sm">Loading seats…</span>
                      </div>
                    } @else {
                      <app-seat-selector
                        [seats]="seatMap.seats"
                        [eventId]="event.id"
                        (seatSelected)="selectedSeat = $event"
                      ></app-seat-selector>
                    }
                  </div>
                }

                <!-- Custom organizer questions -->
                @if (questions.length) {
                  <div class="border-t border-border pt-4 space-y-3">
                    <p class="text-sm font-semibold text-foreground">A few questions from the organizer</p>
                    @for (q of questions; track q.id) {
                      <div>
                        <label class="block text-sm font-medium text-foreground mb-1.5">
                          {{ q.label }}
                          @if (q.is_required) { <span class="text-destructive">*</span> }
                        </label>

                        @switch (q.question_type) {
                          @case ('textarea') {
                            <textarea [(ngModel)]="answers[q.id]" rows="2" class="input resize-none w-full"></textarea>
                          }
                          @case ('dropdown') {
                            <select [(ngModel)]="answers[q.id]" class="input w-full">
                              <option value="">Select…</option>
                              @for (opt of q.options; track opt) { <option [value]="opt">{{ opt }}</option> }
                            </select>
                          }
                          @case ('checkbox') {
                            <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                              <input type="checkbox" [(ngModel)]="answers[q.id]" class="w-4 h-4 rounded" />
                              Yes
                            </label>
                          }
                          @case ('date') {
                            <input type="date" [(ngModel)]="answers[q.id]" class="input w-full" />
                          }
                          @case ('phone') {
                            <input type="tel" [(ngModel)]="answers[q.id]" placeholder="+1 555 000 0000" class="input w-full" />
                          }
                          @default {
                            <input type="text" [(ngModel)]="answers[q.id]" class="input w-full" />
                          }
                        }
                      </div>
                    }
                  </div>
                }

                <!-- Notes -->
                <div>
                  <label for="reg-notes" class="block text-sm font-medium text-foreground mb-1.5">
                    Additional notes <span class="text-muted-foreground font-normal">(optional)</span>
                  </label>
                  <textarea
                    id="reg-notes"
                    [(ngModel)]="registrationNotes"
                    placeholder="Dietary requirements, questions for the organizer..."
                    rows="3"
                    class="input resize-none"
                  ></textarea>
                </div>
              </div>

              <div class="flex items-center gap-3 p-5 border-t border-border">
                <button (click)="showCheckout = false" class="btn btn-secondary flex-1">
                  Cancel
                </button>
                <button
                  (click)="registerForEvent()"
                  [disabled]="registering || !canConfirm()"
                  class="btn btn-primary flex-1"
                >
                  @if (registering) {
                    <span class="spinner spinner-sm"></span>
                    Processing...
                  } @else if (event.has_ticket_types && !selectedTicketType) {
                    Choose a ticket
                  } @else if (!event.is_free && !event.has_ticket_types && (loadingSeatMap || !seatMap)) {
                    Loading seats…
                  } @else if (!event.is_free && !event.has_ticket_types && !selectedSeat) {
                    Select a seat to continue
                  } @else if (confirmIsPaid()) {
                    Proceed to payment — {{ '$' + checkoutTotal }}
                  } @else {
                    Confirm registration
                  }
                </button>
              </div>
            </div>
          </div>
        }

        <!-- Refund request modal -->
        @if (showRefundModal) {
          <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 animate-fade-in" (click)="showRefundModal = false">
            <div class="card w-full max-w-md p-6 animate-slide-up" (click)="$event.stopPropagation()">
              <h3 class="text-lg font-bold text-foreground mb-1">Request a refund</h3>
              <p class="text-sm text-muted-foreground mb-4">
                The organizer will review your request and approve or decline it. You'll be notified of their decision.
              </p>
              <label class="block text-sm font-medium text-foreground mb-1.5">Reason <span class="text-muted-foreground font-normal">(optional)</span></label>
              <textarea [(ngModel)]="refundReason" rows="3" placeholder="Why are you requesting a refund?" class="input resize-none w-full mb-4"></textarea>
              <div class="flex gap-2">
                <button (click)="showRefundModal = false" class="btn btn-secondary flex-1">Cancel</button>
                <button (click)="submitRefundRequest()" [disabled]="requestingRefund" class="btn btn-primary flex-1">
                  {{ requestingRefund ? 'Submitting…' : 'Submit request' }}
                </button>
              </div>
            </div>
          </div>
        }

      </div>
    }
  `,
})
export class EventDetailComponent implements OnInit {
  event: Event | null = null;
  loading = false;
  registering = false;
  cancelling = false;
  imageError = false;

  registrationStatus: string | null = null;
  registrationId: number | null = null;
  myRegistration: Registration | null = null;
  requestingRefund = false;
  showRefundModal = false;
  refundReason = '';
  showCheckout = false;
  registrationNotes = '';
  pricingData: any = null;

  // Seat selection
  seatMap: SeatMap | null = null;
  selectedSeat: Seat | null = null;
  loadingSeatMap = false;

  // Promo code
  promoInput = '';
  promoQuote: PromoQuote | null = null;
  promoError = '';
  checkingPromo = false;

  // Ticket types
  selectedTicketType: TicketType | null = null;
  donationAmount: number | null = null;

  // Custom questions
  questions: EventQuestion[] = [];
  answers: Record<number, any> = {};

  // Waitlist
  waitlist: WaitlistStatus | null = null;
  waitlisting = false;

  // Affiliate referral captured from ?ref=
  affiliateRef = '';

  get isOwner(): boolean {
    return !!this.authService.currentUser &&
      this.authService.currentUser.id === this.event?.organizer?.id;
  }

  get isAdmin(): boolean {
    return !!this.authService.currentUser?.is_superuser;
  }

  get spotsPercent(): number {
    if (!this.event || !this.event.max_participants) return 0;
    return (this.event.registered_count / this.event.max_participants) * 100;
  }

  readonly icons = {
    Calendar, MapPin, Users, Tag, Globe, Link, Edit,
    CheckCircle, Clock, XCircle, Share2, ChevronLeft, Heart, UsersGroup: Users,
  };

  // Favorites
  favorited = false;

  // Reviews
  reviews: any[] = [];
  myReview: any = null;
  showReviewForm = false;
  reviewRating = 0;
  reviewComment = '';
  submittingReview = false;
  get avgRating(): number {
    if (!this.reviews.length) return 0;
    return this.reviews.reduce((s, r) => s + r.rating, 0) / this.reviews.length;
  }

  constructor(
    private eventService: EventService,
    private paymentService: PaymentService,
    public authService: AuthService,
    private route: ActivatedRoute,
    private router: Router,
    private toastService: ToastService,
    private modalService: ModalService,
    private seoService: SeoService,
  ) {}

  ngOnInit(): void {
    // Capture an affiliate referral (?ref=CODE): record a click and remember
    // the code so it's attributed when this visitor registers.
    const ref = this.route.snapshot.queryParamMap.get('ref');
    const id = this.route.snapshot.paramMap.get('id');
    if (ref && id) {
      this.affiliateRef = ref;
      this.eventService.trackAffiliateClick(Number(id), ref).subscribe({ error: () => {} });
    }
    this.loadEvent();
  }

  loadEvent(quiet = false): void {
    if (!quiet) this.loading = true;

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) { this.loading = false; return; }

    this.eventService.getEvent(Number(id)).subscribe({
      next: ev => {
        this.event = ev;
        this.seoService.setEvent(ev);
        if (!quiet) this.loading = false;
        // Check waitlist status when the event is full.
        if (ev.available_spots === 0) this.loadWaitlistStatus();
        // Load dynamic pricing for paid events
        if (!ev.is_free) {
          this.eventService.getEventPricing(ev.id).subscribe({
            next: p => { this.pricingData = p; },
            error: () => {},
          });
        }
        // Load reviews
        this.eventService.getEventReviews(ev.id).subscribe({
          next: list => {
            this.reviews = list;
            if (this.authService.currentUser) {
              this.myReview = list.find((r: any) => r.username === this.authService.currentUser?.username) ?? null;
            }
          },
          error: () => {},
        });
        // Load favorite status
        if (this.authService.isLoggedIn) {
          this.eventService.getFavoriteStatus(ev.id).subscribe({
            next: res => { this.favorited = res.favorited; },
            error: () => {},
          });
        }
      },
      error: () => { if (!quiet) this.loading = false; },
    });

    if (this.authService.isLoggedIn) {
      this.eventService.getMyRegistrations().subscribe({
        next: res => {
          const reg = res.results.find(r => r.event.id === Number(id));
          if (reg) {
            this.registrationStatus = reg.status;
            this.registrationId = reg.id;
            this.myRegistration = reg;
          }
        },
        error: () => {},
      });
    }
  }

  toggleFavorite(): void {
    if (!this.event) return;
    this.eventService.toggleFavorite(this.event.id).subscribe({
      next: res => {
        this.favorited = res.favorited;
        this.toastService.success(res.favorited ? '❤ Added to favorites' : 'Removed from favorites');
      },
      error: () => this.toastService.error('Failed to update favorites'),
    });
  }

  submitReview(): void {
    if (!this.event || !this.reviewRating) return;
    this.submittingReview = true;
    this.eventService.createReview(this.event.id, this.reviewRating, this.reviewComment).subscribe({
      next: review => {
        this.reviews = [review, ...this.reviews];
        this.myReview = review;
        this.showReviewForm = false;
        this.reviewRating = 0;
        this.reviewComment = '';
        this.submittingReview = false;
        this.toastService.success('Review posted!');
      },
      error: err => {
        this.toastService.error(err.error?.non_field_errors?.[0] || 'Failed to post review');
        this.submittingReview = false;
      },
    });
  }

  demandBadgeClass(level: string): string {
    const map: Record<string, string> = {
      low:    'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]',
      medium: 'bg-[color:var(--warning-50)] text-warning',
      high:   'bg-orange-100 text-orange-700',
      surge:  'bg-[color:var(--destructive-50)] text-[color:var(--destructive)] animate-pulse',
    };
    return map[level] ?? 'bg-muted text-muted-foreground';
  }

  priceBarClass(): string {
    if (this.event?.is_free) return 'bg-gradient-to-r from-emerald-400 to-teal-500';
    const d = this.pricingData?.demand_level;
    if (d === 'surge') return 'bg-gradient-to-r from-red-500 to-orange-500';
    if (d === 'high')  return 'bg-gradient-to-r from-orange-400 to-amber-400';
    return 'bg-gradient-to-r from-ember to-pine';
  }

  openCheckout(): void {
    if (!this.event) return;
    this.showCheckout = true;

    // Load custom questions once.
    if (!this.questions.length) {
      this.eventService.getEventQuestions(this.event.id).subscribe({
        next: qs => { this.questions = qs; },
        error: () => {},
      });
    }

    // Загружаем seat map для платных событий
    if (!this.event.is_free && !this.seatMap) {
      this.loadingSeatMap = true;
      this.eventService.getSeatMap(this.event.id).subscribe({
        next: (sm: SeatMap) => {
          this.seatMap = sm;
          this.loadingSeatMap = false;
        },
        error: () => {
          this.loadingSeatMap = false;
          this.toastService.error('Failed to load seat map');
        },
      });
    }
  }

  loadWaitlistStatus(): void {
    if (!this.event || !this.authService.isLoggedIn) return;
    if (this.event.available_spots > 0) return;
    this.eventService.getWaitlistStatus(this.event.id).subscribe({
      next: s => { this.waitlist = s; },
      error: () => {},
    });
  }

  joinWaitlist(): void {
    if (!this.event) return;
    this.waitlisting = true;
    this.eventService.joinWaitlist(this.event.id).subscribe({
      next: s => {
        this.waitlist = s;
        this.waitlisting = false;
        if (s.status === 'spots_available') {
          this.toastService.success('A spot is available — you can register now!');
          this.loadEvent(true);
        } else if (s.status === 'offered') {
          this.toastService.success('A spot is ready for you! Claim it now.');
        } else {
          this.toastService.success(`You're on the waitlist (position #${s.position}).`);
        }
      },
      error: () => { this.waitlisting = false; this.toastService.error('Could not join waitlist.'); },
    });
  }

  leaveWaitlist(): void {
    if (!this.event) return;
    this.waitlisting = true;
    this.eventService.leaveWaitlist(this.event.id).subscribe({
      next: () => {
        this.waitlist = { status: 'not_joined' };
        this.waitlisting = false;
        this.toastService.success('Left the waitlist.');
      },
      error: () => { this.waitlisting = false; this.toastService.error('Could not leave waitlist.'); },
    });
  }

  // ── Ticket types ──
  selectTicketType(tt: TicketType): void {
    if (tt.sale_state !== 'on_sale') return;
    this.selectedTicketType = tt;
    if (tt.kind === 'donation') {
      this.donationAmount = Number(tt.price);
    } else {
      this.donationAmount = null;
    }
    // Promo no longer applies once a free tier is picked.
    if (tt.kind === 'free') this.removePromo();
  }

  showPromoField(): boolean {
    if (!this.event) return false;
    if (this.event.has_ticket_types) {
      // Only for a selected paid/donation tier.
      return !!this.selectedTicketType && this.selectedTicketType.kind !== 'free';
    }
    return !this.event.is_free;
  }

  confirmIsPaid(): boolean {
    if (!this.event) return false;
    if (this.event.has_ticket_types) {
      return !!this.selectedTicketType && this.selectedTicketType.kind !== 'free'
        && Number(this.checkoutTotal) > 0;
    }
    return !this.event.is_free;
  }

  canConfirm(): boolean {
    if (!this.event) return false;
    if (this.event.has_ticket_types) return !!this.selectedTicketType;
    if (this.event.is_free) return true;
    return !!this.seatMap && !!this.selectedSeat;
  }

  /** Base price after tier/seat + promo, before tax & fees. */
  get checkoutSubtotalNum(): number {
    if (!this.event) return 0;
    let base = 0;
    if (this.selectedTicketType) {
      if (this.selectedTicketType.kind === 'free') base = 0;
      else if (this.selectedTicketType.kind === 'donation') base = Number(this.donationAmount || this.selectedTicketType.price);
      else base = Number(this.selectedTicketType.price);
    } else if (this.selectedSeat) {
      base = Number((this.selectedSeat as any).price ?? this.event.price);
    } else {
      base = Number(this.event.price);
    }
    if (this.promoQuote) {
      if (this.promoQuote.discount_type === 'percent') {
        base = base * (1 - Number(this.promoQuote.discount_value) / 100);
      } else {
        base = Math.max(0, base - Number(this.promoQuote.discount_value));
      }
    }
    return base;
  }

  get checkoutSubtotal(): string { return this.checkoutSubtotalNum.toFixed(2); }

  get taxAmount(): number {
    const pct = Number(this.event?.tax_percent || 0);
    return this.checkoutSubtotalNum > 0 ? this.checkoutSubtotalNum * pct / 100 : 0;
  }

  get feeAmount(): number {
    const pct = Number(this.event?.service_fee_percent || 0);
    return this.checkoutSubtotalNum > 0 ? this.checkoutSubtotalNum * pct / 100 : 0;
  }

  showFeeLines(): boolean {
    if (!this.event) return false;
    const hasFees = Number(this.event.tax_percent || 0) > 0 || Number(this.event.service_fee_percent || 0) > 0;
    return hasFees && this.event.fees_passed_to_buyer !== false && this.checkoutSubtotalNum > 0;
  }

  get checkoutTotal(): string {
    let total = this.checkoutSubtotalNum;
    if (this.event?.fees_passed_to_buyer !== false) {
      total += this.taxAmount + this.feeAmount;
    }
    return total.toFixed(2);
  }

  tierAvailabilityLabel(tt: TicketType): string {
    switch (tt.sale_state) {
      case 'sold_out': return 'Sold out';
      case 'scheduled': return 'Sales not started yet';
      case 'ended': return 'Sales ended';
      case 'inactive': return 'Unavailable';
      default:
        if (tt.available !== null && tt.available <= 10) return `Only ${tt.available} left`;
        return 'Available';
    }
  }

  tierAvailabilityClass(tt: TicketType): string {
    if (tt.sale_state !== 'on_sale') return 'text-muted-foreground';
    if (tt.available !== null && tt.available <= 10) return 'text-warning font-medium';
    return 'text-[color:var(--pine-600)]';
  }

  applyPromo(): void {
    if (!this.event || !this.promoInput.trim()) return;
    this.checkingPromo = true;
    this.promoError = '';
    this.eventService.validatePromo(this.event.id, this.promoInput.trim()).subscribe({
      next: q => { this.promoQuote = q; this.checkingPromo = false; },
      error: err => {
        this.promoError = err.error?.error || 'Invalid promo code';
        this.promoQuote = null;
        this.checkingPromo = false;
      },
    });
  }

  removePromo(): void {
    this.promoQuote = null;
    this.promoInput = '';
    this.promoError = '';
  }

  registerForEvent(): void {
    if (!this.event) return;

    // Ticket-typed events require a tier; seat-map events require a seat.
    if (this.event.has_ticket_types) {
      if (!this.selectedTicketType) { this.toastService.error('Please choose a ticket'); return; }
      if (this.selectedTicketType.kind === 'donation') {
        const min = Number(this.selectedTicketType.price);
        if (Number(this.donationAmount) < min) {
          this.toastService.error(`Minimum contribution is $${min}`);
          return;
        }
      }
    } else if (!this.event.is_free && !this.selectedSeat) {
      this.toastService.error('Please select a seat');
      return;
    }

    // Enforce required custom questions.
    const missing = this.questions.find(q => q.is_required && !this.answers[q.id] && this.answers[q.id] !== false);
    if (missing) {
      this.toastService.error(`Please answer: ${missing.label}`);
      return;
    }

    this.registering = true;

    const payload: Record<string, any> = { notes: this.registrationNotes };
    if (this.selectedSeat) payload['seat_id'] = this.selectedSeat.id;
    if (this.selectedTicketType) payload['ticket_type_id'] = this.selectedTicketType.id;
    if (this.selectedTicketType?.kind === 'donation') payload['donation_amount'] = this.donationAmount;
    if (this.promoQuote) payload['promo_code'] = this.promoQuote.code;
    if (this.questions.length) payload['answers'] = this.answers;
    if (this.affiliateRef) payload['affiliate_code'] = this.affiliateRef;

    this.eventService.registerForEvent(this.event.id, payload).subscribe({
      next: (registration: Registration) => {
        this.registrationStatus = registration.status;
        this.registrationId = registration.id;
        this.registrationNotes = '';

        // Status is the source of truth: pending → pay, confirmed → done.
        // This correctly handles free tiers (confirmed) and paid (pending).
        if (registration.status === 'pending') {
          this.paymentService.createCheckoutSession(registration.id).subscribe({
            next: res => { window.location.href = res.checkout_url; },
            error: () => {
              this.registering = false;
              this.showCheckout = false;
              this.toastService.error('Payment setup failed. Your spot is held for 10 minutes — try again.');
              this.loadEvent(true);
            },
          });
          // Redirecting to Stripe — keep `registering` true.
        } else {
          this.registering = false;
          this.showCheckout = false;
          this.toastService.success('You\'re registered!');
          if (this.event) this.event.available_spots--;
          this.loadEvent(true);
        }
      },
      error: err => {
        this.toastService.error(
          err.error?.detail || err.error?.error || 'Registration failed. Please try again.'
        );
        this.registering = false;
      },
    });
  }

  /** Resume payment for a paid registration that is still pending (unpaid). */
  resumePayment(): void {
    if (!this.registrationId) return;
    this.registering = true;
    this.paymentService.createCheckoutSession(this.registrationId).subscribe({
      next: res => { window.location.href = res.checkout_url; },
      error: err => {
        this.registering = false;
        // Payment already went through but the registration was stuck as
        // pending — the backend now reconciles it, so refresh to show it.
        if (err.error?.error === 'Payment already completed') {
          this.toastService.success('Payment already completed — your ticket is confirmed.');
        } else {
          this.toastService.error('Could not start payment. Your seat hold may have expired.');
        }
        this.loadEvent(true);
      },
    });
  }

  isPaidTicket(): boolean {
    return this.registrationStatus === 'confirmed' && !this.event?.is_free;
  }

  async cancelRegistration(): Promise<void> {
    if (!this.event) return;
    const confirmed = await this.modalService.open({
      title: 'Cancel Registration',
      message: `Cancel your registration for "${this.event.title}"?`,
      confirmText: 'Yes, cancel',
      cancelText: 'Keep it',
      isDestructive: true,
    });
    if (!confirmed) return;
    this.cancelling = true;

    this.eventService.cancelRegistration(this.event.id).subscribe({
      next: () => {
        if (this.event) this.event.available_spots++;
        this.registrationStatus = null;
        this.cancelling = false;
        this.toastService.success('Registration cancelled.');
        this.loadEvent(true);
      },
      error: (err) => {
        this.cancelling = false;
        this.toastService.error(err.error?.error || 'Failed to cancel registration.');
      },
    });
  }

  openRefundRequest(): void {
    this.refundReason = '';
    this.showRefundModal = true;
  }

  submitRefundRequest(): void {
    if (!this.event) return;
    this.requestingRefund = true;
    this.eventService.requestRefund(this.event.id, this.refundReason).subscribe({
      next: () => {
        this.requestingRefund = false;
        this.showRefundModal = false;
        this.toastService.success('Refund request submitted — the organizer will review it.');
        this.loadEvent(true);
      },
      error: err => {
        this.requestingRefund = false;
        this.toastService.error(err.error?.error || 'Could not submit refund request.');
      },
    });
  }

  async approve(): Promise<void> {
    if (!this.event) return;
    const confirmed = await this.modalService.open({
      title: 'Approve Event',
      message: `Approve and publish "${this.event.title}"?`,
      confirmText: 'Approve',
      cancelText: 'Cancel',
    });
    if (!confirmed) return;
    this.eventService.approveEvent(this.event.id).subscribe({
      next: () => {
        this.toastService.success('Event approved and published.');
        this.loadEvent(true);
      },
      error: () => this.toastService.error('Failed to approve event.'),
    });
  }

  async reject(): Promise<void> {
    if (!this.event) return;
    const confirmed = await this.modalService.open({
      title: 'Reject Event',
      message: `Reject "${this.event.title}"? The organizer will see it as declined.`,
      confirmText: 'Reject',
      cancelText: 'Cancel',
      isDestructive: true,
    });
    if (!confirmed) return;
    this.eventService.rejectEvent(this.event.id).subscribe({
      next: () => {
        this.toastService.success('Event rejected.');
        this.loadEvent(true);
      },
      error: () => this.toastService.error('Failed to reject event.'),
    });
  }

  async shareEvent(): Promise<void> {
    if (!this.event) return;
    const url = window.location.href;
    if (navigator.share) {
      try { await navigator.share({ title: this.event.title, url }); } catch {}
    } else {
      try {
        await navigator.clipboard.writeText(url);
        this.toastService.success('Link copied!');
      } catch { this.toastService.error('Failed to copy link.'); }
    }
  }
}
