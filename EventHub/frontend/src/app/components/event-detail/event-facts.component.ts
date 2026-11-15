import { Component, Input, inject } from '@angular/core';
import { LucideAngularModule, Armchair, CalendarDays, MapPin, Ticket, Users } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event, ZonePrice } from '../../models/models';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

/** "GMT+5" for the viewer's offset at that instant (events carry no time zone). */
export function gmtOffset(iso: string): string {
  const minutes = -new Date(iso).getTimezoneOffset();
  const sign = minutes >= 0 ? '+' : '−';
  const abs = Math.abs(minutes);
  const mm = abs % 60;
  return `GMT${sign}${Math.floor(abs / 60)}${mm ? ':' + String(mm).padStart(2, '0') : ''}`;
}

/** Key facts under the title: when, where, and how seats/tickets work. */
@Component({
  selector: 'app-event-facts',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe, LocalDatePipe],
  template: `
    <ul class="event-facts">
      <li class="event-fact">
        <span class="event-fact-icon" aria-hidden="true">
          <lucide-icon [img]="icons.CalendarDays" class="w-[18px] h-[18px]" />
        </span>
        <div class="min-w-0">
          <p class="event-fact-title first-letter:uppercase">
            {{ event.date | localDate: 'EEEE, d MMMM y' }}
          </p>
          <p class="event-fact-sub">
            {{ event.date | localDate: 'HH:mm' }}
            @if (event.end_date) {
              – {{ event.end_date | localDate: 'HH:mm' }}
            }
            · {{ 'eventDetail.timeZoneNote' | transloco: { offset: offset } }}
          </p>
        </div>
      </li>

      <li class="event-fact">
        <span class="event-fact-icon" aria-hidden="true">
          <lucide-icon [img]="icons.MapPin" class="w-[18px] h-[18px]" />
        </span>
        <div class="min-w-0">
          <p class="event-fact-title">{{ event.location }}</p>
          @if (event.address) {
            <p class="event-fact-sub">{{ event.address }}</p>
          }
        </div>
      </li>

      <li class="event-fact">
        <span class="event-fact-icon" aria-hidden="true">
          <lucide-icon
            [img]="
              zones.length ? icons.Armchair : event.has_ticket_types ? icons.Ticket : icons.Users
            "
            class="w-[18px] h-[18px]"
          />
        </span>
        <div class="min-w-0">
          @if (zones.length) {
            <p class="event-fact-title">{{ 'eventDetail.seating' | transloco }}</p>
            <p class="event-fact-sub">{{ zoneNames() }} · {{ refundKey | transloco }}</p>
          } @else if (event.has_ticket_types) {
            <p class="event-fact-title">
              {{
                'eventDetail.ticketTypeslengthTicketTypes'
                  | transloco: { ticket_typesLength: event.ticket_types.length }
              }}
            </p>
            <p class="event-fact-sub">{{ refundKey | transloco }}</p>
          } @else {
            <p class="event-fact-title">
              @if (event.max_participants > 0) {
                {{
                  'eventDetail.availablespotsSpotsLeft'
                    | transloco: { availableSpots: event.available_spots }
                }}
              } @else {
                {{ 'dashboard.capacity' | transloco }}
              }
            </p>
            <p class="event-fact-sub">{{ refundKey | transloco }}</p>
          }
        </div>
      </li>
    </ul>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class EventFactsComponent {
  private i18n = inject(LanguageService);

  @Input({ required: true }) event!: Event;
  /** Seat-map zones with prices; empty for general admission. */
  @Input() zones: readonly ZonePrice[] = [];

  readonly icons = { Armchair, CalendarDays, MapPin, Ticket, Users };

  get offset(): string {
    return gmtOffset(this.event.date);
  }

  get refundKey(): string {
    return this.event.refundable ? 'eventDetail.refundable' : 'eventDetail.nonRefundable';
  }

  zoneNames(): string {
    return this.zones.map((z) => this.i18n.tOr('seatSelector.zones.' + z.zone, z.zone)).join(', ');
  }
}
