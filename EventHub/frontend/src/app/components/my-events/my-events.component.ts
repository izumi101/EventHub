import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { Event } from '../../models/models';
import {
  LucideAngularModule,
  Plus,
  Calendar,
  MapPin,
  SquarePen,
  Trash2,
  Users,
  Eye,
  Copy,
} from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';
import { errorMessage } from '../../api/error-message';
import { eventStatusBadge, eventStatusLabel } from '../../utils/event-status';

/** Pages in a row that may bring nothing new before "Show more" stops looking further. */
const MAX_EMPTY_PAGES = 3;

@Component({
  selector: 'app-my-events',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule, TranslocoPipe, LocalDatePipe],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">
        <!-- Header -->
        <div class="flex items-center justify-between mb-7">
          <div>
            <h1 class="text-2xl font-bold text-foreground">
              {{ 'myEvents.myEvents' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground mt-1">
              {{ 'myEvents.eventsYouHaveCreated' | transloco }}
            </p>
          </div>
          <a routerLink="/create-event" class="btn btn-primary flex items-center gap-1.5">
            <lucide-icon [img]="icons.Plus" class="w-4 h-4" aria-hidden="true" />
            {{ 'dashboard.createEvent' | transloco }}
          </a>
        </div>

        <!-- Loading -->
        @if (loading) {
          <div class="flex items-center justify-center py-20 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">{{ 'myEvents.loadingYourEvents' | transloco }}</span>
          </div>
        } @else if (events.length === 0) {
          <!-- Empty -->
          <div class="flex flex-col items-center justify-center py-20 text-center">
            <div class="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-4">
              <lucide-icon
                [img]="icons.Calendar"
                class="w-6 h-6 text-muted-foreground"
                aria-hidden="true"
              />
            </div>
            <h3 class="text-base font-semibold text-foreground mb-1">
              {{ 'myEvents.noEventsYet' | transloco }}
            </h3>
            <p class="text-sm text-muted-foreground mb-5 max-w-xs">
              {{ 'myEvents.createYourFirstEvent' | transloco }}
            </p>
            <a routerLink="/create-event" class="btn btn-primary btn-sm flex items-center gap-1.5">
              <lucide-icon [img]="icons.Plus" class="w-3.5 h-3.5" aria-hidden="true" />
              {{ 'dashboard.createEvent' | transloco }}
            </a>
          </div>
        } @else {
          <div class="card divide-y divide-border">
            @for (event of events; track event.id) {
              <div class="flex items-center gap-4 p-4 hover:bg-muted/40 transition-colors">
                <!-- Thumbnail -->
                <div class="w-16 h-12 rounded-md bg-muted overflow-hidden flex-shrink-0">
                  @if (event.image) {
                    <img
                      [src]="event.image"
                      [alt]="event.title"
                      class="w-full h-full object-cover"
                    />
                  } @else {
                    <div class="w-full h-full flex items-center justify-center bg-secondary">
                      <span class="text-lg font-bold text-muted-foreground/20">{{
                        event.title.charAt(0)
                      }}</span>
                    </div>
                  }
                </div>

                <!-- Info -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-0.5">
                    <span
                      class="badge {{ statusBadgeClass(event.status) }} text-2xs"
                      data-testid="status-badge"
                      >{{ statusLabel(event.status) | transloco }}</span
                    >
                  </div>
                  <p class="text-sm font-semibold text-foreground truncate">{{ event.title }}</p>
                  <div class="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                    <span class="flex items-center gap-1">
                      <lucide-icon [img]="icons.Calendar" class="w-3 h-3" aria-hidden="true" />
                      {{ event.date | localDate: 'MMM d, y' }}
                    </span>
                    <span class="flex items-center gap-1 truncate">
                      <lucide-icon [img]="icons.MapPin" class="w-3 h-3" aria-hidden="true" />
                      {{ event.location }}
                    </span>
                  </div>
                </div>

                <!-- Actions -->
                <div class="flex items-center gap-1 flex-shrink-0">
                  <a
                    [routerLink]="['/events', event.id]"
                    class="btn btn-ghost btn-sm p-2"
                    [title]="'myEvents.previewEvent' | transloco"
                    [attr.aria-label]="'myEvents.previewEvent' | transloco"
                  >
                    <lucide-icon [img]="icons.Eye" class="w-4 h-4" aria-hidden="true" />
                  </a>
                  <a
                    [routerLink]="['/organizer/events', event.id, 'attendees']"
                    class="btn btn-ghost btn-sm p-2"
                    [title]="'myEvents.manageAttendees' | transloco"
                    [attr.aria-label]="'myEvents.manageAttendees' | transloco"
                  >
                    <lucide-icon [img]="icons.Users" class="w-4 h-4" aria-hidden="true" />
                  </a>
                  <a
                    [routerLink]="['/edit-event', event.id]"
                    class="btn btn-ghost btn-sm p-2"
                    [title]="'dashboard.editEvent' | transloco"
                    [attr.aria-label]="'dashboard.editEvent' | transloco"
                  >
                    <lucide-icon [img]="icons.SquarePen" class="w-4 h-4" aria-hidden="true" />
                  </a>
                  <button
                    (click)="cloneEvent(event.id)"
                    [disabled]="cloningId === event.id"
                    class="btn btn-ghost btn-sm p-2"
                    [title]="'myEvents.duplicateEvent' | transloco"
                    [attr.aria-label]="'myEvents.duplicateEvent' | transloco"
                  >
                    @if (cloningId === event.id) {
                      <span class="spinner spinner-sm"></span>
                    } @else {
                      <lucide-icon [img]="icons.Copy" class="w-4 h-4" aria-hidden="true" />
                    }
                  </button>
                  <button
                    (click)="deleteEvent(event.id, event.title)"
                    class="btn btn-ghost btn-sm p-2 text-muted-foreground hover:text-destructive hover:bg-[color:var(--destructive-50)]"
                    [title]="'myEvents.deleteEvent' | transloco"
                    [attr.aria-label]="'myEvents.deleteEvent' | transloco"
                  >
                    <lucide-icon [img]="icons.Trash2" class="w-4 h-4" aria-hidden="true" />
                  </button>
                </div>
              </div>
            }
          </div>

          <div class="flex flex-col items-center gap-2 mt-4">
            <p class="text-xs text-muted-foreground" data-testid="events-counter">
              {{ 'dashboard.countOfTotal' | transloco: { shown: events.length, total: total } }}
            </p>
            @if (events.length < total) {
              <button
                type="button"
                class="btn btn-secondary btn-sm flex items-center gap-2"
                [disabled]="loadingMore"
                (click)="showMore()"
                data-testid="events-more"
              >
                @if (loadingMore) {
                  <span class="spinner spinner-sm" aria-hidden="true"></span>
                }
                {{ 'dashboard.showMore' | transloco }}
              </button>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class MyEventsComponent implements OnInit {
  private i18n = inject(LanguageService);
  private eventService = inject(EventService);
  private modalService = inject(ModalService);
  private toastService = inject(ToastService);

  events: Event[] = [];
  /** How many events the user has in all (the list below loads page by page). */
  total = 0;
  loading = false;
  loadingMore = false;
  cloningId: number | null = null;
  /** Events per page, as the server answered the first one. */
  private pageSize = 0;
  /** The lowest page "Show more" may ask for (after pages that brought nothing new). */
  private pageFloor = 1;

  readonly icons = { Plus, Calendar, MapPin, SquarePen, Trash2, Users, Eye, Copy };

  ngOnInit(): void {
    this.loadEvents();
  }

  loadEvents(): void {
    this.loading = true;
    this.eventService.getMyEvents({ page: 1 }).subscribe({
      next: (res) => {
        this.events = res.results;
        this.total = res.count;
        this.pageSize = res.results.length;
        this.pageFloor = 1;
        this.loading = false;
      },
      error: (err: unknown) => {
        this.toastService.error(
          errorMessage(err, this.i18n, { fallback: this.i18n.t('myEvents.failedToLoadEvents') }),
        );
        this.loading = false;
      },
    });
  }

  /** Appends the next page. It is derived from what is loaded, so a delete shifting the pages skips nothing. */
  showMore(): void {
    if (this.loadingMore || this.events.length >= this.total || this.pageSize === 0) return;
    this.loadingMore = true;
    const derived = Math.floor(this.events.length / this.pageSize) + 1;
    this.fetchMore(Math.max(derived, this.pageFloor), 0);
  }

  /**
   * A page can bring only events already shown (an event created elsewhere
   * shifted the order). The server's count stays the truth: while it says
   * there is a next page, ask for it, a bounded number of times.
   */
  private fetchMore(page: number, attempt: number): void {
    this.eventService.getMyEvents({ page }).subscribe({
      next: (res) => {
        const seen = new Set(this.events.map((e) => e.id));
        const fresh = res.results.filter((e) => !seen.has(e.id));
        this.events = [...this.events, ...fresh];
        this.total = res.count;
        this.pageFloor = fresh.length ? 1 : page + 1;
        if (!fresh.length && res.next && attempt < MAX_EMPTY_PAGES) {
          this.fetchMore(page + 1, attempt + 1);
          return;
        }
        this.loadingMore = false;
      },
      error: (err: unknown) => {
        this.toastService.error(
          errorMessage(err, this.i18n, { fallback: this.i18n.t('myEvents.failedToLoadEvents') }),
        );
        this.loadingMore = false;
      },
    });
  }

  cloneEvent(id: number): void {
    this.cloningId = id;
    this.eventService.cloneEvent(id).subscribe({
      next: () => {
        this.cloningId = null;
        this.toastService.success(this.i18n.t('myEvents.eventDuplicatedAsA'));
        this.loadEvents();
      },
      error: (err: unknown) => {
        this.cloningId = null;
        this.toastService.error(
          errorMessage(err, this.i18n, {
            fallback: this.i18n.t('myEvents.couldNotDuplicateEvent'),
            fields: ['error'],
          }),
        );
      },
    });
  }

  statusBadgeClass(status: string): string {
    return eventStatusBadge(status);
  }

  /** Translation key of the status; one this client does not know shows as the server sent it. */
  statusLabel(status: string): string {
    return eventStatusLabel(status);
  }

  async deleteEvent(id: number, title: string): Promise<void> {
    const ok = await this.modalService.open({
      title: this.i18n.t('dashboard.deleteEvent'),
      message: this.i18n.t('myEvents.deleteTitleThisCannot', { title: title }),
      confirmText: this.i18n.t('dashboard.deleteEvent'),
      cancelText: this.i18n.t('myEvents.keepEvent'),
      isDestructive: true,
    });
    if (!ok) return;
    this.eventService.deleteEvent(id).subscribe({
      next: () => {
        this.events = this.events.filter((e) => e.id !== id);
        this.total = Math.max(0, this.total - 1);
        this.toastService.success(this.i18n.t('dashboard.eventDeleted'));
      },
      error: (err: unknown) =>
        this.toastService.error(
          errorMessage(err, this.i18n, {
            fallback: this.i18n.t('dashboard.failedToDeleteEvent'),
            fields: ['error', 'detail'],
          }),
        ),
    });
  }
}
