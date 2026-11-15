import {
  AfterViewInit,
  Component,
  ElementRef,
  Input,
  OnDestroy,
  ViewChild,
  NgZone,
  inject,
  signal,
} from '@angular/core';
import { Params, RouterModule } from '@angular/router';
import { Observable, Subscription } from 'rxjs';
import { LucideAngularModule, ChevronLeft, ChevronRight } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event } from '../../models/models';
import { EventCardComponent } from '../event-card/event-card.component';

export type RailState = 'idle' | 'loading' | 'ready' | 'failed';

/**
 * A titled row of cards on Discover. It loads its events only when it comes
 * near the viewport and hides itself when the list is empty or fails.
 */
@Component({
  selector: 'app-event-rail',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe, EventCardComponent],
  template: `
    @if (!hidden()) {
      <section class="rail" [attr.aria-labelledby]="headingId">
        <div class="rail-head">
          <h2 [id]="headingId" class="rail-title">{{ title }}</h2>
          <div class="flex items-center gap-2">
            @if (layout === 'row' && state() === 'ready') {
              <button
                type="button"
                class="nav-icon-btn focus-ring hidden md:inline-flex"
                [attr.aria-label]="'home.rails.scrollLeft' | transloco"
                (click)="scroll(-1)"
              >
                <lucide-icon [img]="icons.ChevronLeft" class="w-4 h-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                class="nav-icon-btn focus-ring hidden md:inline-flex"
                [attr.aria-label]="'home.rails.scrollRight' | transloco"
                (click)="scroll(1)"
              >
                <lucide-icon [img]="icons.ChevronRight" class="w-4 h-4" aria-hidden="true" />
              </button>
            }
            @if (seeAll) {
              <a
                routerLink="/"
                [queryParams]="seeAll"
                fragment="all-events"
                class="rail-see-all focus-ring"
                >{{ 'home.rails.seeAll' | transloco }}
                <lucide-icon [img]="icons.ChevronRight" class="w-4 h-4" aria-hidden="true"
              /></a>
            }
          </div>
        </div>

        @if (state() !== 'ready') {
          <div class="rail-row" aria-hidden="true">
            @for (i of skeletons; track i) {
              <div class="rail-item"><div class="card-skeleton"></div></div>
            }
          </div>
        } @else if (layout === 'mosaic') {
          <div class="rail-mosaic">
            @for (event of events().slice(0, 5); track event.id) {
              <app-event-card [event]="event" variant="fill" [class.rail-mosaic-lead]="$first" />
            }
          </div>
        } @else {
          <div #row class="rail-row">
            @for (event of events(); track event.id) {
              <div class="rail-item"><app-event-card [event]="event" /></div>
            }
          </div>
        }
      </section>
    }
  `,
  host: { '[style.display]': "hidden() ? 'none' : 'block'" },
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class EventRailComponent implements AfterViewInit, OnDestroy {
  private static nextId = 0;
  private host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private zone = inject(NgZone);

  @Input({ required: true }) title = '';
  /** Called once, when the rail first comes near the viewport. */
  @Input({ required: true }) source!: () => Observable<Event[]>;
  @Input() layout: 'row' | 'mosaic' = 'row';
  /** Discover query params for "See all" (lands on the All events grid). */
  @Input() seeAll: Params | null = null;
  /** Hide rails that come back with fewer events than this. */
  @Input() minItems = 1;

  @ViewChild('row') private row?: ElementRef<HTMLElement>;

  readonly headingId = `rail-${++EventRailComponent.nextId}`;
  readonly state = signal<RailState>('idle');
  readonly events = signal<Event[]>([]);
  readonly hidden = signal(false);
  readonly skeletons = [1, 2, 3, 4];
  readonly icons = { ChevronLeft, ChevronRight };

  private observer?: IntersectionObserver;
  private sub?: Subscription;

  ngAfterViewInit(): void {
    if (typeof IntersectionObserver === 'undefined') {
      this.load();
      return;
    }
    this.observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          this.observer?.disconnect();
          // IntersectionObserver fires outside Angular's zone.
          this.zone.run(() => this.load());
        }
      },
      { rootMargin: '400px 0px' },
    );
    this.observer.observe(this.host);
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
    this.sub?.unsubscribe();
  }

  load(): void {
    if (this.state() !== 'idle') return;
    this.state.set('loading');
    this.sub = this.source().subscribe({
      next: (events) => {
        this.events.set(events);
        this.state.set('ready');
        this.hidden.set(events.length < this.minItems);
      },
      error: () => {
        this.state.set('failed');
        this.hidden.set(true);
      },
    });
  }

  scroll(direction: 1 | -1): void {
    const el = this.row?.nativeElement;
    if (!el) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollBy({ left: direction * el.clientWidth * 0.9, behavior: reduce ? 'auto' : 'smooth' });
  }
}
