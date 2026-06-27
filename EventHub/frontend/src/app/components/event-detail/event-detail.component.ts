import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import { EventService, WaitlistStatus, QueueStatus } from '../../services/event.service';
import { PaymentService } from '../../services/payment.service';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { SeoService } from '../../services/seo.service';
import { Event, Registration } from '../../models/models';
import { EventReviewsComponent } from './event-reviews.component';
import { EventCheckoutModalComponent } from './event-checkout-modal.component';
import { RefundRequestModalComponent } from './refund-request-modal.component';
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

/** Event page: hero, status banners, key info and the booking sidebar.
 *
 *  Checkout selections live in EventCheckoutModalComponent, reviews in
 *  EventReviewsComponent, refunds in RefundRequestModalComponent — this
 *  component orchestrates loading, registration/payment/queue flow and
 *  the organizer/admin actions. */
@Component({
  selector: 'app-event-detail',
  standalone: true,
  imports: [
    CommonModule, RouterModule, LucideAngularModule,
    EventReviewsComponent, EventCheckoutModalComponent, RefundRequestModalComponent,
  ],
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

        <!-- ── Draft banner: owner can send it to review ── -->
        @if (event.status === 'draft' && isOwner) {
          <div class="bg-muted border-b border-border">
            <div class="container py-3 flex items-center gap-3 flex-wrap">
              <lucide-icon [img]="icons.Edit" class="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true"></lucide-icon>
              <p class="text-sm text-foreground font-medium">
                This is a draft — only you can see it. Submit it for review to get it published.
              </p>
              <button (click)="submitForReview()" [disabled]="submittingForReview" class="btn btn-sm btn-primary ml-auto">
                {{ submittingForReview ? 'Submitting…' : 'Submit for review' }}
              </button>
            </div>
          </div>
        }

        <!-- ── Cancelled banner ── -->
        @if (event.status === 'cancelled') {
          <div class="bg-[color:var(--destructive-50)] border-b border-transparent">
            <div class="container py-3 flex items-center gap-3">
              <lucide-icon [img]="icons.XCircle" class="w-4 h-4 text-[color:var(--destructive)] flex-shrink-0" aria-hidden="true"></lucide-icon>
              <p class="text-sm text-[color:var(--destructive)] font-medium">
                This event has been cancelled by the organizer. Paid tickets were refunded.
              </p>
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
              <app-event-reviews [event]="event" [myRegistration]="myRegistration"></app-event-reviews>

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
                    @if (event.status === 'cancelled' || event.status === 'completed') {
                      <div class="text-center py-3 px-3 rounded-xl bg-muted">
                        <p class="text-sm text-muted-foreground">
                          {{ event.status === 'cancelled' ? 'This event was cancelled — sales are closed.' : 'This event has ended.' }}
                        </p>
                      </div>
                    } @else if (!authService.isLoggedIn) {
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

                      <!-- Refund logic: confirmed tickets can't be cancelled by
                           the client — paid ones can only request a refund,
                           free ones have no exit action. -->
                      @if (myRegistration?.refund_request?.status === 'pending') {
                        <div class="flex items-center gap-2 p-2.5 rounded-lg bg-[color:var(--warning-50)] border border-transparent text-warning text-xs">
                          <lucide-icon [img]="icons.Clock" class="w-4 h-4 flex-shrink-0"></lucide-icon>
                          Refund requested — awaiting organizer review.
                        </div>
                      } @else if (myRegistration?.is_checked_in) {
                        <!-- Scanned at the door → service delivered, no refund -->
                        <p class="text-xs text-muted-foreground text-center px-2">
                          Ticket was used for entry — refunds are unavailable.
                        </p>
                      } @else if (!isPaidTicket()) {
                        <!-- Free ticket → no cancel / refund actions -->
                      } @else if (event.refundable === false) {
                        <!-- Paid, non-refundable -->
                        <p class="text-xs text-muted-foreground text-center px-2">
                          Tickets for this event are non-refundable.
                        </p>
                      } @else {
                        <!-- Paid, refundable → request refund -->
                        <button (click)="showRefundModal = true"
                          class="btn btn-ghost btn-full btn-sm text-muted-foreground hover:text-destructive">
                          Request a refund
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

                    } @else if (!canBuy) {
                      <!-- Organizers/admins manage events, they don't buy tickets -->
                      <div class="text-center py-3 px-3 rounded-xl bg-muted">
                        <p class="text-sm text-muted-foreground">
                          Only attendee accounts can buy tickets — organizer and admin accounts can't register.
                        </p>
                      </div>
                    } @else if (waitlist?.status === 'offered') {
                      <!-- Waitlist offer — reserved spot, shown regardless of the public counter -->
                      <div class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--pine-50)] mb-3">
                        <lucide-icon [img]="icons.CheckCircle" class="w-5 h-5 text-[color:var(--pine-600)] flex-shrink-0"></lucide-icon>
                        <div>
                          <p class="text-sm font-bold text-[color:var(--pine-600)]">A spot opened up for you!</p>
                          <p class="text-xs text-[color:var(--pine-600)]">It's reserved for a limited time — grab it before it passes on.</p>
                        </div>
                      </div>
                      <button (click)="showCheckout = true" class="btn btn-primary btn-full btn-lg font-bold">
                        Claim my spot
                      </button>
                    } @else if (queueInfo && queueInfo.status === 'queued') {
                      <!-- Virtual waiting room -->
                      <div class="flex items-center gap-3 p-3 rounded-xl border border-ember/30 bg-ember/10 mb-3">
                        <span class="spinner spinner-sm flex-shrink-0"></span>
                        <div>
                          <p class="text-sm font-bold text-foreground">You're in the queue</p>
                          <p class="text-xs text-ember">
                            Position #{{ queueInfo.position }} of {{ queueInfo.total }} · ~{{ queueInfo.wait_minutes }} min.
                            We'll start your checkout automatically.
                          </p>
                        </div>
                      </div>
                      <button (click)="leaveQueue()" class="btn btn-ghost btn-full btn-sm text-muted-foreground">
                        Leave queue
                      </button>
                    } @else if (event.available_spots === 0) {
                      <!-- Sold out → waitlist -->
                      @if (waitlist?.status === 'waiting') {
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
                        (click)="showCheckout = true"
                        [disabled]="registering"
                        class="btn btn-primary btn-full btn-lg font-bold shadow-md hover:shadow-primary/30 transition-all"
                      >
                        @if (registering) {
                          <span class="spinner spinner-sm"></span> Processing...
                        } @else if (event.has_ticket_types) {
                          Choose tickets
                        } @else {
                          {{ event.is_free ? 'Register for free' : 'Get tickets — $' + currentGaPrice }}
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
          <app-event-checkout-modal
            [event]="event"
            [currentGaPrice]="currentGaPrice"
            [registering]="registering"
            (closed)="showCheckout = false"
            (confirmed)="registerForEvent($event)"
          ></app-event-checkout-modal>
        }

        <!-- Refund request modal -->
        @if (showRefundModal) {
          <app-refund-request-modal
            [event]="event"
            (closed)="showRefundModal = false"
            (submitted)="onRefundSubmitted()"
          ></app-refund-request-modal>
        }

      </div>
    }
  `,
})
export class EventDetailComponent implements OnInit, OnDestroy {
  event: Event | null = null;
  loading = false;
  registering = false;
  cancelling = false;
  imageError = false;

  registrationStatus: string | null = null;
  registrationId: number | null = null;
  myRegistration: Registration | null = null;
  showRefundModal = false;
  showCheckout = false;
  pricingData: any = null;

  // Virtual waiting queue
  queueInfo: QueueStatus | null = null;
  private queueTimer?: ReturnType<typeof setInterval>;
  private pendingQueuePayload: Record<string, any> | null = null;

  // Draft → review
  submittingForReview = false;

  // Waitlist
  waitlist: WaitlistStatus | null = null;
  waitlisting = false;

  // Affiliate referral captured from ?ref=
  affiliateRef = '';

  // Favorites
  favorited = false;

  get isOwner(): boolean {
    return !!this.authService.currentUser &&
      this.authService.currentUser.id === this.event?.organizer?.id;
  }

  get isAdmin(): boolean {
    return !!this.authService.currentUser?.is_superuser;
  }

  /** Business rule: only attendee accounts buy tickets. */
  get canBuy(): boolean {
    const u = this.authService.currentUser;
    return !!u && !u.is_staff && !u.is_superuser && u.profile?.role !== 'organizer';
  }

  get spotsPercent(): number {
    if (!this.event || !this.event.max_participants) return 0;
    return (this.event.registered_count / this.event.max_participants) * 100;
  }

  readonly icons = {
    Calendar, MapPin, Users, Tag, Globe, Link, Edit,
    CheckCircle, Clock, XCircle, Share2, ChevronLeft, Heart, UsersGroup: Users,
  };

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
      // Count each visitor's click once per session, not on every refresh.
      const clickKey = `aff_click_${id}_${ref}`;
      if (!sessionStorage.getItem(clickKey)) {
        sessionStorage.setItem(clickKey, '1');
        this.eventService.trackAffiliateClick(Number(id), ref).subscribe({ error: () => {} });
      }
    }
    this.loadEvent();
  }

  ngOnDestroy(): void {
    this.stopQueuePolling();
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
        // Waitlist offers reserve a spot, so check the status even when the
        // public counter shows availability.
        this.loadWaitlistStatus();
        // Load dynamic pricing for paid events
        if (!ev.is_free) {
          this.eventService.getEventPricing(ev.id).subscribe({
            next: p => { this.pricingData = p; },
            error: () => {},
          });
        }
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
      // Server-side filter — immune to pagination (a user with many tickets
      // would otherwise "lose" their registration past page one).
      this.eventService.getMyRegistrations({ event: Number(id) }).subscribe({
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

  /** The price actually charged for a flat-priced (GA) ticket right now. */
  get currentGaPrice(): string {
    if (!this.event) return '0.00';
    return this.pricingData?.current_price ?? this.event.price;
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

  loadWaitlistStatus(): void {
    if (!this.event || !this.authService.isLoggedIn || this.isOwner) return;
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

  /** Run the registration with the payload assembled by the checkout modal. */
  registerForEvent(payload: Record<string, any>): void {
    if (!this.event) return;
    if (this.affiliateRef) payload['affiliate_code'] = this.affiliateRef;

    this.registering = true;

    this.eventService.registerForEvent(this.event.id, payload).subscribe({
      next: (registration: Registration) => {
        this.registrationStatus = registration.status;
        this.registrationId = registration.id;

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
        this.registering = false;
        // High-demand event → enter the virtual waiting room and retry
        // automatically once admitted.
        if (err.error?.error === 'QUEUE_REQUIRED') {
          this.showCheckout = false;
          this.enterQueue(payload);
          return;
        }
        this.toastService.error(
          err.error?.detail || err.error?.error || 'Registration failed. Please try again.'
        );
      },
    });
  }

  // ── Virtual waiting queue ──

  private enterQueue(payload: Record<string, any>): void {
    if (!this.event) return;
    this.pendingQueuePayload = payload;
    this.eventService.queueJoin(this.event.id).subscribe({
      next: s => {
        this.queueInfo = s;
        if (s.status === 'queued') {
          this.toastService.info(`High demand — you're #${s.position} in the queue.`);
          this.startQueuePolling();
        } else {
          // not_needed / already admitted → just retry.
          this.retryAfterQueue();
        }
      },
      error: () => this.toastService.error('Could not join the queue. Please try again.'),
    });
  }

  private startQueuePolling(): void {
    this.stopQueuePolling();
    this.queueTimer = setInterval(() => {
      if (!this.event) return;
      this.eventService.queueStatus(this.event.id).subscribe({
        next: s => {
          this.queueInfo = s;
          if (s.status === 'admitted' || s.status === 'not_needed') {
            this.stopQueuePolling();
            this.queueInfo = null;
            this.toastService.success('You\'re in! Completing your registration…');
            this.retryAfterQueue();
          }
        },
        error: () => {},
      });
    }, 5000);
  }

  private stopQueuePolling(): void {
    if (this.queueTimer) {
      clearInterval(this.queueTimer);
      this.queueTimer = undefined;
    }
  }

  private retryAfterQueue(): void {
    const payload = this.pendingQueuePayload;
    this.pendingQueuePayload = null;
    if (!payload || !this.event) return;
    this.registering = true;
    this.eventService.registerForEvent(this.event.id, payload).subscribe({
      next: (registration: Registration) => {
        this.registrationStatus = registration.status;
        this.registrationId = registration.id;
        if (registration.status === 'pending') {
          this.paymentService.createCheckoutSession(registration.id).subscribe({
            next: res => { window.location.href = res.checkout_url; },
            error: () => {
              this.registering = false;
              this.toastService.error('Payment setup failed. Your spot is held for 10 minutes — try again.');
              this.loadEvent(true);
            },
          });
        } else {
          this.registering = false;
          this.toastService.success('You\'re registered!');
          this.loadEvent(true);
        }
      },
      error: err => {
        this.registering = false;
        this.toastService.error(err.error?.error || 'Registration failed — please try again.');
        this.loadEvent(true);
      },
    });
  }

  leaveQueue(): void {
    this.stopQueuePolling();
    this.queueInfo = null;
    this.pendingQueuePayload = null;
  }

  /** Draft → pending: owner sends the event to admin review. */
  submitForReview(): void {
    if (!this.event) return;
    this.submittingForReview = true;
    this.eventService.submitEvent(this.event.id).subscribe({
      next: () => {
        this.submittingForReview = false;
        this.toastService.success('Submitted for review — an admin will approve it.');
        this.loadEvent(true);
      },
      error: err => {
        this.submittingForReview = false;
        this.toastService.error(err.error?.error || 'Could not submit for review.');
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

  /** Only releases a PENDING (unpaid) seat hold — confirmed tickets can't be
   *  cancelled by the client (backend enforces this too). */
  async cancelRegistration(): Promise<void> {
    if (!this.event) return;
    const confirmed = await this.modalService.open({
      title: 'Release Seat',
      message: `Release your held seat for "${this.event.title}"? You can register again later.`,
      confirmText: 'Yes, release',
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
        this.toastService.success('Seat released.');
        this.loadEvent(true);
      },
      error: (err) => {
        this.cancelling = false;
        this.toastService.error(err.error?.error || 'Failed to release the seat.');
      },
    });
  }

  onRefundSubmitted(): void {
    this.showRefundModal = false;
    this.loadEvent(true);
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
