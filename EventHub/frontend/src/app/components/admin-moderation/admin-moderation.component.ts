import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { EventService, type AdminDashboard } from '../../services/event.service';
import { apiErrorBody } from '../../api/api-error';
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
            {{
              'moderation.awaitingApprovalPendinglength'
                | transloco: { pendingLength: pending.length }
            }}
          </h2>

          @if (loading) {
            <div class="flex justify-center py-12"><span class="spinner"></span></div>
          } @else if (pending.length === 0) {
            <div class="card p-8 text-center mb-8">
              <p class="text-sm text-muted-foreground">
                {{ 'moderation.nothingToReviewThe' | transloco }}
              </p>
            </div>
          } @else {
            <div class="space-y-3 mb-8">
              @for (ev of pending; track ev.id) {
                <div class="card p-4 flex items-start gap-4 flex-wrap">
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
                      [disabled]="actingId === ev.id"
                      class="btn btn-sm flex items-center gap-1"
                      style="background:#15803d;color:#fff;border-color:#15803d"
                    >
                      <lucide-icon [img]="icons.Check" class="w-3.5 h-3.5" />
                      {{ 'common.approve' | transloco }}
                    </button>
                    <button
                      (click)="reject(ev)"
                      [disabled]="actingId === ev.id"
                      class="btn btn-sm btn-danger flex items-center gap-1"
                    >
                      <lucide-icon [img]="icons.X" class="w-3.5 h-3.5" />
                      {{ 'common.reject' | transloco }}
                    </button>
                  </div>
                </div>
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

  pending: EventModel[] = [];
  stats: AdminDashboard | null = null;
  loading = false;
  actingId: number | null = null;

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
    this.loading = true;
    this.eventService.getEvents({ status: 'pending' }).subscribe({
      next: (res) => {
        this.pending = res.results;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.toast.error(this.i18n.t('moderation.failedToLoadThe'));
      },
    });
  }

  async approve(ev: EventModel): Promise<void> {
    const ok = await this.modal.open({
      title: this.i18n.t('eventDetail.approveEvent'),
      message: this.i18n.t('eventDetail.approveAndPublishTitle', { title: ev.title }),
      confirmText: this.i18n.t('common.approve'),
      cancelText: this.i18n.t('common.cancel'),
    });
    if (!ok) return;
    this.actingId = ev.id;
    this.eventService.approveEvent(ev.id).subscribe({
      next: () => {
        this.actingId = null;
        this.pending = this.pending.filter((e) => e.id !== ev.id);
        this.toast.success(this.i18n.t('moderation.titlePublished', { title: ev.title }));
      },
      error: () => {
        this.actingId = null;
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
    this.actingId = ev.id;
    this.eventService.rejectEvent(ev.id).subscribe({
      next: () => {
        this.actingId = null;
        this.pending = this.pending.filter((e) => e.id !== ev.id);
        this.toast.success(this.i18n.t('moderation.titleRejected', { title: ev.title }));
      },
      error: () => {
        this.actingId = null;
        this.toast.error(this.i18n.t('moderation.rejectFailed'));
      },
    });
  }
}
