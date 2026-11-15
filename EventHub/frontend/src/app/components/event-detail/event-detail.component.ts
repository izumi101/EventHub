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
import { FavoritesStore } from '../../services/favorites.store';
import { CheckoutSessionResponse, Event, Registration, ZonePrice } from '../../models/models';
import { PaymentQrComponent } from '../payment-qr/payment-qr.component';
import { EventCheckoutModalComponent } from './event-checkout-modal.component';
import { RefundRequestModalComponent } from './refund-request-modal.component';
import { EventMediaComponent } from './event-media.component';
import { EventFactsComponent } from './event-facts.component';
import { EventTabsComponent } from './event-tabs.component';
import { OrganizerCardComponent } from './organizer-card.component';
import {
  LucideAngularModule,
  Armchair,
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
  Ticket,
} from 'lucide-angular';
import { MoneyPipe } from '../../pipes/money.pipe';
import { apiErrorBody, apiErrorMessage } from '../../api/api-error';
import { supportsWebShare } from '../../utils/browser-support';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

/** The cheapest zone of a seat map, or null without zones (the price a seated event starts "from"). */
export function cheapestZonePrice(zones: readonly ZonePrice[] | null | undefined): string | null {
  if (!zones?.length) return null;
  return zones.reduce((min, z) => (Number(z.price) < Number(min.price) ? z : min)).price;
}

/** The one action the mobile purchase bar repeats from the panel. */
export type PrimaryAction = 'login' | 'ticket' | 'pay' | 'claim' | 'waitlist' | 'buy' | null;

/** Event page (Concept A): photo, facts and tabs, and the sticky "Tickets" panel.
 *
 *  Presentational pieces live in EventMedia/Facts/Tabs/OrganizerCard. The
 *  purchase panel stays in this template on purpose: it is the 11-state chain
 *  bound straight to this component's registration / payment / queue /
 *  waitlist / refund flow, which is unchanged. Checkout selections live in
 *  EventCheckoutModalComponent, refunds in RefundRequestModalComponent; both
 *  and the QR dialog load lazily. */
