import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { EventService, type AdminDashboard } from '../../services/event.service';
import { apiErrorBody } from '../../api/api-error';
import { errorMessage } from '../../api/error-message';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { Event as EventModel } from '../../models/models';
import {
  LucideAngularModule,
  Shield,
  Users,
  CalendarDays,
  Ticket,
  Wallet,
  Check,
  X,
  Clock,
  UserPlus,
} from 'lucide-angular';
import { MoneyPipe } from '../../pipes/money.pipe';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-admin-moderation',
  standalone: true,
  imports: [
    MoneyPipe,
    CommonModule,
    FormsModule,
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">
        <p class="kicker mb-2">{{ 'dashboard.admin' | transloco }}</p>
        <h1
          class="font-display text-2xl font-semibold text-foreground mb-6 flex items-center gap-2"
        >
          <lucide-icon [img]="icons.Shield" class="w-6 h-6 text-ember" />
          {{ 'moderation.moderation' | transloco }}
        </h1>

        @if (!isAdmin) {
          <div class="card p-8 text-center">
            <p class="text-sm text-muted-foreground">
              {{ 'moderation.thisPageIsFor' | transloco }}
            </p>
            <a routerLink="/" class="btn btn-secondary btn-sm mt-4">{{
              'eventDetail.backToEvents' | transloco
            }}</a>
          </div>
        } @else {
          <!-- Platform stats -->
          @if (stats) {
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.Users" class="w-4 h-4" />
                  <span class="text-xs font-medium uppercase tracking-wide">{{
                    'moderation.users' | transloco
                  }}</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">{{ stats.total_users }}</p>
              </div>
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.CalendarDays" class="w-4 h-4" />
                  <span class="text-xs font-medium uppercase tracking-wide">{{
                    'dashboard.events' | transloco
                  }}</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">{{ stats.total_events }}</p>
                <p class="text-xs text-muted-foreground mt-0.5">
                  {{
                    'moderation.publishedeventsPublished'
                      | transloco: { publishedEvents: stats.published_events }
                  }}
                </p>
              </div>
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.Ticket" class="w-4 h-4" />
                  <span class="text-xs font-medium uppercase tracking-wide">{{
                    'dashboard.registrations' | transloco
                  }}</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">
                  {{ stats.total_registrations }}
                </p>
                <p class="text-xs text-muted-foreground mt-0.5">
                  {{
                    'moderation.confirmedregistrationsConfirmed'
                      | transloco: { confirmedRegistrations: stats.confirmed_registrations }
                  }}
                </p>
              </div>
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.Wallet" class="w-4 h-4" />
                  <span class="text-xs font-medium uppercase tracking-wide">{{
                    'dashboard.revenue' | transloco
                  }}</span>
                </div>
                <!-- One line per currency: amounts in different currencies can't be added up. -->
                @for (r of stats.revenue_by_currency; track r.currency) {
                  <p class="num text-2xl font-bold text-foreground">
                    {{ r.amount }}
                    <span class="text-sm font-semibold text-muted-foreground">{{
                      r.currency
                    }}</span>
                  </p>
                } @empty {
                  <p class="num text-2xl font-bold text-foreground">0</p>
                }
              </div>
            </div>
          }

          <!-- Pending queue -->
          <h2 class="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <lucide-icon [img]="icons.Clock" class="w-4 h-4 text-warning" />
            {{ 'moderation.awaitingApprovalPendinglength' | transloco: { pendingLength: total() } }}
          </h2>
          <p class="sr-only" role="status" aria-live="polite" data-testid="live-region">
            {{ announcement() }}
          </p>

          @if (status() === 'loading') {
            <div class="flex justify-center py-12"><span class="spinner"></span></div>
          } @else if (status() === 'error') {
            <div class="note note-error mb-8" role="alert" data-testid="pending-error">
              <span class="flex-1">{{ loadError() }}</span>
              <button type="button" class="btn btn-sm btn-secondary" (click)="reload()">
                {{ 'common.retry' | transloco }}
              </button>
            </div>
          } @else if (pending().length === 0 && total() === 0) {
            <div class="card p-8 text-center mb-8" data-testid="pending-empty">
              <p class="text-sm text-muted-foreground">
                {{ 'moderation.nothingToReviewThe' | transloco }}
              </p>
            </div>
          } @else {
            <div class="space-y-3 mb-4">
              @for (ev of pending(); track ev.id) {
                <div class="card p-4 flex items-start gap-4 flex-wrap" data-testid="pending-item">
                  <div class="flex-1 min-w-0">
                    <a
                      [routerLink]="['/events', ev.id]"
                      class="font-semibold text-foreground hover:text-primary transition-colors"
                    >
                      {{ ev.title }}
                    </a>
                    <p class="text-xs text-muted-foreground mt-0.5">
                      {{
                        'moderation.byUsernameDateLocation'
                          | transloco
                            : {
                                username: ev.organizer.username,
                                date: (ev.date | localDate: 'MMM d, y · h:mm a'),
                                location: ev.location,
                              }
                      }}
                    </p>
                    <p class="text-sm text-foreground/80 mt-1.5 line-clamp-2">
                      {{ ev.description }}
                    </p>
                    <p class="text-xs text-muted-foreground mt-1">
                      {{
                        ev.is_free ? ('common.free' | transloco) : (ev.price | money: ev.currency)
                      }}
                      ·
                      {{ 'moderation.capacityCount' | transloco: { count: ev.max_participants } }}
                      @if (ev.is_online) {
                        {{ 'moderation.online' | transloco }}
                      }
                    </p>
                  </div>
                  <div class="flex gap-2 flex-shrink-0">
                    <button
                      (click)="approve(ev)"
                      [disabled]="actingId() === ev.id"
                      data-testid="approve"
                      class="btn btn-sm flex items-center gap-1 bg-[color:var(--success)] text-[color:var(--success-foreground)] border-[color:var(--success)] hover:opacity-90"
                    >
                      <lucide-icon [img]="icons.Check" class="w-3.5 h-3.5" />
                      {{ 'common.approve' | transloco }}
                    </button>
                    <button
                      (click)="reject(ev)"
                      [disabled]="actingId() === ev.id"
                      data-testid="reject"
                      class="btn btn-sm btn-danger flex items-center gap-1"
                    >
                      <lucide-icon [img]="icons.X" class="w-3.5 h-3.5" />
                      {{ 'common.reject' | transloco }}
                    </button>
                  </div>
                </div>
              }
            </div>
            <div class="mb-8 flex flex-col items-center gap-2">
              <p class="text-xs text-muted-foreground" data-testid="pending-counter">
                {{
                  'dashboard.countOfTotal' | transloco: { shown: pending().length, total: total() }
                }}
              </p>
              @if (moreError(); as message) {
                <div class="note note-error w-full" role="alert" data-testid="pending-more-error">
                  {{ message }}
                </div>
              }
              @if (pending().length < total()) {
                <button
                  type="button"
                  class="btn btn-secondary btn-sm flex items-center gap-2"
                  [disabled]="loadingMore()"
                  (click)="showMore()"
                  data-testid="pending-more"
                >
                  @if (loadingMore()) {
                    <span class="spinner spinner-sm" aria-hidden="true"></span>
                  }
                  {{ 'dashboard.showMore' | transloco }}
                </button>
              }
            </div>
          }

          <!-- Create organizer -->
          <h2 class="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <lucide-icon [img]="icons.UserPlus" class="w-4 h-4 text-ember" />
            {{ 'moderation.createAnOrganizerAccount' | transloco }}
          </h2>
          <form class="card p-5 mb-8" (ngSubmit)="createOrganizer()" novalidate>
            <p class="text-xs text-muted-foreground mb-4">
              {{ 'moderation.attendeesCannotBecomeOrganizers' | transloco }}
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label
                  for="org-username"
                  class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'eventSettings.username' | transloco }}</label
                >
                <input
                  id="org-username"
                  type="text"
                  [(ngModel)]="orgForm.username"
                  name="username"
                  class="input"
                  [placeholder]="'moderation.organizerName' | transloco"
                  autocomplete="off"
                />
              </div>
              <div>
                <label for="org-email" class="block text-sm font-medium text-foreground mb-1.5">{{
                  'common.email' | transloco
                }}</label>
                <input
                  id="org-email"
                  type="email"
                  [(ngModel)]="orgForm.email"
                  name="email"
                  class="input"
                  [placeholder]="'moderation.organizerExampleCom' | transloco"
                  autocomplete="off"
                />
              </div>
              <div>
                <label for="org-first" class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'moderation.firstName' | transloco }}
                  <span class="text-muted-foreground font-normal">{{
                    'checkout.optional' | transloco
                  }}</span></label
                >
                <input
                  id="org-first"
                  type="text"
                  [(ngModel)]="orgForm.first_name"
                  name="first_name"
                  class="input"
                />
              </div>
              <div>
                <label for="org-last" class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'moderation.lastName' | transloco }}
                  <span class="text-muted-foreground font-normal">{{
                    'checkout.optional' | transloco
                  }}</span></label
                >
                <input
                  id="org-last"
                  type="text"
                  [(ngModel)]="orgForm.last_name"
                  name="last_name"
                  class="input"
                />
              </div>
              <div class="sm:col-span-2">
                <label
                  for="org-password"
                  class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'moderation.temporaryPassword' | transloco }}</label
                >
                <input
                  id="org-password"
                  type="text"
                  [(ngModel)]="orgForm.password"
                  name="password"
                  class="input"
                  [placeholder]="'moderation.minCharactersWithA' | transloco"
                  autocomplete="new-password"
                />
              </div>
            </div>
            <button
              type="submit"
              [disabled]="creatingOrganizer"
              class="btn btn-primary btn-sm flex items-center gap-1.5"
            >
              @if (creatingOrganizer) {
                <span class="spinner spinner-sm"></span>
              }
              {{ 'moderation.createOrganizer' | transloco }}
            </button>
          </form>

          <!-- Top events -->
          @if (stats && stats.top_events.length) {
            <h2 class="text-sm font-semibold text-foreground mb-3">
              {{ 'moderation.topEventsByRegistrations' | transloco }}
            </h2>
            <div class="card divide-y divide-border">
              @for (ev of stats.top_events; track ev.id) {
                <a
                  [routerLink]="['/events', ev.id]"
                  class="flex items-center justify-between gap-3 px-4 py-3 hover:bg-muted/40 transition-colors"
                >
                  <span class="text-sm font-medium text-foreground truncate">{{ ev.title }}</span>
                  <span class="text-xs text-muted-foreground flex-shrink-0">{{
                    'moderation.registeredcountRegistered'
                      | transloco: { registeredCount: ev.registered_count }
                  }}</span>
                </a>
              }
            </div>
          }
        }
      </div>
    </div>
  `,
})
export class AdminModerationComponent implements OnInit {
  private i18n = inject(LanguageService);
  private eventService = inject(EventService);
  private authService = inject(AuthService);
  private toast = inject(ToastService);
  private modal = inject(ModalService);

  private destroyRef = inject(DestroyRef);

  readonly pending = signal<EventModel[]>([]);
  /** How many events wait for review in all (the queue loads page by page). */
  readonly total = signal(0);
  readonly status = signal<'loading' | 'ready' | 'error'>('loading');
  readonly loadError = signal('');
  readonly moreError = signal<string | null>(null);
  readonly loadingMore = signal(false);
  readonly announcement = signal('');
  readonly actingId = signal<number | null>(null);
  stats: AdminDashboard | null = null;
  /** Events per page, as the server answered the first one. */
  private pageSize = 0;
  /** Bumped by every reload, so an answer to an abandoned request is ignored. */
  private generation = 0;

  orgForm = { username: '', email: '', password: '', first_name: '', last_name: '' };
  creatingOrganizer = false;

  readonly icons = { Shield, Users, CalendarDays, Ticket, Wallet, Check, X, Clock, UserPlus };

  get isAdmin(): boolean {
    return !!this.authService.currentUser?.is_superuser;
  }

  ngOnInit(): void {
    if (!this.isAdmin) return;
    this.loadPending();
    this.eventService.getAdminDashboard().subscribe({
      next: (s) => {
        this.stats = s;
      },
      error: () => {
        // The KPI cards stay hidden; moderation itself does not need them.
      },
    });
  }

  loadPending(): void {
    this.reload();
  }

  reload(): void {
    const generation = ++this.generation;
    this.status.set('loading');
    this.loadingMore.set(false);
    this.moreError.set(null);
    this.eventService
      .getEvents({ status: 'pending', page: 1 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          if (generation !== this.generation) return;
          this.pending.set(res.results);
          this.total.set(res.count);
          this.pageSize = res.results.length;
          this.status.set('ready');
          this.announce();
        },
        error: (err: unknown) => {
          if (generation !== this.generation) return;
          this.loadError.set(
            errorMessage(err, this.i18n, { fallback: this.i18n.t('moderation.failedToLoadThe') }),
          );
          this.status.set('error');
        },
      });
  }

  /**
   * Appends the next page. It is derived from what is loaded, so an approve or
   * reject shifting the server's pages skips nothing; duplicates are dropped.
   */
  showMore(): void {
    if (this.loadingMore() || this.pending().length >= this.total() || this.pageSize === 0) return;
    const generation = this.generation;
    this.loadingMore.set(true);
    this.moreError.set(null);
    const page = Math.floor(this.pending().length / this.pageSize) + 1;
    this.eventService
      .getEvents({ status: 'pending', page })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          if (generation !== this.generation) return;
          const seen = new Set(this.pending().map((e) => e.id));
          const fresh = res.results.filter((e) => !seen.has(e.id));
          this.pending.update((current) => [...current, ...fresh]);
          // Nothing new although the server counts more: stop offering "show more".
          this.total.set(fresh.length ? res.count : this.pending().length);
          this.loadingMore.set(false);
          this.announce();
        },
        error: (err: unknown) => {
          if (generation !== this.generation) return;
          this.moreError.set(
            errorMessage(err, this.i18n, { fallback: this.i18n.t('moderation.failedToLoadThe') }),
          );
          this.loadingMore.set(false);
        },
      });
  }

  private announce(): void {
    this.announcement.set(
      this.i18n.t('dashboard.showingOfTotal', {
        shown: this.pending().length,
        total: this.total(),
      }),
    );
  }

  /** The event is no longer waiting: drop it and the total, so the next page stays exact. */
  private remove(id: number): void {
    this.pending.update((list) => list.filter((e) => e.id !== id));
    this.total.update((n) => Math.max(0, n - 1));
    this.announce();
  }

  async approve(ev: EventModel): Promise<void> {
    const ok = await this.modal.open({
      title: this.i18n.t('eventDetail.approveEvent'),
      message: this.i18n.t('eventDetail.approveAndPublishTitle', { title: ev.title }),
      confirmText: this.i18n.t('common.approve'),
      cancelText: this.i18n.t('common.cancel'),
    });
    if (!ok) return;
    this.actingId.set(ev.id);
    this.eventService.approveEvent(ev.id).subscribe({
      next: () => {
        this.actingId.set(null);
        this.remove(ev.id);
        this.toast.success(this.i18n.t('moderation.titlePublished', { title: ev.title }));
      },
      error: () => {
        this.actingId.set(null);
        this.toast.error(this.i18n.t('moderation.approveFailed'));
      },
    });
  }

  createOrganizer(): void {
    const f = this.orgForm;
    if (!f.username.trim() || !f.email.trim() || !f.password) {
      this.toast.error(this.i18n.t('moderation.usernameEmailAndPassword'));
      return;
    }
    this.creatingOrganizer = true;
    this.authService
      .adminCreateOrganizer({
        username: f.username.trim(),
        email: f.email.trim(),
        password: f.password,
        first_name: f.first_name.trim(),
        last_name: f.last_name.trim(),
      })
      .subscribe({
        next: (user) => {
          this.creatingOrganizer = false;
          this.orgForm = { username: '', email: '', password: '', first_name: '', last_name: '' };
          this.toast.success(
            this.i18n.t('moderation.organizerUsernameCreated', { username: user.username }),
          );
        },
        error: (err) => {
          this.creatingOrganizer = false;
          const data = apiErrorBody(err);
          const msg = data
            ? Object.values(data).flat().join(' ')
            : this.i18n.t('moderation.couldNotCreateThe');
          this.toast.error(msg || this.i18n.t('moderation.couldNotCreateThe'));
        },
      });
  }

  async reject(ev: EventModel): Promise<void> {
    const ok = await this.modal.open({
      title: this.i18n.t('eventDetail.rejectEvent'),
      message: this.i18n.t('eventDetail.rejectTitleTheOrganizer', { title: ev.title }),
      confirmText: this.i18n.t('common.reject'),
      cancelText: this.i18n.t('common.cancel'),
      isDestructive: true,
    });
    if (!ok) return;
    this.actingId.set(ev.id);
    this.eventService.rejectEvent(ev.id).subscribe({
      next: () => {
        this.actingId.set(null);
        this.remove(ev.id);
        this.toast.success(this.i18n.t('moderation.titleRejected', { title: ev.title }));
      },
      error: () => {
        this.actingId.set(null);
        this.toast.error(this.i18n.t('moderation.rejectFailed'));
      },
    });
  }
}
