import { Component, HostListener, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import {
  EventService,
  WaitlistStatus,
  QueueStatus,
  type DynamicPrice,
  type RegisterPayload,
} from '../../services/event.service';
import { PaymentService } from '../../services/payment.service';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { SeoService } from '../../services/seo.service';
import { CheckoutSessionResponse, Event, Registration, ZonePrice } from '../../models/models';
import { PaymentQrComponent } from '../payment-qr/payment-qr.component';
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
  SquarePen,
  CircleCheckBig,
  Clock,
  CircleX,
  Share2,
  ChevronLeft,
  Heart,
} from 'lucide-angular';
import { MoneyPipe } from '../../pipes/money.pipe';
import { apiErrorBody, apiErrorMessage } from '../../api/api-error';
import { supportsWebShare } from '../../utils/browser-support';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

/** The cheapest zone of a seat map, or null without zones (the price a seated event starts "from"). */
export function cheapestZonePrice(zones: readonly ZonePrice[] | null | undefined): string | null {
  if (!zones?.length) return null;
  return zones.reduce((min, z) => (Number(z.price) < Number(min.price) ? z : min)).price;
}

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
    MoneyPipe,
    CommonModule,
    RouterModule,
    LucideAngularModule,
    EventReviewsComponent,
    EventCheckoutModalComponent,
    RefundRequestModalComponent,
    PaymentQrComponent,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <!-- Loading -->
    @if (loading) {
      <div class="page-root-white flex items-center justify-center">
        <div class="flex flex-col items-center gap-3 text-muted-foreground">
          <span class="spinner spinner-lg"></span>
          <p class="text-sm">{{ 'eventDetail.loadingEvent' | transloco }}</p>
        </div>
      </div>
    }

    @if (!loading && !event) {
      <div class="page-root-white flex items-center justify-center">
        <div class="text-center">
          <p class="text-foreground font-semibold mb-2">
            {{ 'eventDetail.eventNotFound' | transloco }}
          </p>
          <a routerLink="/" class="btn btn-secondary btn-sm">{{
            'eventDetail.backToEvents' | transloco
          }}</a>
        </div>
      </div>
    }

    @if (!loading && event) {
      <div class="page-root-white pb-16">
        <!-- ── Pending banner ── -->
        @if (event.status === 'pending') {
          <div class="bg-[color:var(--warning-50)] border-b border-transparent">
            <div class="container py-3 flex items-center gap-3">
              <lucide-icon
                [img]="icons.Clock"
                class="w-4 h-4 text-warning flex-shrink-0"
                aria-hidden="true"
              />
              <p class="text-sm text-warning font-medium">
                {{ 'eventDetail.thisEventIsPending' | transloco }}
              </p>
              @if (isAdmin) {
                <div class="ml-auto flex gap-2">
                  <button
                    (click)="approve()"
                    class="btn btn-sm"
                    style="background:#15803d;color:#fff;border-color:#15803d"
                  >
                    {{ 'common.approve' | transloco }}
                  </button>
                  <button
                    (click)="reject()"
                    class="btn btn-sm btn-danger border border-transparent"
                  >
                    {{ 'common.reject' | transloco }}
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
              <lucide-icon
                [img]="icons.SquarePen"
                class="w-4 h-4 text-muted-foreground flex-shrink-0"
                aria-hidden="true"
              />
              <p class="text-sm text-foreground font-medium">
                {{ 'eventDetail.thisIsADraft' | transloco }}
              </p>
              <button
                (click)="submitForReview()"
                [disabled]="submittingForReview"
                class="btn btn-sm btn-primary ml-auto"
              >
                {{
                  (submittingForReview ? 'eventDetail.submitting' : 'eventDetail.submitForReview')
                    | transloco
                }}
              </button>
            </div>
          </div>
        }

        <!-- ── Cancelled banner ── -->
        @if (event.status === 'cancelled') {
          <div class="bg-[color:var(--destructive-50)] border-b border-transparent">
            <div class="container py-3 flex items-center gap-3">
              <lucide-icon
                [img]="icons.CircleX"
                class="w-4 h-4 text-[color:var(--destructive)] flex-shrink-0"
                aria-hidden="true"
              />
              <p class="text-sm text-[color:var(--destructive)] font-medium">
                {{ 'eventDetail.thisEventHasBeen' | transloco }}
              </p>
            </div>
          </div>
        }

        <!-- ── Editorial hero ── -->
        <div class="container mt-6">
          <!-- Breadcrumb -->
          <nav
            class="flex items-center gap-1.5 text-sm text-muted-foreground mb-4"
            [attr.aria-label]="'attendees.breadcrumb' | transloco"
          >
            <a
              routerLink="/"
              class="hover:text-foreground transition-colors flex items-center gap-1"
            >
              <lucide-icon [img]="icons.ChevronLeft" class="w-3.5 h-3.5" aria-hidden="true" />
              {{ 'dashboard.events' | transloco }}
            </a>
            <span>/</span>
            <span class="text-foreground font-medium truncate max-w-xs">{{ event.title }}</span>
          </nav>

          <div
            class="relative rounded-2xl overflow-hidden bg-muted border border-border"
            style="aspect-ratio:16/7;max-height:460px"
          >
            @if (event.image && !imageError) {
              <img
                [src]="event.image"
                [alt]="event.title"
                class="w-full h-full object-cover"
                (error)="imageError = true"
              />
            } @else {
              <div
                class="w-full h-full flex items-center justify-center"
                style="background:linear-gradient(135deg,#F4D9CC,#E8B8A2 55%,#CBB6A6)"
              >
                <span class="font-display text-7xl font-semibold text-white/70 select-none">
                  {{ event.title.charAt(0).toUpperCase() || 'E' }}
                </span>
              </div>
            }
            <!-- scrim -->
            <div
              class="absolute inset-0 pointer-events-none"
              style="background:linear-gradient(to top, rgba(26,23,20,0.84), rgba(26,23,20,0.18) 48%, transparent 72%)"
            ></div>
            <!-- overlay -->
            <div class="absolute bottom-0 left-0 right-0 p-5 sm:p-8">
              <p class="kicker mb-2" style="color:rgba(255,255,255,0.82)">
                {{ event.category.name || ('nav.event' | transloco) }} ·
                {{ event.date | localDate: 'EEE, MMM d' }}
              </p>
              <h1
                class="font-display font-semibold text-white leading-[1.04] max-w-3xl"
                style="font-size:clamp(1.9rem,3.8vw,3rem)"
              >
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
                  <a
                    [routerLink]="['/edit-event', event.id]"
                    class="btn btn-sm btn-outline flex items-center gap-1.5"
                  >
                    <lucide-icon [img]="icons.SquarePen" class="w-3.5 h-3.5" aria-hidden="true" />
                    {{ 'common.edit' | transloco }}
                  </a>
                  <a
                    [routerLink]="['/organizer/events', event.id, 'ticket-types']"
                    class="btn btn-sm btn-outline flex items-center gap-1.5"
                  >
                    <lucide-icon [img]="icons.Tag" class="w-3.5 h-3.5" aria-hidden="true" />
                    {{ 'nav.tickets' | transloco }}
                  </a>
                  <a
                    [routerLink]="['/organizer/events', event.id, 'attendees']"
                    class="btn btn-sm btn-secondary"
                  >
                    {{ 'nav.attendees' | transloco }}
                  </a>
                </div>
              }

              <!-- Meta chips -->
              <div class="flex flex-wrap gap-2 mb-6">
                <span class="badge badge-{{ event.status }}">
                  {{ event.status | titlecase }}
                </span>
                @if (event.is_free) {
                  <span class="badge badge-free">{{ 'common.free' | transloco }}</span>
                }
                @if (event.is_online) {
                  <span class="badge badge-online">{{ 'home.online' | transloco }}</span>
                }
              </div>

              <!-- Key info grid -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon
                    [img]="icons.Calendar"
                    class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0"
                    aria-hidden="true"
                  />
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">
                      {{ 'eventDetail.dateTime' | transloco }}
                    </p>
                    <p class="text-sm font-semibold text-foreground">
                      {{ event.date | localDate: 'EEEE, MMM d, y' }}
                    </p>
                    <p class="text-xs text-muted-foreground">
                      {{ event.date | localDate: 'h:mm a' }}
                      @if (event.end_date) {
                        – {{ event.end_date | localDate: 'h:mm a' }}
                      }
                    </p>
                  </div>
                </div>

                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon
                    [img]="icons.MapPin"
                    class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0"
                    aria-hidden="true"
                  />
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">
                      {{ 'home.location' | transloco }}
                    </p>
                    <p class="text-sm font-semibold text-foreground">{{ event.location }}</p>
                    @if (event.address) {
                      <p class="text-xs text-muted-foreground">{{ event.address }}</p>
                    }
                  </div>
                </div>

                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon
                    [img]="icons.Users"
                    class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0"
                    aria-hidden="true"
                  />
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">
                      {{ 'dashboard.capacity' | transloco }}
                    </p>
                    <p class="text-sm font-semibold text-foreground">
                      {{
                        'eventDetail.availablespotsSpotsLeft'
                          | transloco: { availableSpots: event.available_spots }
                      }}
                    </p>
                    <p class="text-xs text-muted-foreground">
                      {{
                        'eventDetail.registeredcountMaxparticipantsRegistered'
                          | transloco
                            : {
                                registeredCount: event.registered_count,
                                maxParticipants: event.max_participants,
                              }
                      }}
                    </p>
                  </div>
                </div>

                <div class="flex items-start gap-3 p-3 rounded-lg border border-border bg-muted/40">
                  <lucide-icon
                    [img]="icons.Tag"
                    class="w-4 h-4 text-muted-foreground mt-0.5 flex-shrink-0"
                    aria-hidden="true"
                  />
                  <div>
                    <p class="text-xs text-muted-foreground font-medium mb-0.5">
                      {{ 'common.category' | transloco }}
                    </p>
                    <p class="text-sm font-semibold text-foreground">
                      {{ event.category.name || '—' }}
                    </p>
                  </div>
                </div>
              </div>

              <!-- Online link -->
              @if (event.is_online && event.online_link) {
                <div
                  class="flex items-center gap-2 p-3 rounded-lg border border-border bg-muted/40 mb-6"
                >
                  <lucide-icon
                    [img]="icons.Link"
                    class="w-4 h-4 text-primary flex-shrink-0"
                    aria-hidden="true"
                  />
                  <a
                    [href]="event.online_link"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-sm text-primary font-medium hover:underline truncate"
                    >{{ event.online_link }}</a
                  >
                </div>
              }

              <!-- Organizer -->
              <div class="mb-8">
                <h2
                  class="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3"
                >
                  {{ 'footer.organizer' | transloco }}
                </h2>
                <div class="flex items-center gap-3">
                  <div
                    class="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary flex-shrink-0"
                  >
                    {{ event.organizer.username.charAt(0).toUpperCase() || 'O' }}
                  </div>
                  <div>
                    <p class="text-sm font-semibold text-foreground">
                      {{ event.organizer.first_name || event.organizer.username }}
                      {{ event.organizer.last_name }}
                    </p>
                    <p class="text-xs text-muted-foreground">@{{ event.organizer.username }}</p>
                  </div>
                </div>
              </div>

              <!-- Description -->
              <div class="mb-8">
                <h2
                  class="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3"
                >
                  {{ 'eventDetail.aboutThisEvent' | transloco }}
                </h2>
                <div class="prose-sm text-foreground leading-relaxed whitespace-pre-wrap text-sm">
                  {{ event.description }}
                </div>
              </div>

              <!-- Reviews -->
              <app-event-reviews [event]="event" [myRegistration]="myRegistration" />
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
                      <p
                        class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2"
                      >
                        {{
                          (event.has_ticket_types ? 'eventDetail.ticketsFrom' : 'common.price')
                            | transloco
                        }}
                      </p>
                      <div class="flex items-center gap-3 flex-wrap">
                        <span
                          class="text-3xl font-extrabold text-foreground tracking-tight leading-none"
                        >
                          @if (event.is_free) {
                            {{ 'common.free' | transloco }}
                          } @else if (event.has_ticket_types) {
                            {{ event.price_from | money: event.currency }}
                          } @else if (seatPriceFrom) {
                            <span class="text-base font-semibold text-muted-foreground">{{
                              'eventDetail.from' | transloco
                            }}</span>
                            {{ seatPriceFrom | money: event.currency }}
                          } @else if (pricingData && pricingData.multiplier !== 1.0) {
                            {{ pricingData.current_price | money: event.currency }}
                          } @else {
                            {{ event.price | money: event.currency }}
                          }
                        </span>
                        @if (
                          !event.has_ticket_types && !seatPriceFrom && pricingData && !event.is_free
                        ) {
                          <span
                            class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border"
                            [class]="demandBadgeClass(pricingData.demand_level)"
                            >{{
                              'eventDetail.demandlevelDemand'
                                | transloco: { demandLevel: pricingData.demand_level }
                            }}</span
                          >
                        }
                      </div>
                      @if (event.has_ticket_types) {
                        <p class="text-xs text-muted-foreground mt-1">
                          {{
                            'eventDetail.ticketTypeslengthTicketTypes'
                              | transloco: { ticket_typesLength: event.ticket_types.length }
                          }}
                        </p>
                      } @else if (seatPriceFrom) {
                        <p class="text-xs text-muted-foreground mt-1">
                          {{ 'eventDetail.perSeatThePrice' | transloco }}
                        </p>
                      } @else if (!event.is_free) {
                        <p class="text-xs text-muted-foreground mt-1">
                          {{ 'eventDetail.perTicket' | transloco }}
                          @if (
                            pricingData && pricingData.base_price !== pricingData.current_price
                          ) {
                            {{
                              'eventDetail.basePriceBasepriceDemand'
                                | transloco
                                  : {
                                      basePrice: (pricingData.base_price | money: event.currency),
                                      multiplier: pricingData.multiplier,
                                    }
                            }}
                          }
                        </p>
                      }
                    </div>

                    <!-- Divider -->
                    <div class="border-t border-border my-4"></div>

                    <!-- Spots bar -->
                    @if (event.max_participants > 0) {
                      <div class="mb-5">
                        <div class="flex justify-between text-xs mb-1.5">
                          <span class="font-semibold text-foreground">{{
                            'eventDetail.availablespotsSpotsLeft'
                              | transloco: { availableSpots: event.available_spots }
                          }}</span>
                          <span class="text-muted-foreground"
                            >{{ event.registered_count }} / {{ event.max_participants }}</span
                          >
                        </div>
                        <div class="h-1.5 bg-muted rounded-full overflow-hidden">
                          <div
                            class="h-full rounded-full transition-all duration-700"
                            [style.width.%]="spotsPercent"
                            [class]="
                              spotsPercent > 80
                                ? 'bg-red-400'
                                : spotsPercent > 50
                                  ? 'bg-amber-400'
                                  : 'bg-[color:var(--pine-50)]0'
                            "
                          ></div>
                        </div>
                      </div>
                    }

                    <!-- CTA area -->
                    @if (event.status === 'cancelled' || event.status === 'completed') {
                      <div class="text-center py-3 px-3 rounded-xl bg-muted">
                        <p class="text-sm text-muted-foreground">
                          {{
                            (event.status === 'cancelled'
                              ? 'eventDetail.thisEventWasCancelled'
                              : 'eventDetail.thisEventHasEnded'
                            ) | transloco
                          }}
                        </p>
                      </div>
                    } @else if (!authService.isLoggedIn) {
                      <a routerLink="/login" class="btn btn-primary btn-full btn-lg">
                        {{ 'eventDetail.signInToRegister' | transloco }}
                      </a>
                    } @else if (isOwner) {
                      <div class="text-center py-3 px-3 rounded-xl bg-muted">
                        <p class="text-sm text-muted-foreground">
                          {{ 'eventDetail.youReTheOrganizer' | transloco }}
                        </p>
                      </div>
                    } @else if (registrationStatus === 'confirmed') {
                      <!-- Already registered -->
                      <div
                        class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--pine-50)] mb-4"
                      >
                        <lucide-icon
                          [img]="icons.CircleCheckBig"
                          class="w-5 h-5 text-[color:var(--pine-600)] flex-shrink-0"
                          aria-hidden="true"
                        />
                        <div>
                          <p class="text-sm font-semibold text-[color:var(--pine-600)]">
                            {{ 'eventDetail.youReRegistered' | transloco }}
                          </p>
                          <p class="text-xs text-[color:var(--pine-600)]">
                            {{ 'eventDetail.ticketIsInMy' | transloco }}
                          </p>
                        </div>
                      </div>
                      <a routerLink="/my-registrations" class="btn btn-primary btn-full mb-2">
                        {{ 'eventDetail.viewMyTicket' | transloco }}
                      </a>

                      <!-- Refund logic: confirmed tickets can't be cancelled by
                           the client — paid ones can only request a refund,
                           free ones have no exit action. -->
                      @if (myRegistration?.refund_request?.status === 'pending') {
                        <div
                          class="flex items-center gap-2 p-2.5 rounded-lg bg-[color:var(--warning-50)] border border-transparent text-warning text-xs"
                        >
                          <lucide-icon [img]="icons.Clock" class="w-4 h-4 flex-shrink-0" />
                          {{ 'eventDetail.refundRequestedAwaitingOrganizer' | transloco }}
                        </div>
                      } @else if (myRegistration?.is_checked_in) {
                        <!-- Scanned at the door → service delivered, no refund -->
                        <p class="text-xs text-muted-foreground text-center px-2">
                          {{ 'eventDetail.ticketWasUsedFor' | transloco }}
                        </p>
                      } @else if (!isPaidTicket()) {
                        <!-- Free ticket → no cancel / refund actions -->
                      } @else if (event.refundable === false) {
                        <!-- Paid, non-refundable -->
                        <p class="text-xs text-muted-foreground text-center px-2">
                          {{ 'eventDetail.ticketsForThisEvent' | transloco }}
                        </p>
                      } @else {
                        <!-- Paid, refundable → request refund -->
                        <button
                          (click)="showRefundModal = true"
                          class="btn btn-ghost btn-full btn-sm text-muted-foreground hover:text-destructive"
                        >
                          {{ 'eventDetail.requestARefund' | transloco }}
                        </button>
                      }
                    } @else if (registrationStatus === 'pending') {
                      <div
                        class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--warning-50)] mb-4"
                      >
                        <lucide-icon
                          [img]="icons.Clock"
                          class="w-5 h-5 text-warning flex-shrink-0"
                          aria-hidden="true"
                        />
                        <div>
                          <p class="text-sm font-semibold text-warning">
                            {{ 'eventDetail.paymentIncomplete' | transloco }}
                          </p>
                          <p class="text-xs text-warning">
                            {{ 'eventDetail.seatHeldCompletePayment' | transloco }}
                          </p>
                        </div>
                      </div>
                      <button
                        (click)="resumePayment()"
                        [disabled]="registering"
                        class="btn btn-primary btn-full mb-2"
                      >
                        {{
                          (registering ? 'checkout.processing' : 'eventDetail.completePayment')
                            | transloco
                        }}
                      </button>
                      <button
                        (click)="cancelRegistration()"
                        [disabled]="cancelling"
                        class="btn btn-ghost btn-full btn-sm text-muted-foreground hover:text-destructive"
                      >
                        {{
                          (cancelling ? 'eventDetail.cancelling' : 'eventDetail.releaseSeat2')
                            | transloco
                        }}
                      </button>
                    } @else if (registrationStatus === 'rejected') {
                      <div
                        class="flex items-center gap-3 p-3.5 rounded-xl bg-[color:var(--destructive-50)] border border-transparent"
                      >
                        <lucide-icon
                          [img]="icons.CircleX"
                          class="w-5 h-5 text-[color:var(--destructive)] flex-shrink-0"
                          aria-hidden="true"
                        />
                        <div>
                          @if (myRegistration?.refund_request?.status === 'rejected') {
                            <p class="text-sm font-bold text-[color:var(--destructive)]">
                              {{ 'eventDetail.refundRequestDeclined' | transloco }}
                            </p>
                            <p class="text-xs text-[color:var(--destructive)]">
                              {{
                                myRegistration?.refund_request?.organizer_note ||
                                  ('eventDetail.theOrganizerDeclinedYour' | transloco)
                              }}
                            </p>
                          } @else {
                            <p class="text-sm font-bold text-[color:var(--destructive)]">
                              {{ 'eventDetail.registrationDeclined' | transloco }}
                            </p>
                            <p class="text-xs text-[color:var(--destructive)]">
                              {{ 'eventDetail.contactTheOrganizerFor' | transloco }}
                            </p>
                          }
                        </div>
                      </div>
                    } @else if (!canBuy) {
                      <!-- Organizers/admins manage events, they don't buy tickets -->
                      <div class="text-center py-3 px-3 rounded-xl bg-muted">
                        <p class="text-sm text-muted-foreground">
                          {{ 'eventDetail.onlyAttendeeAccountsCan' | transloco }}
                        </p>
                      </div>
                    } @else if (waitlist?.status === 'offered') {
                      <!-- Waitlist offer — reserved spot, shown regardless of the public counter -->
                      <div
                        class="flex items-center gap-3 p-3 rounded-xl border border-transparent bg-[color:var(--pine-50)] mb-3"
                      >
                        <lucide-icon
                          [img]="icons.CircleCheckBig"
                          class="w-5 h-5 text-[color:var(--pine-600)] flex-shrink-0"
                        />
                        <div>
                          <p class="text-sm font-bold text-[color:var(--pine-600)]">
                            {{ 'eventDetail.aSpotOpenedUp' | transloco }}
                          </p>
                          <p class="text-xs text-[color:var(--pine-600)]">
                            {{ 'eventDetail.itSReservedFor' | transloco }}
                          </p>
                        </div>
                      </div>
                      <button
                        (click)="showCheckout = true"
                        class="btn btn-primary btn-full btn-lg font-bold"
                      >
                        {{ 'eventDetail.claimMySpot' | transloco }}
                      </button>
                    } @else if (queueInfo && queueInfo.status === 'queued') {
                      <!-- Virtual waiting room -->
                      <div
                        class="flex items-center gap-3 p-3 rounded-xl border border-ember/30 bg-ember/10 mb-3"
                      >
                        <span class="spinner spinner-sm flex-shrink-0"></span>
                        <div>
                          <p class="text-sm font-bold text-foreground">
                            {{ 'eventDetail.youReInThe' | transloco }}
                          </p>
                          <p class="text-xs text-ember">
                            {{
                              'eventDetail.positionPositionOfTotal'
                                | transloco
                                  : {
                                      position: queueInfo.position,
                                      total: queueInfo.total,
                                      waitMinutes: queueInfo.wait_minutes,
                                    }
                            }}
                          </p>
                        </div>
                      </div>
                      <button
                        (click)="leaveQueue()"
                        class="btn btn-ghost btn-full btn-sm text-muted-foreground"
                      >
                        {{ 'eventDetail.leaveQueue' | transloco }}
                      </button>
                    } @else if (event.available_spots === 0) {
                      <!-- Sold out → waitlist -->
                      @if (waitlist?.status === 'waiting') {
                        <div
                          class="flex items-center gap-3 p-3 rounded-xl border border-ember/30 bg-ember/10 mb-3"
                        >
                          <lucide-icon
                            [img]="icons.Clock"
                            class="w-5 h-5 text-ember flex-shrink-0"
                          />
                          <div>
                            <p class="text-sm font-bold text-foreground">
                              {{ 'eventDetail.youReOnThe' | transloco }}
                            </p>
                            <p class="text-xs text-ember">
                              {{
                                'eventDetail.positionPositionWeLl'
                                  | transloco: { position: waitlist?.position }
                              }}
                            </p>
                          </div>
                        </div>
                        <button
                          (click)="leaveWaitlist()"
                          [disabled]="waitlisting"
                          class="btn btn-ghost btn-full btn-sm text-muted-foreground"
                        >
                          {{ 'eventDetail.leaveWaitlist' | transloco }}
                        </button>
                      } @else {
                        <button
                          disabled
                          class="btn btn-full btn-lg opacity-50 cursor-not-allowed bg-muted text-muted-foreground mb-2"
                        >
                          {{ 'event.soldOut' | transloco }}
                        </button>
                        @if (authService.isLoggedIn) {
                          <button
                            (click)="joinWaitlist()"
                            [disabled]="waitlisting"
                            class="btn btn-secondary btn-full"
                          >
                            {{
                              (waitlisting ? 'eventDetail.joining' : 'eventDetail.joinTheWaitlist')
                                | transloco
                            }}
                          </button>
                        } @else {
                          <a routerLink="/login" class="btn btn-secondary btn-full">{{
                            'eventDetail.signInToJoin' | transloco
                          }}</a>
                        }
                      }
                    } @else {
                      <button
                        (click)="showCheckout = true"
                        [disabled]="registering"
                        class="btn btn-primary btn-full btn-lg font-bold shadow-md hover:shadow-primary/30 transition-all"
                      >
                        @if (registering) {
                          <span class="spinner spinner-sm"></span>
                          {{ 'checkout.processing' | transloco }}
                        } @else if (event.has_ticket_types) {
                          {{ 'eventDetail.chooseTickets' | transloco }}
                        } @else if (seatPriceFrom) {
                          {{
                            'eventDetail.chooseSeatFrom'
                              | transloco: { price: (seatPriceFrom | money: event.currency) }
                          }}
                        } @else {
                          {{
                            event.is_free
                              ? ('eventDetail.registerFree' | transloco)
                              : ('eventDetail.getTicketsPrice'
                                | transloco: { price: (currentGaPrice | money: event.currency) })
                          }}
                        }
                      </button>
                      @if (!event.is_free && !event.has_ticket_types) {
                        <a
                          [routerLink]="['/events', event.id, 'group']"
                          class="btn btn-secondary btn-full mt-2 flex items-center justify-center gap-2 text-sm"
                        >
                          <lucide-icon [img]="icons.Users" class="w-4 h-4" aria-hidden="true" />
                          {{ 'eventDetail.bookSeatsForA' | transloco }}
                        </a>
                      }
                    }

                    <!-- Favorite + Share row -->
                    <div class="flex gap-2 mt-4 pt-4 border-t border-border">
                      @if (authService.isLoggedIn) {
                        <button
                          (click)="toggleFavorite()"
                          class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-colors border"
                          [class]="
                            favorited
                              ? 'border-transparent bg-[color:var(--destructive-50)] text-ember'
                              : 'border-border hover:bg-muted text-muted-foreground'
                          "
                        >
                          <lucide-icon [img]="icons.Heart" class="w-4 h-4" aria-hidden="true" />
                          {{ (favorited ? 'eventDetail.saved' : 'common.save') | transloco }}
                        </button>
                      }
                      <button
                        (click)="shareEvent()"
                        class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:bg-muted border border-border transition-colors"
                      >
                        <lucide-icon [img]="icons.Share2" class="w-4 h-4" aria-hidden="true" />
                        {{ 'eventDetail.share' | transloco }}
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
          />
        }

        <!-- Pay with a phone: QR code of the provider's payment page (Freedom Pay) -->
        @if (qrCheckout) {
          <app-payment-qr [checkout]="qrCheckout" (closed)="onQrClosed()" />
        }

        <!-- Refund request modal -->
        @if (showRefundModal) {
          <app-refund-request-modal
            [event]="event"
            (closed)="showRefundModal = false"
            (submitted)="onRefundSubmitted()"
          />
        }
      </div>
    }
  `,
})
export class EventDetailComponent implements OnInit, OnDestroy {
  private i18n = inject(LanguageService);
  private eventService = inject(EventService);
  private paymentService = inject(PaymentService);
  authService = inject(AuthService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toastService = inject(ToastService);
  private modalService = inject(ModalService);
  private seoService = inject(SeoService);

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
  /** Checkout answer with a QR code, shown in the QR payment dialog. */
  qrCheckout: CheckoutSessionResponse | null = null;
  pricingData: DynamicPrice | null = null;
  /** Cheapest seat zone of an event with a seat map: seats are priced by zone, not by demand. */
  seatPriceFrom: string | null = null;

  // Virtual waiting queue
  queueInfo: QueueStatus | null = null;
  private queueTimer?: ReturnType<typeof setInterval>;
  private pendingQueuePayload: RegisterPayload | null = null;

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
    return (
      !!this.authService.currentUser && this.authService.currentUser.id === this.event?.organizer.id
    );
  }

  get isAdmin(): boolean {
    return !!this.authService.currentUser?.is_superuser;
  }

  /** Business rule: only attendee accounts buy tickets. */
  get canBuy(): boolean {
    const u = this.authService.currentUser;
    return !!u && !u.is_staff && !u.is_superuser && u.profile.role !== 'organizer';
  }

  get spotsPercent(): number {
    if (!this.event?.max_participants) return 0;
    return (this.event.registered_count / this.event.max_participants) * 100;
  }

  readonly icons = {
    Calendar,
    MapPin,
    Users,
    Tag,
    Globe,
    Link,
    SquarePen,
    CircleCheckBig,
    Clock,
    CircleX,
    Share2,
    ChevronLeft,
    Heart,
    UsersGroup: Users,
  };

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
        this.eventService.trackAffiliateClick(Number(id), ref).subscribe({
          error: () => {
            // Click analytics only: never disturb the visitor over it.
          },
        });
      }
    }
    this.loadEvent();
  }

  ngOnDestroy(): void {
    this.stopQueuePolling();
  }

  /** Back from the payment page via the browser's Back button: the page
   *  comes from the back/forward cache with `registering` still true. */
  @HostListener('window:pageshow', ['$event'])
  onPageShow(event: PageTransitionEvent): void {
    if (!event.persisted) return;
    this.registering = false;
    this.qrCheckout = null;
    this.loadEvent(true);
  }

  /** Send the buyer to the payment page, or show its QR code when there is one. */
  private startCheckout(res: CheckoutSessionResponse): void {
    if (res.qr_code) {
      this.showCheckout = false;
      this.qrCheckout = res;
      return;
    }
    window.location.href = res.checkout_url;
  }

  onQrClosed(): void {
    this.qrCheckout = null;
    this.registering = false;
    this.loadEvent(true);
  }

  loadEvent(quiet = false): void {
    if (!quiet) this.loading = true;

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.loading = false;
      return;
    }

    this.eventService.getEvent(Number(id)).subscribe({
      next: (ev) => {
        this.event = ev;
        this.seoService.setEvent(ev);
        if (!quiet) this.loading = false;
        // Waitlist offers reserve a spot, so check the status even when the
        // public counter shows availability.
        this.loadWaitlistStatus();
        // Load dynamic pricing for paid events
        if (!ev.is_free) {
          this.eventService.getEventPricing(ev.id).subscribe({
            next: (p) => {
              this.pricingData = p;
            },
            error: () => {
              // No dynamic quote: the page shows the event's base price.
            },
          });
          if (!ev.has_ticket_types) {
            this.eventService.getSeatMap(ev.id).subscribe({
              next: (sm) => {
                this.seatPriceFrom = cheapestZonePrice(sm.zone_prices);
              },
              error: () => {
                // 404: general admission, priced by demand.
                this.seatPriceFrom = null;
              },
            });
          }
        }
        // Load favorite status
        if (this.authService.isLoggedIn) {
          this.eventService.getFavoriteStatus(ev.id).subscribe({
            next: (res) => {
              this.favorited = res.favorited;
            },
            error: () => {
              // The heart just stays empty.
            },
          });
        }
      },
      error: () => {
        if (!quiet) this.loading = false;
      },
    });

    if (this.authService.isLoggedIn) {
      // Server-side filter — immune to pagination (a user with many tickets
      // would otherwise "lose" their registration past page one).
      this.eventService.getMyRegistrations({ event: Number(id) }).subscribe({
        next: (res) => {
          const reg = res.results.find((r) => r.event.id === Number(id));
          if (reg) {
            this.registrationStatus = reg.status;
            this.registrationId = reg.id;
            this.myRegistration = reg;
          }
        },
        error: () => {
          // Without it the page offers registration; the backend still refuses duplicates.
        },
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
      next: (res) => {
        this.favorited = res.favorited;
        this.toastService.success(
          res.favorited
            ? this.i18n.t('eventDetail.addedToFavorites')
            : this.i18n.t('eventDetail.removedFromFavorites'),
        );
      },
      error: () => this.toastService.error(this.i18n.t('eventDetail.failedToUpdateFavorites')),
    });
  }

  demandBadgeClass(level: string): string {
    const map: Record<string, string> = {
      low: 'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]',
      medium: 'bg-[color:var(--warning-50)] text-warning',
      high: 'bg-orange-100 text-orange-700',
      surge: 'bg-[color:var(--destructive-50)] text-[color:var(--destructive)] animate-pulse',
    };
    return map[level] ?? 'bg-muted text-muted-foreground';
  }

  priceBarClass(): string {
    if (this.event?.is_free) return 'bg-gradient-to-r from-emerald-400 to-teal-500';
    const d = this.pricingData?.demand_level;
    if (d === 'surge') return 'bg-gradient-to-r from-red-500 to-orange-500';
    if (d === 'high') return 'bg-gradient-to-r from-orange-400 to-amber-400';
    return 'bg-gradient-to-r from-ember to-pine';
  }

  loadWaitlistStatus(): void {
    if (!this.event || !this.authService.isLoggedIn || this.isOwner) return;
    this.eventService.getWaitlistStatus(this.event.id).subscribe({
      next: (s) => {
        this.waitlist = s;
      },
      error: () => {
        // The waitlist block stays hidden.
      },
    });
  }

  joinWaitlist(): void {
    if (!this.event) return;
    this.waitlisting = true;
    this.eventService.joinWaitlist(this.event.id).subscribe({
      next: (s) => {
        this.waitlist = s;
        this.waitlisting = false;
        if (s.status === 'spots_available') {
          this.toastService.success(this.i18n.t('eventDetail.aSpotIsAvailable'));
          this.loadEvent(true);
        } else if (s.status === 'offered') {
          this.toastService.success(this.i18n.t('eventDetail.aSpotIsReady'));
        } else {
          this.toastService.success(
            this.i18n.t('eventDetail.youReOnThe2', { position: s.position }),
          );
        }
      },
      error: () => {
        this.waitlisting = false;
        this.toastService.error(this.i18n.t('eventDetail.couldNotJoinWaitlist'));
      },
    });
  }

  leaveWaitlist(): void {
    if (!this.event) return;
    this.waitlisting = true;
    this.eventService.leaveWaitlist(this.event.id).subscribe({
      next: () => {
        this.waitlist = { status: 'not_joined' };
        this.waitlisting = false;
        this.toastService.success(this.i18n.t('eventDetail.leftTheWaitlist'));
      },
      error: () => {
        this.waitlisting = false;
        this.toastService.error(this.i18n.t('eventDetail.couldNotLeaveWaitlist'));
      },
    });
  }

  /** Run the registration with the payload assembled by the checkout modal. */
  registerForEvent(payload: RegisterPayload): void {
    if (!this.event) return;
    if (this.affiliateRef) payload.affiliate_code = this.affiliateRef;

    this.registering = true;

    this.eventService.registerForEvent(this.event.id, payload).subscribe({
      next: (registration: Registration) => {
        this.registrationStatus = registration.status;
        this.registrationId = registration.id;

        // Status is the source of truth: pending → pay, confirmed → done.
        // This correctly handles free tiers (confirmed) and paid (pending).
        if (registration.status === 'pending') {
          this.paymentService.createCheckoutSession(registration.id).subscribe({
            next: (res) => {
              this.startCheckout(res);
            },
            error: () => {
              this.registering = false;
              this.showCheckout = false;
              this.toastService.error(this.i18n.t('eventDetail.paymentSetupFailedYour'));
              this.loadEvent(true);
            },
          });
          // Redirecting to Stripe — keep `registering` true.
        } else {
          this.registering = false;
          this.showCheckout = false;
          this.toastService.success(this.i18n.t('eventDetail.youReRegistered'));
          if (this.event)
            this.event = { ...this.event, available_spots: this.event.available_spots - 1 };
          this.loadEvent(true);
        }
      },
      error: (err) => {
        this.registering = false;
        // High-demand event → enter the virtual waiting room and retry
        // automatically once admitted.
        if (apiErrorBody(err)?.['code'] === 'QUEUE_REQUIRED') {
          this.showCheckout = false;
          this.enterQueue(payload);
          return;
        }
        this.toastService.error(
          apiErrorMessage(
            err,
            this.i18n.t('eventDetail.registrationFailedPleaseTry'),
            'detail',
            'error',
          ),
        );
      },
    });
  }

  // ── Virtual waiting queue ──

  private enterQueue(payload: RegisterPayload): void {
    if (!this.event) return;
    this.pendingQueuePayload = payload;
    this.eventService.queueJoin(this.event.id).subscribe({
      next: (s) => {
        this.queueInfo = s;
        if (s.status === 'queued') {
          this.toastService.info(
            this.i18n.t('eventDetail.highDemandYouRe', { position: s.position }),
          );
          this.startQueuePolling();
        } else {
          // not_needed / already admitted → just retry.
          this.retryAfterQueue();
        }
      },
      error: () => this.toastService.error(this.i18n.t('eventDetail.couldNotJoinThe')),
    });
  }

  private startQueuePolling(): void {
    this.stopQueuePolling();
    this.queueTimer = setInterval(() => {
      if (!this.event) return;
      this.eventService.queueStatus(this.event.id).subscribe({
        next: (s) => {
          this.queueInfo = s;
          if (s.status === 'admitted' || s.status === 'not_needed') {
            this.stopQueuePolling();
            this.queueInfo = null;
            this.toastService.success(this.i18n.t('eventDetail.youReInCompleting'));
            this.retryAfterQueue();
          }
        },
        error: () => {
          // Transient poll failure: the next tick asks again.
        },
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
            next: (res) => {
              this.startCheckout(res);
            },
            error: () => {
              this.registering = false;
              this.toastService.error(this.i18n.t('eventDetail.paymentSetupFailedYour'));
              this.loadEvent(true);
            },
          });
        } else {
          this.registering = false;
          this.toastService.success(this.i18n.t('eventDetail.youReRegistered'));
          this.loadEvent(true);
        }
      },
      error: (err) => {
        this.registering = false;
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('eventDetail.registrationFailedPleaseTry2'), 'error'),
        );
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
        this.toastService.success(this.i18n.t('eventDetail.submittedForReviewAn'));
        this.loadEvent(true);
      },
      error: (err) => {
        this.submittingForReview = false;
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('eventDetail.couldNotSubmitFor'), 'error'),
        );
      },
    });
  }

  /** Resume payment for a paid registration that is still pending (unpaid). */
  resumePayment(): void {
    if (!this.registrationId) return;
    this.registering = true;
    this.paymentService.createCheckoutSession(this.registrationId).subscribe({
      next: (res) => {
        this.startCheckout(res);
      },
      error: (err) => {
        this.registering = false;
        // Payment already went through but the registration was stuck as
        // pending — the backend now reconciles it, so refresh to show it.
        if (apiErrorBody(err)?.['error'] === 'Payment already completed') {
          this.toastService.success(this.i18n.t('eventDetail.paymentAlreadyCompletedYour'));
        } else {
          this.toastService.error(this.i18n.t('eventDetail.couldNotStartPayment'));
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
      title: this.i18n.t('eventDetail.releaseSeat'),
      message: this.i18n.t('eventDetail.releaseYourHeldSeat', { title: this.event.title }),
      confirmText: this.i18n.t('eventDetail.yesRelease'),
      cancelText: this.i18n.t('eventDetail.keepIt'),
      isDestructive: true,
    });
    if (!confirmed) return;
    this.cancelling = true;

    this.eventService.cancelRegistration(this.event.id).subscribe({
      next: () => {
        if (this.event)
          this.event = { ...this.event, available_spots: this.event.available_spots + 1 };
        this.registrationStatus = null;
        this.cancelling = false;
        this.toastService.success(this.i18n.t('eventDetail.seatReleased'));
        this.loadEvent(true);
      },
      error: (err) => {
        this.cancelling = false;
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('eventDetail.failedToReleaseThe'), 'error'),
        );
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
      title: this.i18n.t('eventDetail.approveEvent'),
      message: this.i18n.t('eventDetail.approveAndPublishTitle', { title: this.event.title }),
      confirmText: this.i18n.t('common.approve'),
      cancelText: this.i18n.t('common.cancel'),
    });
    if (!confirmed) return;
    this.eventService.approveEvent(this.event.id).subscribe({
      next: () => {
        this.toastService.success(this.i18n.t('eventDetail.eventApprovedAndPublished'));
        this.loadEvent(true);
      },
      error: () => this.toastService.error(this.i18n.t('eventDetail.failedToApproveEvent')),
    });
  }

  async reject(): Promise<void> {
    if (!this.event) return;
    const confirmed = await this.modalService.open({
      title: this.i18n.t('eventDetail.rejectEvent'),
      message: this.i18n.t('eventDetail.rejectTitleTheOrganizer', { title: this.event.title }),
      confirmText: this.i18n.t('common.reject'),
      cancelText: this.i18n.t('common.cancel'),
      isDestructive: true,
    });
    if (!confirmed) return;
    this.eventService.rejectEvent(this.event.id).subscribe({
      next: () => {
        this.toastService.success(this.i18n.t('eventDetail.eventRejected'));
        this.loadEvent(true);
      },
      error: () => this.toastService.error(this.i18n.t('eventDetail.failedToRejectEvent')),
    });
  }

  async shareEvent(): Promise<void> {
    if (!this.event) return;
    const url = window.location.href;
    if (supportsWebShare()) {
      try {
        await navigator.share({ title: this.event.title, url });
      } catch {
        // The visitor closed the share sheet: nothing to report.
      }
    } else {
      try {
        await navigator.clipboard.writeText(url);
        this.toastService.success(this.i18n.t('eventDetail.linkCopied'));
      } catch {
        this.toastService.error(this.i18n.t('eventDetail.failedToCopyLink'));
      }
    }
  }
}
