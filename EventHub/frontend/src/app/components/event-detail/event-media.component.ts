import { Component, Input, computed, signal } from '@angular/core';
import { LucideAngularModule } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event } from '../../models/models';
import { PluralPipe } from '../../i18n/locale.pipes';
import { categoryCover } from '../home/category-cover';

/** Event photo (or its category cover) with the spots-left pill. */
@Component({
  selector: 'app-event-media',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe, PluralPipe],
  template: `
    <figure class="event-media">
      @if (event.image && !failed()) {
        <img [src]="event.image" [alt]="event.title" (error)="failed.set(true)" />
      } @else {
        <div class="event-media-cover" [style.background]="cover().background" aria-hidden="true">
          <lucide-icon [img]="cover().icon" class="event-media-icon" />
        </div>
      }
      @if (event.max_participants > 0) {
        <figcaption class="event-media-pill" [class.event-media-pill-out]="soldOut()">
          @if (soldOut()) {
            {{ 'event.soldOut' | transloco }}
          } @else {
            {{ 'event.spotsLeft' | tPlural: event.available_spots }}
          }
        </figcaption>
      }
    </figure>
  `,
  styles: [
    `
      :host {
        display: block;
        min-width: 0;
      }
    `,
  ],
})
export class EventMediaComponent {
  private readonly eventSig = signal<Event | null>(null);
  private current!: Event;
  @Input({ required: true })
  set event(value: Event) {
    this.current = value;
    this.eventSig.set(value);
    this.failed.set(false);
  }
  get event(): Event {
    return this.current;
  }

  readonly failed = signal(false);
  readonly cover = computed(() => {
    const e = this.eventSig();
    return categoryCover(e?.category.icon, e?.category.id);
  });
  readonly soldOut = computed(() => this.eventSig()?.available_spots === 0);
}
