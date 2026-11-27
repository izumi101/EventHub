import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslocoPipe } from '@jsverse/transloco';
import { ChevronDown, ChevronRight, LucideAngularModule } from 'lucide-angular';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { LocalNumberPipe } from '../../i18n/locale.pipes';
import { MoneyPipe } from '../../pipes/money.pipe';
import { EventService, type EventAnalytics } from '../../services/event.service';
import { ticketTypeLabelKey } from '../../utils/ticket-type-label';

type TicketTypesStatus = 'idle' | 'loading' | 'ready' | 'error';

/**
 * The "Ticket types" disclosure of an event card: sold, remaining and revenue
 * per tier. The numbers come from the event's analytics, fetched the first
 * time the section is opened (a list of cards must not ask for all of them),
 * and kept for as long as the card lives. A failed load is retried from the
 * section itself.
 */
@Component({
  selector: 'app-dashboard-ticket-types',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe, MoneyPipe, LocalNumberPipe],
  template: `
    <div class="mb-3" data-testid="ticket-types">
      <button
        type="button"
        class="flex items-center gap-1.5 text-xs font-medium text-foreground hover:text-primary"
        [attr.aria-expanded]="open()"
        [attr.aria-controls]="panelId()"
        (click)="toggle()"
        data-testid="ticket-types-toggle"
      >
        <lucide-icon
          [img]="open() ? icons.ChevronDown : icons.ChevronRight"
          class="w-3.5 h-3.5"
          aria-hidden="true"
        />
        {{ 'dashboard.ticketTypes.toggle' | transloco }}
      </button>
      <div [id]="panelId()" [hidden]="!open()" class="mt-2" data-testid="ticket-types-panel">
        @if (open()) {
          @switch (status()) {
            @case ('error') {
              <div class="note note-error" role="alert" data-testid="ticket-types-error">
                <span class="flex-1">{{ error() }}</span>
                <button type="button" class="btn btn-sm btn-secondary" (click)="load()">
                  {{ 'common.retry' | transloco }}
                </button>
              </div>
            }
            @case ('ready') {
              @if (data(); as d) {
                @if (d.by_ticket_type.length === 0) {
                  <p class="text-xs text-muted-foreground" data-testid="ticket-types-empty">
                    {{ 'dashboard.ticketTypes.empty' | transloco }}
                  </p>
                } @else {
                  <div class="overflow-x-auto">
                    <table class="w-full text-xs" data-testid="ticket-types-table">
                      <caption class="sr-only">
                        {{
                          'dashboard.ticketTypes.caption' | transloco: { title: title() }
                        }}
                      </caption>
                      <thead class="text-muted-foreground">
                        <tr>
                          <th scope="col" class="text-left font-medium py-1 pr-3">
                            {{ 'dashboard.ticketTypes.colType' | transloco }}
                          </th>
                          <th scope="col" class="text-right font-medium py-1 px-3">
                            {{ 'dashboard.ticketTypes.colSold' | transloco }}
                          </th>
                          <th scope="col" class="text-right font-medium py-1 px-3">
                            {{ 'dashboard.ticketTypes.colLeft' | transloco }}
                          </th>
                          <th scope="col" class="text-right font-medium py-1 pl-3">
                            {{ 'dashboard.ticketTypes.colRevenue' | transloco }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        @for (row of d.by_ticket_type; track $index) {
                          <tr class="border-t border-border/60" data-testid="ticket-types-row">
                            <th
                              scope="row"
                              class="text-left font-medium text-foreground py-1.5 pr-3"
                            >
                              @if (labelKey(row); as key) {
                                {{ key | transloco }}
                              } @else {
                                {{ row.name }}
                              }
                            </th>
                            <td class="text-right num py-1.5 px-3" data-testid="ticket-types-sold">
                              {{ row.count | localNumber }}
                            </td>
                            <td class="text-right num py-1.5 px-3" data-testid="ticket-types-left">
                              @if (row.remaining === null) {
                                {{ 'dashboard.ticketTypes.unlimited' | transloco }}
                              } @else {
                                {{ row.remaining | localNumber }}
                              }
                            </td>
                            <td
                              class="text-right num font-semibold text-foreground py-1.5 pl-3 whitespace-nowrap"
                              data-testid="ticket-types-revenue"
                            >
                              {{ row.revenue | money: d.currency }}
                            </td>
                          </tr>
                        }
                      </tbody>
                    </table>
                  </div>
                }
              }
            }
            @default {
              <div
                class="space-y-2"
                role="status"
                [attr.aria-label]="'common.loading' | transloco"
                data-testid="ticket-types-loading"
              >
                @for (n of placeholders; track n) {
                  <div
                    class="h-4 rounded bg-muted animate-pulse motion-reduce:animate-none"
                    aria-hidden="true"
                  ></div>
                }
              </div>
            }
          }
        }
      </div>
    </div>
  `,
})
export class DashboardTicketTypesComponent {
  private readonly events = inject(EventService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly eventId = input.required<number>();
  /** For the table's caption. */
  readonly title = input('');

  readonly open = signal(false);
  readonly status = signal<TicketTypesStatus>('idle');
  readonly data = signal<EventAnalytics | null>(null);
  readonly error = signal('');

  readonly icons = { ChevronDown, ChevronRight };
  readonly placeholders = [1, 2];
  readonly panelId = computed(() => `dashboard-ticket-types-${this.eventId()}`);
  readonly labelKey = ticketTypeLabelKey;

  toggle(): void {
    const open = !this.open();
    this.open.set(open);
    // Fetched on the first opening; a failure is tried again on the next one.
    if (open && (this.status() === 'idle' || this.status() === 'error')) this.load();
  }

  load(): void {
    if (this.status() === 'loading') return;
    this.status.set('loading');
    this.events
      .getEventAnalytics(this.eventId())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.data.set(data);
          this.status.set('ready');
        },
        error: (err: unknown) => {
          this.error.set(
            errorMessage(err, this.language, {
              fallback: this.language.t('dashboard.ticketTypes.loadFailed'),
            }),
          );
          this.status.set('error');
        },
      });
  }
}
