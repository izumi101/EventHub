import { Component, Input, computed, inject, signal } from '@angular/core';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, Heart } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event } from '../../models/models';
import { MoneyPipe } from '../../pipes/money.pipe';
import { LocalDatePipe, PluralPipe } from '../../i18n/locale.pipes';
import { FavoritesStore } from '../../services/favorites.store';
import { categoryCover } from '../home/category-cover';

/** At or below this many free spots a card says "N spots left" (Q7). */
export const LOW_STOCK = 20;

/**
 * Discover card (Concept A): photo or category cover, date pill, favourite
 * heart, status pills, then kicker / title / venue / price over a dark fade.
 *
 * The title is the card's link and stretches over the whole card; the heart
 * is a sibling button above it, so both stay separately focusable.
 */
@Component({
  selector: 'app-event-card',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe, MoneyPipe, LocalDatePipe, PluralPipe],
  template: `
    <article
      class="event-card group"
      [class.event-card-portrait]="variant === 'portrait'"
      [class.event-card-fill]="variant === 'fill'"
    >
      <!-- Media -->
      @if (event.image && !imageError()) {
        <img
          [src]="event.image"
          alt=""
          loading="lazy"
          (error)="imageError.set(true)"
          class="event-card-media"
        />
      } @else {
        <div class="event-card-media" [style.background]="cover().background" aria-hidden="true">
          <lucide-icon [img]="cover().icon" class="event-card-cover-icon" />
        </div>
      }
      <div class="event-card-fade" aria-hidden="true"></div>

      <!-- Top row: date + heart -->
      <div class="event-card-top">
        <span class="event-card-date">
          <span class="font-semibold">{{ event.date | localDate: 'd' }}</span>
          <span class="uppercase opacity-75">{{ event.date | localDate: 'LLL' }}</span>
        </span>
        <button
          type="button"
          class="event-card-heart focus-ring"
          [attr.aria-pressed]="favorited()"
          [attr.aria-label]="
            (favorited() ? 'event.removeFavorite' : 'event.addFavorite')
              | transloco: { title: event.title }
          "
          (click)="favorites.toggle(event.id)"
        >
          <lucide-icon
            [img]="icons.Heart"
            class="w-[18px] h-[18px]"
            [class.fill-current]="favorited()"
            aria-hidden="true"
          />
        </button>
      </div>

      <!-- Body -->
      <div class="event-card-body">
        @if (pills().length) {
          <div class="flex flex-wrap gap-1.5 mb-2">
            @for (pill of pills(); track pill) {
              @switch (pill) {
                @case ('low') {
                  <span class="card-pill card-pill-hot">{{
                    'event.spotsLeft' | tPlural: event.available_spots
                  }}</span>
                }
                @case ('soldout') {
                  <span class="card-pill card-pill-light">{{ 'event.soldOut' | transloco }}</span>
                }
                @case ('free') {
                  <span class="card-pill card-pill-free">{{ 'common.free' | transloco }}</span>
                }
                @case ('online') {
                  <span class="card-pill card-pill-light">{{ 'home.online' | transloco }}</span>
                }
              }
            }
          </div>
        }
        @if (event.category.name) {
          <p class="event-card-kicker">{{ event.category.name }}</p>
        }
        <h3 class="event-card-title">
          <a
            [routerLink]="['/events', event.id]"
            class="event-card-link"
            [attr.aria-label]="'event.viewDetailsFor' | transloco: { title: event.title }"
            >{{ event.title }}</a
          >
        </h3>
        <p class="event-card-venue" [title]="event.location">{{ event.location }}</p>
        <p class="event-card-price num" data-testid="card-price">
          @if (soldOut()) {
            {{ 'event.soldOut' | transloco }}
          } @else if (freeEntry()) {
            {{ 'common.free' | transloco }}
          } @else if (event.has_ticket_types) {
            {{
              'event.priceFrom'
                | transloco: { price: (event.price_from | money: event.currency : 'short') }
            }}
          } @else {
            {{ event.price_from | money: event.currency : 'short' }}
          }
        </p>
      </div>
    </article>
  `,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
        height: 100%;
      }
    `,
  ],
})
export class EventCardComponent {
  readonly favorites = inject(FavoritesStore);

  private readonly eventSig = signal<Event | null>(null);
  private current!: Event;
  @Input({ required: true })
  set event(value: Event) {
    this.current = value;
    this.eventSig.set(value);
    this.imageError.set(false);
  }
  get event(): Event {
    return this.current;
  }

  /** 'portrait' keeps a 3:4 ratio; 'fill' takes the height its grid cell gives it. */
  @Input() variant: 'portrait' | 'fill' = 'portrait';

  readonly imageError = signal(false);
  readonly icons = { Heart };

  readonly cover = computed(() => {
    const e = this.eventSig();
    return categoryCover(e?.category.icon, e?.category.id);
  });

  readonly favorited = computed(() => {
    const e = this.eventSig();
    return !!e && this.favorites.has(e.id);
  });

  /**
   * Free to get in: the event is free, or its cheapest ticket costs nothing
   * (a free tier next to a pay-what-you-want one). Never "0 ₸".
   */
  readonly freeEntry = computed(() => {
    const e = this.eventSig();
    return !!e && (e.is_free || Number(e.price_from) === 0);
  });

  readonly soldOut = computed(() => {
    const e = this.eventSig();
    return !!e && e.max_participants > 0 && e.available_spots === 0;
  });

  readonly pills = computed(() => {
    const e = this.eventSig();
    if (!e) return [];
    const pills: ('low' | 'soldout' | 'free' | 'online')[] = [];
    if (this.soldOut()) pills.push('soldout');
    else if (e.max_participants > 0 && e.available_spots <= LOW_STOCK) pills.push('low');
    if (this.freeEntry() && !this.soldOut()) pills.push('free');
    if (e.is_online) pills.push('online');
    return pills;
  });
}
