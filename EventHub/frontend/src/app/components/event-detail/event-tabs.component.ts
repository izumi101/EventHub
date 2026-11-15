import { Component, ElementRef, Input, ViewChildren, QueryList, signal } from '@angular/core';
import { LucideAngularModule, ExternalLink, Link } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event, Registration } from '../../models/models';
import { EventReviewsComponent } from './event-reviews.component';

type Tab = 'about' | 'location' | 'reviews';
const TABS: Tab[] = ['about', 'location', 'reviews'];

/** About / Location / Reviews. Tabs follow the ARIA tabs pattern (arrow keys, Home, End). */
@Component({
  selector: 'app-event-tabs',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe, EventReviewsComponent],
  template: `
    <div class="event-tabs" role="tablist" [attr.aria-label]="'eventDetail.tabs.label' | transloco">
      @for (tab of tabs; track tab) {
        <button
          #tabButton
          type="button"
          role="tab"
          class="event-tab focus-ring"
          [id]="'event-tab-' + tab"
          [attr.aria-selected]="active() === tab"
          [attr.aria-controls]="'event-panel-' + tab"
          [attr.tabindex]="active() === tab ? 0 : -1"
          (click)="active.set(tab)"
          (keydown)="onKey($event, $index)"
        >
          {{ 'eventDetail.tabs.' + tab | transloco }}
        </button>
      }
    </div>

    <div
      class="event-tab-panel"
      role="tabpanel"
      [id]="'event-panel-' + active()"
      [attr.aria-labelledby]="'event-tab-' + active()"
      tabindex="0"
    >
      @switch (active()) {
        @case ('about') {
          <div class="event-description">{{ event.description }}</div>
          @if (event.is_online && event.online_link) {
            <a
              [href]="event.online_link"
              target="_blank"
              rel="noopener noreferrer"
              class="event-online-link focus-ring"
            >
              <lucide-icon [img]="icons.Link" class="w-4 h-4 flex-shrink-0" aria-hidden="true" />
              <span class="truncate">{{ event.online_link }}</span>
            </a>
          }
        }
        @case ('location') {
          <p class="text-foreground font-semibold">{{ event.location }}</p>
          @if (event.address) {
            <p class="text-secondary-text mt-1">{{ event.address }}</p>
          }
          @if (!event.is_online) {
            <a
              [href]="mapsUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1.5 mt-4 text-sm font-medium text-primary hover:underline"
            >
              {{ 'eventDetail.openInMaps' | transloco }}
              <lucide-icon [img]="icons.ExternalLink" class="w-3.5 h-3.5" aria-hidden="true" />
            </a>
          }
        }
        @case ('reviews') {
          <!-- Loaded only when the tab opens. -->
          @defer (on immediate) {
            <app-event-reviews [event]="event" [myRegistration]="myRegistration" />
          } @placeholder {
            <span class="spinner"></span>
          }
        }
      }
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class EventTabsComponent {
  @Input({ required: true }) event!: Event;
  @Input() myRegistration: Registration | null = null;

  @ViewChildren('tabButton') private buttons?: QueryList<ElementRef<HTMLButtonElement>>;

  readonly tabs = TABS;
  readonly active = signal<Tab>('about');
  readonly icons = { ExternalLink, Link };

  /** A map search for the venue (no embed: the CSP allows no third-party frames). */
  get mapsUrl(): string {
    const q = [this.event.location, this.event.address].filter(Boolean).join(', ');
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
  }

  onKey(event: KeyboardEvent, i: number): void {
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = (i + 1) % TABS.length;
    else if (event.key === 'ArrowLeft') next = (i - 1 + TABS.length) % TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TABS.length - 1;
    if (next === null) return;
    event.preventDefault();
    this.active.set(TABS[next]);
    this.buttons?.get(next)?.nativeElement.focus();
  }
}
