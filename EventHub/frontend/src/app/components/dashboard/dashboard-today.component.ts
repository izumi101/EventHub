import { Component, DestroyRef, NgZone, OnInit, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Params, RouterModule } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';
import { Subject, catchError, map, of, switchMap } from 'rxjs';
import { Calendar, LucideAngularModule, MapPin, ScanLine, Users } from 'lucide-angular';
import { errorMessage } from '../../api/error-message';
import { LanguageService } from '../../i18n/language.service';
import { LocalDatePipe, LocalNumberPipe, PluralPipe } from '../../i18n/locale.pipes';
import {
  OrganizerDashboardService,
  type TodayBlock,
  type TodayEvent,
} from '../../services/organizer-dashboard.service';
import { countdownParts, countdownUnits } from '../../utils/event-countdown';
import { eventStatusBadge, eventStatusLabel } from '../../utils/event-status';
import { RELATIVE_TIME_TICK_MS } from './dashboard-activity.component';
import { DASHBOARD_PANEL_ID } from './dashboard-toolbar.component';
import type { SectionStatus } from './dashboard-summary.component';

const UNIT_KEY = {
  day: 'dashboard.today.unitDay',
  hour: 'dashboard.today.unitHour',
  minute: 'dashboard.today.unitMinute',
} as const;

/**
 * "Today & this week": the events that are in progress or start within 7
 * days, with a live countdown and the links an organizer needs on the day
 * (scan, attendees, check-in lists). It is not drawn at all while there is
 * nothing to show, and it loads and fails on its own. The countdown is
 * recomputed every minute on the device; it asks the server nothing.
 */
@Component({
  selector: 'app-dashboard-today',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
    LocalNumberPipe,
    PluralPipe,
  ],
  template: `
    @if (status() === 'error') {
      <div class="note note-error" role="alert" data-testid="today-error">
        <span class="flex-1">{{ error() }}</span>
        <button type="button" class="btn btn-sm btn-secondary" (click)="reload()">
          {{ 'common.retry' | transloco }}
        </button>
      </div>
    } @else if (status() === 'ready' && block(); as data) {
      @if (data.results.length > 0) {
        <section class="card p-5" aria-labelledby="dashboard-today-title" data-testid="today">
          <h2 id="dashboard-today-title" class="text-sm font-semibold text-foreground mb-3">
            {{ 'dashboard.today.title' | transloco }}
          </h2>
          <ul class="divide-y divide-border/60">
            @for (ev of data.results; track ev.id) {
              <li class="py-3 first:pt-0 last:pb-0" data-testid="today-event">
                <div class="flex flex-wrap items-center gap-2 mb-1">
                  @if (ev.in_progress) {
                    <span class="badge badge-published" data-testid="today-in-progress">{{
                      'dashboard.today.inProgress' | transloco
                    }}</span>
                  } @else {
                    <span class="text-xs font-medium text-primary" data-testid="today-countdown">{{
                      countdown(ev)
                    }}</span>
                  }
                  @if (ev.status !== 'published') {
                    <span class="badge" [class]="badgeClass(ev.status)">{{
                      statusKey(ev.status) | transloco
                    }}</span>
                  }
                  @if (!ev.is_owner) {
                    <span class="badge badge-info">{{ 'dashboard.coOrganizer' | transloco }}</span>
                  }
                </div>
                <h3 class="text-sm font-semibold text-foreground min-w-0">
                  <a
                    [routerLink]="['/events', ev.id]"
                    class="hover:underline break-words"
                    data-testid="today-title"
                    >{{ ev.title }}</a
                  >
                </h3>
                <div
                  class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-muted-foreground"
                >
                  <span class="flex items-center gap-1">
                    <lucide-icon [img]="icons.Calendar" class="w-3.5 h-3.5" aria-hidden="true" />
                    <time [attr.datetime]="ev.date">{{
                      ev.date | localDate: 'EEE, MMM d · h:mm a'
                    }}</time>
                  </span>
                  <span class="flex items-center gap-1 min-w-0">
                    <lucide-icon
                      [img]="icons.MapPin"
                      class="w-3.5 h-3.5 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <span class="truncate">{{ ev.location }}</span>
                  </span>
                </div>
                <p class="mt-1.5 text-xs text-foreground num flex flex-wrap gap-x-3">
                  <span data-testid="today-sold">{{
                    'dashboard.today.sold'
                      | transloco
                        : {
                            sold: (ev.stats.tickets_sold | localNumber),
                            capacity: (ev.stats.capacity | localNumber),
                          }
                  }}</span>
                  <span data-testid="today-checked-in">{{
                    'dashboard.today.checkedIn'
                      | transloco: { count: (ev.stats.checked_in | localNumber) }
                  }}</span>
                </p>
                <div class="flex flex-wrap gap-2 mt-2.5">
                  <a
                    routerLink="/scan"
                    class="btn btn-sm btn-secondary flex items-center gap-1"
                    [attr.aria-label]="
                      'dashboard.today.linkFor'
                        | transloco: { label: ('dashboard.scan' | transloco), title: ev.title }
                    "
                    data-testid="today-scan"
                  >
                    <lucide-icon [img]="icons.ScanLine" class="w-3.5 h-3.5" aria-hidden="true" />
                    {{ 'dashboard.scan' | transloco }}
                  </a>
                  <a
                    [routerLink]="['/organizer/events', ev.id, 'attendees']"
                    class="btn btn-sm btn-secondary flex items-center gap-1"
                    [attr.aria-label]="
                      'dashboard.today.linkFor'
                        | transloco: { label: ('nav.attendees' | transloco), title: ev.title }
                    "
                    data-testid="today-attendees"
                  >
                    <lucide-icon [img]="icons.Users" class="w-3.5 h-3.5" aria-hidden="true" />
                    {{ 'nav.attendees' | transloco }}
                  </a>
                  <a
                    [routerLink]="['/organizer/events', ev.id, 'checkin-lists']"
                    class="btn btn-sm btn-secondary"
                    [attr.aria-label]="
                      'dashboard.today.linkFor'
                        | transloco: { label: ('nav.checkinLists' | transloco), title: ev.title }
                    "
                    data-testid="today-checkin-lists"
                  >
                    {{ 'nav.checkinLists' | transloco }}
                  </a>
                </div>
              </li>
            }
          </ul>
          @if (data.more > 0) {
            <a
              [routerLink]="[]"
              [queryParams]="linkParams()"
              [fragment]="panelId"
              [replaceUrl]="true"
              class="inline-block mt-3 text-xs text-primary hover:underline"
              data-testid="today-more"
            >
              {{ 'dashboard.today.more' | tPlural: data.more }}
            </a>
          }
        </section>
      }
    }
  `,
})
export class DashboardTodayComponent implements OnInit {
  private readonly service = inject(OrganizerDashboardService);
  private readonly language = inject(LanguageService);
  private readonly destroyRef = inject(DestroyRef);

