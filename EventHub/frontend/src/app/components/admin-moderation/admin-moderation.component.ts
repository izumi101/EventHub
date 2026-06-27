import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { AuthService } from '../../services/auth.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, Shield, Users, CalendarDays, Ticket, Wallet, Check, X, Clock, UserPlus } from 'lucide-angular';

@Component({
  selector: 'app-admin-moderation',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">

        <p class="kicker mb-2">Admin</p>
        <h1 class="font-display text-2xl font-semibold text-foreground mb-6 flex items-center gap-2">
          <lucide-icon [img]="icons.Shield" class="w-6 h-6 text-ember"></lucide-icon>
          Moderation
        </h1>

        @if (!isAdmin) {
          <div class="card p-8 text-center">
            <p class="text-sm text-muted-foreground">This page is for administrators only.</p>
            <a routerLink="/" class="btn btn-secondary btn-sm mt-4">Back to events</a>
          </div>
        } @else {

          <!-- Platform stats -->
          @if (stats) {
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.Users" class="w-4 h-4"></lucide-icon>
                  <span class="text-xs font-medium uppercase tracking-wide">Users</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">{{ stats.total_users }}</p>
              </div>
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.CalendarDays" class="w-4 h-4"></lucide-icon>
                  <span class="text-xs font-medium uppercase tracking-wide">Events</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">{{ stats.total_events }}</p>
                <p class="text-xs text-muted-foreground mt-0.5">{{ stats.published_events }} published</p>
              </div>
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.Ticket" class="w-4 h-4"></lucide-icon>
                  <span class="text-xs font-medium uppercase tracking-wide">Registrations</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">{{ stats.total_registrations }}</p>
                <p class="text-xs text-muted-foreground mt-0.5">{{ stats.confirmed_registrations }} confirmed</p>
              </div>
              <div class="card p-4">
                <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                  <lucide-icon [img]="icons.Wallet" class="w-4 h-4"></lucide-icon>
                  <span class="text-xs font-medium uppercase tracking-wide">Revenue</span>
                </div>
                <p class="num text-2xl font-bold text-foreground">{{ '$' + stats.total_revenue }}</p>
              </div>
            </div>
          }

          <!-- Pending queue -->
          <h2 class="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <lucide-icon [img]="icons.Clock" class="w-4 h-4 text-warning"></lucide-icon>
            Awaiting approval ({{ pending.length }})
          </h2>

          @if (loading) {
            <div class="flex justify-center py-12"><span class="spinner"></span></div>
          } @else if (pending.length === 0) {
            <div class="card p-8 text-center mb-8">
              <p class="text-sm text-muted-foreground">Nothing to review — the moderation queue is empty. 🎉</p>
            </div>
          } @else {
            <div class="space-y-3 mb-8">
              @for (ev of pending; track ev.id) {
                <div class="card p-4 flex items-start gap-4 flex-wrap">
                  <div class="flex-1 min-w-0">
                    <a [routerLink]="['/events', ev.id]" class="font-semibold text-foreground hover:text-primary transition-colors">
                      {{ ev.title }}
                    </a>
                    <p class="text-xs text-muted-foreground mt-0.5">
                      by @{{ ev.organizer.username }} · {{ ev.date | date:'MMM d, y · h:mm a' }} · {{ ev.location }}
                    </p>
                    <p class="text-sm text-foreground/80 mt-1.5 line-clamp-2">{{ ev.description }}</p>
                    <p class="text-xs text-muted-foreground mt-1">
                      {{ ev.is_free ? 'Free' : '$' + ev.price }} · capacity {{ ev.max_participants }}
                      @if (ev.is_online) { · online }
                    </p>
                  </div>
                  <div class="flex gap-2 flex-shrink-0">
                    <button (click)="approve(ev)" [disabled]="actingId === ev.id"
                      class="btn btn-sm flex items-center gap-1" style="background:#15803d;color:#fff;border-color:#15803d">
                      <lucide-icon [img]="icons.Check" class="w-3.5 h-3.5"></lucide-icon>
                      Approve
                    </button>
                    <button (click)="reject(ev)" [disabled]="actingId === ev.id"
                      class="btn btn-sm btn-danger flex items-center gap-1">
                      <lucide-icon [img]="icons.X" class="w-3.5 h-3.5"></lucide-icon>
                      Reject
                    </button>
                  </div>
                </div>
              }
            </div>
          }

          <!-- Create organizer -->
          <h2 class="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <lucide-icon [img]="icons.UserPlus" class="w-4 h-4 text-ember"></lucide-icon>
            Create an organizer account
          </h2>
          <form class="card p-5 mb-8" (ngSubmit)="createOrganizer()" novalidate>
            <p class="text-xs text-muted-foreground mb-4">
              Attendees cannot become organizers on their own — new organizer accounts are provisioned here.
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label for="org-username" class="block text-sm font-medium text-foreground mb-1.5">Username</label>
                <input id="org-username" type="text" [(ngModel)]="orgForm.username" name="username" class="input" placeholder="organizer_name" autocomplete="off" />
              </div>
              <div>
                <label for="org-email" class="block text-sm font-medium text-foreground mb-1.5">Email</label>
                <input id="org-email" type="email" [(ngModel)]="orgForm.email" name="email" class="input" placeholder="organizer@example.com" autocomplete="off" />
              </div>
              <div>
                <label for="org-first" class="block text-sm font-medium text-foreground mb-1.5">First name <span class="text-muted-foreground font-normal">(optional)</span></label>
                <input id="org-first" type="text" [(ngModel)]="orgForm.first_name" name="first_name" class="input" />
              </div>
              <div>
                <label for="org-last" class="block text-sm font-medium text-foreground mb-1.5">Last name <span class="text-muted-foreground font-normal">(optional)</span></label>
                <input id="org-last" type="text" [(ngModel)]="orgForm.last_name" name="last_name" class="input" />
              </div>
              <div class="sm:col-span-2">
                <label for="org-password" class="block text-sm font-medium text-foreground mb-1.5">Temporary password</label>
                <input id="org-password" type="text" [(ngModel)]="orgForm.password" name="password" class="input" placeholder="Min 8 characters, with a number" autocomplete="new-password" />
              </div>
            </div>
            <button type="submit" [disabled]="creatingOrganizer" class="btn btn-primary btn-sm flex items-center gap-1.5">
              @if (creatingOrganizer) { <span class="spinner spinner-sm"></span> }
              Create organizer
            </button>
          </form>

          <!-- Top events -->
          @if (stats?.top_events?.length) {
            <h2 class="text-sm font-semibold text-foreground mb-3">Top events by registrations</h2>
            <div class="card divide-y divide-border">
              @for (ev of stats.top_events; track ev.id) {
                <a [routerLink]="['/events', ev.id]" class="flex items-center justify-between gap-3 px-4 py-3 hover:bg-muted/40 transition-colors">
                  <span class="text-sm font-medium text-foreground truncate">{{ ev.title }}</span>
                  <span class="text-xs text-muted-foreground flex-shrink-0">{{ ev.registered_count }} registered</span>
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
  pending: EventModel[] = [];
  stats: any = null;
  loading = false;
  actingId: number | null = null;

  orgForm = { username: '', email: '', password: '', first_name: '', last_name: '' };
  creatingOrganizer = false;

  readonly icons = { Shield, Users, CalendarDays, Ticket, Wallet, Check, X, Clock, UserPlus };

  constructor(
    private eventService: EventService,
    private authService: AuthService,
    private toast: ToastService,
    private modal: ModalService,
  ) {}

  get isAdmin(): boolean {
    return !!this.authService.currentUser?.is_superuser;
  }

  ngOnInit(): void {
    if (!this.isAdmin) return;
    this.loadPending();
    this.eventService.getAdminDashboard().subscribe({
      next: s => { this.stats = s; },
      error: () => {},
    });
  }

  loadPending(): void {
    this.loading = true;
    this.eventService.getEvents({ status: 'pending' }).subscribe({
      next: res => { this.pending = res.results; this.loading = false; },
      error: () => { this.loading = false; this.toast.error('Failed to load the moderation queue.'); },
    });
  }

  async approve(ev: EventModel): Promise<void> {
    const ok = await this.modal.open({
      title: 'Approve Event',
      message: `Approve and publish "${ev.title}"?`,
      confirmText: 'Approve',
      cancelText: 'Cancel',
    });
    if (!ok) return;
    this.actingId = ev.id;
    this.eventService.approveEvent(ev.id).subscribe({
      next: () => {
        this.actingId = null;
        this.pending = this.pending.filter(e => e.id !== ev.id);
        this.toast.success(`"${ev.title}" published.`);
      },
      error: () => { this.actingId = null; this.toast.error('Approve failed.'); },
    });
  }

  createOrganizer(): void {
    const f = this.orgForm;
    if (!f.username.trim() || !f.email.trim() || !f.password) {
      this.toast.error('Username, email and password are required.');
      return;
    }
    this.creatingOrganizer = true;
    this.authService.adminCreateOrganizer({
      username: f.username.trim(),
      email: f.email.trim(),
      password: f.password,
      first_name: f.first_name.trim(),
      last_name: f.last_name.trim(),
    }).subscribe({
      next: user => {
        this.creatingOrganizer = false;
        this.orgForm = { username: '', email: '', password: '', first_name: '', last_name: '' };
        this.toast.success(`Organizer "${user.username}" created.`);
      },
      error: err => {
        this.creatingOrganizer = false;
        const data = err.error;
        const msg = data && typeof data === 'object'
          ? Object.values(data).flat().join(' ')
          : 'Could not create the organizer.';
        this.toast.error(msg || 'Could not create the organizer.');
      },
    });
  }

  async reject(ev: EventModel): Promise<void> {
    const ok = await this.modal.open({
      title: 'Reject Event',
      message: `Reject "${ev.title}"? The organizer will see it as declined.`,
      confirmText: 'Reject',
      cancelText: 'Cancel',
      isDestructive: true,
    });
    if (!ok) return;
    this.actingId = ev.id;
    this.eventService.rejectEvent(ev.id).subscribe({
      next: () => {
        this.actingId = null;
        this.pending = this.pending.filter(e => e.id !== ev.id);
        this.toast.success(`"${ev.title}" rejected.`);
      },
      error: () => { this.actingId = null; this.toast.error('Reject failed.'); },
    });
  }
}