@Component({
  selector: 'app-event-detail',
  standalone: true,
  imports: [
    MoneyPipe,
    CommonModule,
    RouterModule,
    LucideAngularModule,
    EventCheckoutModalComponent,
    RefundRequestModalComponent,
    PaymentQrComponent,
    EventMediaComponent,
    EventFactsComponent,
    EventTabsComponent,
    OrganizerCardComponent,
    TranslocoPipe,
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
      <!-- Price as one line, shared by the panel and the mobile bar. -->
      <ng-template #priceTpl>
        @if (event.is_free || isZeroPrice(event.price_from)) {
          {{ 'common.free' | transloco }}
        } @else if (event.has_ticket_types) {
          {{
            'event.priceFrom'
              | transloco: { price: (event.price_from | money: event.currency : 'short') }
          }}
        } @else if (seatPriceFrom) {
          {{
            'event.priceFrom'
              | transloco: { price: (seatPriceFrom | money: event.currency : 'short') }
          }}
        } @else if (pricingData && pricingData.multiplier !== 1.0) {
          {{ pricingData.current_price | money: event.currency : 'short' }}
        } @else {
          {{ event.price | money: event.currency : 'short' }}
        }
      </ng-template>

      <div class="event-page">
        <!-- ── Pending banner ── -->
        @if (event.status === 'pending') {
          <div class="event-banner event-banner-warning">
            <div class="container py-3 flex items-center gap-3 flex-wrap">
              <lucide-icon [img]="icons.Clock" class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
              <p class="text-sm font-medium">{{ 'eventDetail.thisEventIsPending' | transloco }}</p>
              @if (isAdmin) {
                <div class="ml-auto flex gap-2">
                  <button (click)="approve()" class="btn btn-sm btn-approve">
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
          <div class="event-banner">
            <div class="container py-3 flex items-center gap-3 flex-wrap">
              <lucide-icon
                [img]="icons.SquarePen"
                class="w-4 h-4 flex-shrink-0"
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
          <div class="event-banner event-banner-danger">
            <div class="container py-3 flex items-center gap-3">
              <lucide-icon [img]="icons.CircleX" class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
              <p class="text-sm font-medium">{{ 'eventDetail.thisEventHasBeen' | transloco }}</p>
            </div>
          </div>
        }

        <div class="container event-page-body">
          <!-- Breadcrumb: Discover / category -->
          <nav class="event-crumbs" [attr.aria-label]="'attendees.breadcrumb' | transloco">
            <a routerLink="/" class="event-crumb-link focus-ring">
              <lucide-icon [img]="icons.ChevronLeft" class="w-4 h-4" aria-hidden="true" />
              {{ 'nav.discover' | transloco }}
            </a>
            @if (event.category.name) {
              <span aria-hidden="true">/</span>
              <a
                routerLink="/"
                [queryParams]="{ category: event.category.id }"
                fragment="all-events"
                class="event-crumb-link focus-ring"
                >{{ event.category.name }}</a
              >
            }
          </nav>

          <div class="event-layout">
            <app-event-media class="event-layout-media" [event]="event" />

            <div class="event-layout-main">
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

              <p class="event-kicker">
                {{ event.category.name || ('nav.event' | transloco) }}
                @if (event.is_online) {
                  · {{ 'home.online' | transloco }}
                }
              </p>
              <h1 class="event-title">{{ event.title }}</h1>
              @if (event.status !== 'published') {
                <span class="badge badge-{{ event.status }} mt-3">{{
                  event.status | titlecase
                }}</span>
              }

              <app-event-facts [event]="event" [zones]="seatZones" />
              <app-event-tabs [event]="event" [myRegistration]="myRegistration" />
              <app-organizer-card [organizer]="event.organizer" />
            </div>

            <!-- ── Tickets panel ── -->
            <aside
              class="event-layout-panel"
              id="purchase-panel"
              aria-labelledby="purchase-panel-title"
            >
              <div class="purchase-panel">
                <h2 id="purchase-panel-title" class="purchase-title">
                  {{ 'eventDetail.ticketsTitle' | transloco }}
                </h2>
                <p class="purchase-subtitle">
                  @if (seatZones.length) {
                    {{ 'eventDetail.priceByZone' | transloco }}
                  } @else if (event.has_ticket_types) {
                    {{
                      'eventDetail.ticketTypeslengthTicketTypes'
                        | transloco: { ticket_typesLength: event.ticket_types.length }
                    }}
                  } @else if (!event.is_free) {
                    {{ 'eventDetail.perTicket' | transloco }}
                    @if (pricingData && pricingData.base_price !== pricingData.current_price) {
                      ·
                      {{
                        'eventDetail.basePriceBasepriceDemand'
                          | transloco
                            : {
                                basePrice: (pricingData.base_price | money: event.currency),
                                multiplier: pricingData.multiplier,
                              }
                      }}
                    }
                  }
                </p>

                <!-- Price (general admission and summaries) -->
                <div class="purchase-price-row">
                  <span class="purchase-price num"
                    ><ng-container [ngTemplateOutlet]="priceTpl"
                  /></span>
                  @if (!event.has_ticket_types && !seatPriceFrom && pricingData && !event.is_free) {
                    <span
                      class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                      [class]="demandBadgeClass(pricingData.demand_level)"
                      >{{
                        'eventDetail.demandlevelDemand'
                          | transloco: { demandLevel: pricingData.demand_level }
                      }}</span
                    >
                  }
                </div>

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
                        [style.background]="
                          spotsPercent > 80
                            ? 'var(--destructive)'
                            : spotsPercent > 50
                              ? 'var(--warning)'
                              : 'var(--success)'
                        "
                      ></div>
                    </div>
                  </div>
                }

                <!-- CTA area: the same state chain, in the same order, as before. -->
                @if (event.status === 'cancelled' || event.status === 'completed') {
                  <div class="purchase-note">
                    {{
                      (event.status === 'cancelled'
                        ? 'eventDetail.thisEventWasCancelled'
                        : 'eventDetail.thisEventHasEnded'
                      ) | transloco
                    }}
                  </div>
                } @else if (!authService.isLoggedIn) {
                  <a
                    routerLink="/login"
                    [queryParams]="{ returnUrl: router.url }"
                    class="btn btn-primary btn-full btn-lg"
                  >
                    {{ 'eventDetail.signInToRegister' | transloco }}
                  </a>
                } @else if (isOwner) {
                  <div class="purchase-note">{{ 'eventDetail.youReTheOrganizer' | transloco }}</div>
                } @else if (registrationStatus === 'confirmed') {
                  <!-- Already registered -->
                  <div class="purchase-state purchase-state-success">
                    <lucide-icon
                      [img]="icons.CircleCheckBig"
                      class="w-5 h-5 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <p class="text-sm font-semibold">
                        {{ 'eventDetail.youReRegistered' | transloco }}
                      </p>
                      <p class="text-xs">{{ 'eventDetail.ticketIsInMy' | transloco }}</p>
                    </div>
                  </div>
                  <a routerLink="/my-registrations" class="btn btn-primary btn-full mb-2">
                    {{ 'eventDetail.viewMyTicket' | transloco }}
                  </a>

                  <!-- Refund logic: confirmed tickets can't be cancelled by
                       the client — paid ones can only request a refund,
                       free ones have no exit action. -->
                  @if (myRegistration?.refund_request?.status === 'pending') {
                    <div class="purchase-state purchase-state-warning text-xs">
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
                  <div class="purchase-state purchase-state-warning">
                    <lucide-icon
                      [img]="icons.Clock"
                      class="w-5 h-5 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      <p class="text-sm font-semibold">
                        {{ 'eventDetail.paymentIncomplete' | transloco }}
                      </p>
                      <p class="text-xs">{{ 'eventDetail.seatHeldCompletePayment' | transloco }}</p>
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
                  <div class="purchase-state purchase-state-danger">
                    <lucide-icon
                      [img]="icons.CircleX"
                      class="w-5 h-5 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <div>
                      @if (myRegistration?.refund_request?.status === 'rejected') {
                        <p class="text-sm font-bold">
                          {{ 'eventDetail.refundRequestDeclined' | transloco }}
                        </p>
                        <p class="text-xs">
                          {{
                            myRegistration?.refund_request?.organizer_note ||
                              ('eventDetail.theOrganizerDeclinedYour' | transloco)
                          }}
                        </p>
                      } @else {
                        <p class="text-sm font-bold">
                          {{ 'eventDetail.registrationDeclined' | transloco }}
                        </p>
                        <p class="text-xs">
                          {{ 'eventDetail.contactTheOrganizerFor' | transloco }}
                        </p>
                      }
                    </div>
                  </div>
                } @else if (!canBuy) {
                  <!-- Organizers/admins manage events, they don't buy tickets -->
                  <div class="purchase-note">
                    {{ 'eventDetail.onlyAttendeeAccountsCan' | transloco }}
                  </div>
                } @else if (waitlist?.status === 'offered') {
                  <!-- Waitlist offer — reserved spot, shown regardless of the public counter -->
                  <div class="purchase-state purchase-state-success" aria-live="polite">
                    <lucide-icon [img]="icons.CircleCheckBig" class="w-5 h-5 flex-shrink-0" />
                    <div>
                      <p class="text-sm font-bold">{{ 'eventDetail.aSpotOpenedUp' | transloco }}</p>
                      <p class="text-xs">{{ 'eventDetail.itSReservedFor' | transloco }}</p>
                    </div>
                  </div>
                  <button
                    (click)="openCheckout()"
                    class="btn btn-primary btn-full btn-lg font-bold"
                  >
                    {{ 'eventDetail.claimMySpot' | transloco }}
                  </button>
                } @else if (queueInfo && queueInfo.status === 'queued') {
                  <!-- Virtual waiting room -->
                  <div class="purchase-state purchase-state-accent" aria-live="polite">
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
                    <div class="purchase-state purchase-state-accent" aria-live="polite">
                      <lucide-icon [img]="icons.Clock" class="w-5 h-5 text-ember flex-shrink-0" />
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
                  }
                } @else {
                  <!-- Buy -->
                  @if (groupAvailable) {
                    <div
                      class="purchase-modes"
                      role="radiogroup"
                      [attr.aria-label]="'eventDetail.modeLabel' | transloco"
                    >
                      <button
                        type="button"
                        role="radio"
                        class="purchase-mode focus-ring"
                        [attr.aria-checked]="bookingMode === 'ticket'"
                        (click)="bookingMode = 'ticket'"
                      >
                        <lucide-icon [img]="icons.Ticket" class="w-4 h-4" aria-hidden="true" />
                        {{ 'eventDetail.modeTicket' | transloco }}
                      </button>
                      <button
                        type="button"
                        role="radio"
                        class="purchase-mode focus-ring"
                        [attr.aria-checked]="bookingMode === 'group'"
                        (click)="bookingMode = 'group'"
                      >
                        <lucide-icon [img]="icons.Users" class="w-4 h-4" aria-hidden="true" />
                        {{ 'eventDetail.modeGroup' | transloco }}
                      </button>
                    </div>
                  }

                  @if (groupAvailable && bookingMode === 'group') {
                    <p class="text-sm text-secondary-text mb-4">
                      {{ 'eventDetail.groupHint' | transloco }}
                    </p>
                    <a
                      [routerLink]="['/events', event.id, 'group']"
                      class="btn btn-primary btn-full btn-lg flex items-center justify-center gap-2"
                    >
                      <lucide-icon [img]="icons.Users" class="w-4 h-4" aria-hidden="true" />
                      {{ 'eventDetail.bookSeatsForA' | transloco }}
                    </a>
                  } @else {
                    <!-- Ticket tiers (read-only rows; a row opens checkout on it) -->
                    @if (event.has_ticket_types) {
                      <ul class="purchase-rows">
                        @for (tt of event.ticket_types; track tt.id) {
                          <li>
                            <button
                              type="button"
                              class="purchase-row focus-ring"
                              [disabled]="tt.sale_state !== 'on_sale'"
                              (click)="openCheckout(tt.id)"
                            >
                              <span class="min-w-0">
                                <span class="purchase-row-name">{{ tt.name }}</span>
                                <span class="purchase-row-sub">{{ tierStateLabel(tt) }}</span>
                              </span>
                              <span class="purchase-row-price num">
                                @if (tt.kind === 'donation') {
                                  <!-- Pay what you want: show the minimum, if any -->
                                  @if (isZeroPrice(tt.price)) {
                                    {{ 'checkout.donation' | transloco }}
                                  } @else {
                                    {{
                                      'event.priceFrom'
                                        | transloco
                                          : { price: (tt.price | money: event.currency : 'short') }
                                    }}
                                  }
                                } @else if (tt.kind === 'free' || isZeroPrice(tt.price)) {
                                  {{ 'common.free' | transloco }}
                                } @else {
                                  {{ tt.price | money: event.currency : 'short' }}
                                }
                              </span>
                            </button>
                          </li>
                        }
                      </ul>
                    }

                    <!-- Seat-map zones: prices only; the seat is chosen on the map -->
                    @if (seatZones.length) {
                      <ul class="purchase-rows">
                        @for (z of seatZones; track z.zone) {
                          <li class="purchase-row purchase-row-static">
                            <span class="purchase-row-name">{{ zoneLabel(z.zone) }}</span>
                            <span class="purchase-row-price num">{{
                              z.price | money: event.currency : 'short'
                            }}</span>
                          </li>
                        }
                      </ul>
                    }

                    <button
                      (click)="openCheckout()"
                      [disabled]="registering"
                      class="btn btn-primary btn-full btn-lg font-bold"
                    >
                      @if (registering) {
                        <span class="spinner spinner-sm"></span>
                        {{ 'checkout.processing' | transloco }}
                      } @else if (event.has_ticket_types) {
                        {{ 'eventDetail.chooseTickets' | transloco }}
                      } @else if (seatPriceFrom) {
                        <lucide-icon [img]="icons.Armchair" class="w-4 h-4" aria-hidden="true" />
                        {{
                          'eventDetail.chooseSeatFrom'
                            | transloco
                              : { price: (seatPriceFrom | money: event.currency : 'short') }
                        }}
                      } @else {
                        {{
                          event.is_free
                            ? ('eventDetail.registerFree' | transloco)
                            : ('eventDetail.getTicketsPrice'
                              | transloco
                                : { price: (currentGaPrice | money: event.currency : 'short') })
                        }}
                      }
                    </button>
                  }
                }

                <!-- Favourite + share -->
                <div class="purchase-footer">
                  @if (authService.isLoggedIn) {
                    <button
                      type="button"
                      (click)="favorites.toggle(event.id)"
                      class="purchase-footer-btn focus-ring"
                      [class.purchase-footer-btn-on]="favorites.has(event.id)"
                      [attr.aria-pressed]="favorites.has(event.id)"
                    >
                      <lucide-icon
                        [img]="icons.Heart"
                        class="w-4 h-4"
                        [class.fill-current]="favorites.has(event.id)"
                        aria-hidden="true"
                      />
                      {{
                        (favorites.has(event.id) ? 'eventDetail.saved' : 'common.save') | transloco
                      }}
                    </button>
                  }
                  <button
                    type="button"
                    (click)="shareEvent()"
                    class="purchase-footer-btn focus-ring"
                  >
                    <lucide-icon [img]="icons.Share2" class="w-4 h-4" aria-hidden="true" />
                    {{ 'eventDetail.share' | transloco }}
                  </button>
                </div>
                @if (event.currency === 'KZT' && !event.is_free) {
                  <p class="purchase-pay-note">{{ 'eventDetail.paymentNoteKzt' | transloco }}</p>
                }
              </div>
            </aside>
          </div>
        </div>

        <!-- ── Mobile purchase bar (<768px): price + the panel's primary action ── -->
        <div class="purchase-bar md:hidden">
          <div class="min-w-0">
            <p class="text-[11px] text-muted-foreground">
              {{ 'eventDetail.ticketsTitle' | transloco }}
            </p>
            <p class="purchase-bar-price num"><ng-container [ngTemplateOutlet]="priceTpl" /></p>
          </div>
          @switch (primaryAction) {
            @case ('login') {
              <a
                routerLink="/login"
                [queryParams]="{ returnUrl: router.url }"
                class="btn btn-primary"
              >
                {{ 'nav.signIn' | transloco }}
              </a>
            }
            @case ('ticket') {
              <a routerLink="/my-registrations" class="btn btn-primary">
                {{ 'nav.myTickets' | transloco }}
              </a>
            }
            @case ('pay') {
              <button (click)="resumePayment()" [disabled]="registering" class="btn btn-primary">
                {{ 'eventDetail.completePayment' | transloco }}
              </button>
            }
            @case ('claim') {
              <button (click)="openCheckout()" class="btn btn-primary">
                {{ 'eventDetail.claimMySpot' | transloco }}
              </button>
            }
            @case ('waitlist') {
              <button (click)="joinWaitlist()" [disabled]="waitlisting" class="btn btn-secondary">
                {{ 'eventDetail.joinTheWaitlist' | transloco }}
              </button>
            }
            @case ('buy') {
              @if (groupAvailable && bookingMode === 'group') {
                <a [routerLink]="['/events', event.id, 'group']" class="btn btn-primary">
                  {{ 'eventDetail.modeGroup' | transloco }}
                </a>
              } @else {
                <button (click)="openCheckout()" [disabled]="registering" class="btn btn-primary">
                  {{
                    (event.is_free ? 'eventDetail.registerFree' : 'home.hero.buyTicket') | transloco
                  }}
                </button>
              }
            }
            @default {
              <a href="#purchase-panel" (click)="scrollToPanel($event)" class="btn btn-secondary">
                {{ 'home.hero.details' | transloco }}
              </a>
            }
          }
        </div>

        <!-- ── Dialogs: loaded on first use ── -->
        @if (showCheckout) {
          @defer (on immediate) {
            <app-event-checkout-modal
              [event]="event"
              [currentGaPrice]="currentGaPrice"
              [registering]="registering"
              [preselectTicketTypeId]="preselectTicketTypeId"
              (closed)="showCheckout = false"
              (confirmed)="registerForEvent($event)"
            />
          }
        }

        <!-- Pay with a phone: QR code of the provider's payment page (Freedom Pay) -->
        @if (qrCheckout) {
          @defer (on immediate) {
            <app-payment-qr [checkout]="qrCheckout" (closed)="onQrClosed()" />
          }
        }

        <!-- Refund request modal -->
        @if (showRefundModal) {
          @defer (on immediate) {
            <app-refund-request-modal
              [event]="event"
              (closed)="showRefundModal = false"
              (submitted)="onRefundSubmitted()"
            />
          }
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
  readonly router = inject(Router);
  private toastService = inject(ToastService);
  private modalService = inject(ModalService);
  private seoService = inject(SeoService);
  readonly favorites = inject(FavoritesStore);

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
  /** Every zone of the seat map with its price (read-only rows in the panel). */
  seatZones: ZonePrice[] = [];

  /** Ticket vs group booking, where group booking exists (flat-priced paid events). */
  bookingMode: 'ticket' | 'group' = 'ticket';
  /** Tier the checkout opens on, when a tier row was clicked. */
  preselectTicketTypeId: number | null = null;

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

  /** A cheapest ticket of zero (e.g. a free tier beside a donation one) reads as Free, never "0 ₸". */
  isZeroPrice(price: string | number | null | undefined): boolean {
    return price !== null && price !== undefined && Number(price) === 0;
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
    Armchair,
    Ticket,
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
                this.seatZones = sm.zone_prices;
              },
              error: () => {
                // 404: general admission, priced by demand.
                this.seatPriceFrom = null;
                this.seatZones = [];
              },
            });
          }
        }
        // Favourite state comes from FavoritesStore (shared with the Discover cards).
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

  /** Group booking is offered where it is today: flat-priced paid events. */
  get groupAvailable(): boolean {
    return !!this.event && !this.event.is_free && !this.event.has_ticket_types;
  }

  /** Open checkout, optionally on a tier the visitor picked in the panel. */
  openCheckout(ticketTypeId: number | null = null): void {
    this.preselectTicketTypeId = ticketTypeId;
    this.showCheckout = true;
  }

  /**
   * The single action the mobile bar repeats, following the panel's state
   * chain in the same order; null where the panel shows a note instead.
   */
  get primaryAction(): PrimaryAction {
    const e = this.event;
    if (!e || e.status === 'cancelled' || e.status === 'completed') return null;
    if (!this.authService.isLoggedIn) return 'login';
    if (this.isOwner) return null;
    if (this.registrationStatus === 'confirmed') return 'ticket';
    if (this.registrationStatus === 'pending') return 'pay';
    if (this.registrationStatus === 'rejected') return null;
    if (!this.canBuy) return null;
    if (this.waitlist?.status === 'offered') return 'claim';
    if (this.queueInfo?.status === 'queued') return null;
    if (e.available_spots === 0) return this.waitlist?.status === 'waiting' ? null : 'waitlist';
    return 'buy';
  }

  scrollToPanel(event: MouseEvent): void {
    event.preventDefault();
    document.getElementById('purchase-panel')?.scrollIntoView({ block: 'start' });
  }

  zoneLabel(zone: string): string {
    return this.i18n.tOr('seatSelector.zones.' + zone, zone);
  }

  /** Same wording as the checkout's tier list. */
  tierStateLabel(tt: Event['ticket_types'][number]): string {
    switch (tt.sale_state) {
      case 'sold_out':
        return this.i18n.t('event.soldOut');
      case 'scheduled':
        return this.i18n.t('checkout.salesNotStartedYet');
      case 'ended':
        return this.i18n.t('checkout.salesEnded');
      case 'inactive':
        return this.i18n.t('checkout.unavailable');
      default:
        if (tt.available !== null && tt.available <= 10)
          return this.i18n.t('checkout.onlyAvailableLeft', { available: tt.available });
        return this.i18n.t('checkout.available');
    }
  }

  demandBadgeClass(level: string): string {
    const map: Record<string, string> = {
      low: 'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]',
      medium: 'bg-[color:var(--warning-50)] text-warning',
      high: 'bg-[color:var(--warning-50)] text-[color:var(--warning-text)]',
      surge: 'bg-[color:var(--destructive-50)] text-[color:var(--destructive)] animate-pulse',
    };
    return map[level] ?? 'bg-muted text-muted-foreground';
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