  /**
   * Query params of the "+N more" link: the Upcoming tab, plus whatever else
   * the page keeps in its URL (the chart range), so following the link loses nothing.
   */
  readonly linkParams = input<Params>({ tab: 'upcoming' });

  readonly status = signal<SectionStatus>('loading');
  readonly block = signal<TodayBlock | null>(null);
  readonly error = signal('');

  readonly icons = { Calendar, MapPin, ScanLine, Users };
  readonly panelId = DASHBOARD_PANEL_ID;

  /** The countdown is computed against this clock, which ticks without any request. */
  private readonly now = signal(Date.now());
  private readonly requests$ = new Subject<void>();

  constructor() {
    this.requests$
      .pipe(
        switchMap(() =>
          this.service.getToday().pipe(
            map((block) => ({ block })),
            catchError((err: unknown) =>
              of({
                message: errorMessage(err, this.language, {
                  fallback: this.language.t('dashboard.today.loadFailed'),
                }),
              }),
            ),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if ('block' in result) {
          this.block.set(result.block);
          this.status.set('ready');
        } else {
          this.error.set(result.message);
          this.status.set('error');
        }
      });

    // Outside the zone: the timer must not keep the app "unstable".
    const zone = inject(NgZone);
    const timer = zone.runOutsideAngular(() =>
      setInterval(() => {
        this.now.set(Date.now());
      }, RELATIVE_TIME_TICK_MS),
    );
    this.destroyRef.onDestroy(() => {
      clearInterval(timer);
    });
  }

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.status.set('loading');
    this.requests$.next();
  }

  statusKey(status: string): string {
    return eventStatusLabel(status);
  }

  badgeClass(status: string): string {
    return eventStatusBadge(status);
  }

  /** "Starts in 2 d 3 h", "Starts in 12 min", "Starting now". */
  countdown(event: TodayEvent): string {
    // Read so the text follows a language switch.
    this.language.lang();
    const parts = countdownParts(event.date, this.now());
    if (!parts) return this.language.t('dashboard.today.startingNow');
    const units = countdownUnits(parts);
    if (units.length === 0) return this.language.t('dashboard.today.lessThanMinute');
    const time = units.map(([unit, count]) => this.language.t(UNIT_KEY[unit], { count })).join(' ');
    return this.language.t('dashboard.today.startsIn', { time });
  }
}
