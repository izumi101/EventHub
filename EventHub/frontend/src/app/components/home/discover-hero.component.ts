import {
  AfterViewInit,
  Component,
  ElementRef,
  Input,
  OnDestroy,
  computed,
  NgZone,
  inject,
  signal,
} from '@angular/core';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, CalendarDays, MapPin, Ticket } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event } from '../../models/models';
import { MoneyPipe } from '../../pipes/money.pipe';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LayoutService } from '../../layout/layout.service';
import { categoryCover } from './category-cover';

const SOON_MS = 7 * 24 * 60 * 60 * 1000;
export const HERO_SIZE = 3;

/**
 * Hero rule (REDESIGN_PLAN §3): the pool is recommendations then the upcoming
 * list, de-duplicated; sold-out events are skipped. Events with a photo win;
 * when none has one, the first upcoming events show with category covers.
 * An empty result means the brand hero.
 */
export function pickHeroEvents(pool: Event[], size = HERO_SIZE): Event[] {
  const seen = new Set<number>();
  const open = pool.filter((e) => {
    if (seen.has(e.id)) return false;
    seen.add(e.id);
    return e.max_participants === 0 || e.available_spots > 0;
  });
  const withImage = open.filter((e) => !!e.image);
  return (withImage.length ? withImage : open).slice(0, size);
}

@Component({
  selector: 'app-discover-hero',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe, MoneyPipe, LocalDatePipe],
  template: `
    <section class="hero" [attr.aria-label]="'home.hero.label' | transloco">
      <!-- Once this marker scrolls under the nav, the nav turns solid. -->
      <div class="hero-sentinel" aria-hidden="true"></div>
      @if (loading) {
        <div class="hero-bg hero-skeleton" aria-hidden="true"></div>
        <div class="container hero-inner">
          <div class="hero-copy">
            <div class="h-3 w-40 rounded-full bg-white/15 mb-5"></div>
            <div class="h-12 w-3/4 max-w-xl rounded-xl bg-white/15 mb-3"></div>
            <div class="h-12 w-1/2 max-w-md rounded-xl bg-white/10 mb-6"></div>
            <div class="h-11 w-56 rounded-full bg-white/10"></div>
          </div>
        </div>
      } @else if (active(); as e) {
        <div class="hero-bg" aria-hidden="true">
          @if (e.image && !failed().has(e.id)) {
            <img [src]="e.image" alt="" class="hero-img" (error)="markFailed(e.id)" />
          } @else {
            <div class="hero-img" [style.background]="coverOf(e).background">
              <lucide-icon [img]="coverOf(e).icon" class="hero-cover-icon" />
            </div>
          }
        </div>
        <div class="hero-scrim" aria-hidden="true"></div>

        <div class="container hero-inner">
          <div class="hero-copy" aria-live="polite">
            <p class="hero-kicker">
              @if (isSoon(e)) {
                {{ 'home.hero.soon' | transloco }} ·
              }
              {{ e.category.name }}
            </p>
            <h1 class="hero-title">{{ e.title }}</h1>
            <div class="hero-meta">
              <span class="inline-flex items-center gap-2">
                <lucide-icon [img]="icons.CalendarDays" class="w-4 h-4" aria-hidden="true" />
                {{ e.date | localDate: 'EEE, d MMMM · HH:mm' }}
              </span>
              <span class="inline-flex items-center gap-2 min-w-0">
                <lucide-icon
                  [img]="icons.MapPin"
                  class="w-4 h-4 flex-shrink-0"
                  aria-hidden="true"
                />
                <span class="truncate">{{ e.location }}</span>
              </span>
            </div>
            <div class="hero-actions">
              <a [routerLink]="['/events', e.id]" class="btn btn-primary hero-btn">
                <lucide-icon [img]="icons.Ticket" class="w-4 h-4" aria-hidden="true" />
                {{ (freeEntry(e) ? 'home.hero.register' : 'home.hero.buyTicket') | transloco }}
              </a>
              <a [routerLink]="['/events', e.id]" class="hero-btn hero-btn-ghost">
                {{ 'home.hero.details' | transloco }}
              </a>
              <span class="hero-price num">
                @if (freeEntry(e)) {
                  {{ 'common.free' | transloco }}
                } @else if (e.has_ticket_types) {
                  {{
                    'event.priceFrom'
                      | transloco: { price: (e.price_from | money: e.currency : 'short') }
                  }}
                } @else {
                  {{ e.price_from | money: e.currency : 'short' }}
                }
              </span>
            </div>
          </div>

          @if (picks().length > 1) {
            <div class="hero-thumbs" role="group" [attr.aria-label]="'home.hero.more' | transloco">
              @for (ev of picks(); track ev.id) {
                <button
                  type="button"
                  class="hero-thumb focus-ring"
                  [attr.aria-pressed]="$index === index()"
                  [attr.aria-label]="'home.hero.showEvent' | transloco: { title: ev.title }"
                  (click)="select($index)"
                  (keydown)="onThumbKey($event, $index)"
                >
                  <span class="hero-thumb-media">
                    @if (ev.image && !failed().has(ev.id)) {
                      <img [src]="ev.image" alt="" (error)="markFailed(ev.id)" />
                    } @else {
                      <span class="block w-full h-full" [style.background]="coverOf(ev).background">
                      </span>
                    }
                  </span>
                  <span class="hero-thumb-caption"
                    >{{ ev.date | localDate: 'd MMM' }} · {{ ev.title }}</span
                  >
                </button>
              }
            </div>
          }
        </div>
      } @else {
        <div class="hero-bg hero-brand-bg" aria-hidden="true"></div>
        <div class="container hero-inner">
          <div class="hero-copy">
            <p class="hero-kicker">{{ 'home.kicker' | transloco }}</p>
            <h1 class="hero-title">
              {{ 'home.titleLine1' | transloco }}
              <span class="text-[color:var(--ember-600)]">{{ 'home.titleLine2' | transloco }}</span>
            </h1>
            <p class="hero-subtitle">{{ 'home.subtitle' | transloco }}</p>
          </div>
        </div>
      }
    </section>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class DiscoverHeroComponent implements AfterViewInit, OnDestroy {
  private layout = inject(LayoutService);
  private zone = inject(NgZone);
  private host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private observer?: IntersectionObserver;

  /** True until the first lists answered. */
  @Input() loading = false;

  private readonly pool = signal<Event[]>([]);
  @Input()
  set events(value: Event[]) {
    this.pool.set(value);
    this.index.set(0);
  }

  readonly picks = computed(() => pickHeroEvents(this.pool()));
  readonly index = signal(0);
  readonly active = computed<Event | null>(() => this.picks()[this.index()] ?? null);
  readonly failed = signal<ReadonlySet<number>>(new Set());

  readonly icons = { CalendarDays, MapPin, Ticket };

  ngAfterViewInit(): void {
    if (typeof IntersectionObserver === 'undefined') return;
    // The nav (64px) floats over the hero until the hero has scrolled under it.
    this.observer = new IntersectionObserver(
      // IntersectionObserver fires outside Angular's zone: re-enter it so the nav updates.
      ([entry]) => this.zone.run(() => this.layout.navOverHero.set(entry.isIntersecting)),
      { rootMargin: '-64px 0px 0px 0px', threshold: 0 },
    );
    const sentinel = this.host.querySelector('.hero-sentinel');
    if (sentinel) this.observer.observe(sentinel);
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
    this.layout.navOverHero.set(false);
  }

  select(i: number): void {
    this.index.set(i);
  }

  /** Arrow keys move between thumbnails (and show that event). */
  onThumbKey(event: KeyboardEvent, i: number): void {
    const n = this.picks().length;
    let next: number | null = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (i + 1) % n;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (i - 1 + n) % n;
    if (next === null) return;
    event.preventDefault();
    this.select(next);
    const buttons = (event.currentTarget as HTMLElement).parentElement?.querySelectorAll('button');
    buttons?.[next]?.focus();
  }

  markFailed(id: number): void {
    this.failed.set(new Set([...this.failed(), id]));
  }

  coverOf(e: Event) {
    return categoryCover(e.category.icon, e.category.id);
  }

  freeEntry(e: Event): boolean {
    return e.is_free || Number(e.price_from) === 0;
  }

  isSoon(e: Event): boolean {
    const t = new Date(e.date).getTime() - Date.now();
    return t >= 0 && t <= SOON_MS;
  }
}
