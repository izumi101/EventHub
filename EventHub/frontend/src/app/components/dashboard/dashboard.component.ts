import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { AuthService } from '../../services/auth.service';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { Event, EventStatsResponse } from '../../models/models';
import { forkJoin } from 'rxjs';
import {
  LucideAngularModule,
  Plus,
  Calendar,
  MapPin,
  Users,
  CheckCircle,
  BarChart2,
  ScanLine,
  Search,
  Edit3,
  Copy,
  Trash2,
  MoreHorizontal,
  TrendingUp,
  DollarSign,
} from 'lucide-angular';

type EventTab = 'upcoming' | 'past' | 'drafts';
type SortKey = 'date' | 'registrations' | 'checkin' | 'capacity';

interface ActivityItem {
  id: string;
  message: string;
  timestamp: Date;
  type: 'registration' | 'approval' | 'change';
}

interface EventWithStats extends Event {
  stats?: EventStatsResponse;
  revenue?: number;
  capacityPercent?: number;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-6xl py-8">

        <!-- Header -->
        <div class="mb-8">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <div>
              <p class="kicker mb-2">{{ isAdmin ? 'Admin' : 'Workspace' }}</p>
              <h1 class="text-3xl font-semibold text-foreground">
                {{ isAdmin ? 'Admin Panel' : 'Organizer Dashboard' }}
              </h1>
              <p class="text-sm text-muted-foreground mt-1.5">
                {{ isAdmin ? 'Review and approve events' : 'Manage your events and track performance' }}
              </p>
            </div>
            @if (!isAdmin) {
              <div class="flex items-center gap-2 flex-shrink-0">
                <a routerLink="/scan" class="btn btn-secondary flex items-center gap-1.5">
                  <lucide-icon [img]="icons.ScanLine" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                  Scan
                </a>
                <a routerLink="/create-event" class="btn btn-primary flex items-center gap-1.5">
                  <lucide-icon [img]="icons.Plus" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                  New event
                </a>
              </div>
            }
          </div>

          <!-- Stats row -->
          @if (!isAdmin && events.length > 0) {
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div class="card p-4">
                <p class="text-xs text-muted-foreground font-medium mb-1">Events</p>
                <div class="flex items-baseline gap-2">
                  <p class="text-2xl font-bold text-foreground num">{{ filteredEvents.length }}</p>
                  <span class="text-xs text-[color:var(--pine-600)] flex items-center gap-0.5" *ngIf="eventsTrend">
                    <lucide-icon [img]="icons.TrendingUp" class="w-3 h-3" aria-hidden="true"></lucide-icon>
                    {{ eventsTrend }}
                  </span>
                </div>
              </div>
              <div class="card p-4">
                <p class="text-xs text-muted-foreground font-medium mb-1">Registrations</p>
                <div class="flex items-baseline gap-2">
                  <p class="text-2xl font-bold text-foreground num">{{ totalRegistrations }}</p>
                  <span class="text-xs text-[color:var(--pine-600)] flex items-center gap-0.5" *ngIf="regTrend">
                    <lucide-icon [img]="icons.TrendingUp" class="w-3 h-3" aria-hidden="true"></lucide-icon>
                    {{ regTrend }}
                  </span>
                </div>
              </div>
              <div class="card p-4">
                <p class="text-xs text-muted-foreground font-medium mb-1">Check-in Rate</p>
                <p class="text-2xl font-bold text-foreground num">{{ totalCheckinRate }}%</p>
              </div>
              <div class="card p-4">
                <p class="text-xs text-muted-foreground font-medium mb-1">Revenue</p>
                <p class="text-2xl font-bold text-foreground num">{{ totalRevenue | number:'1.0-0' }} KZT</p>
              </div>
            </div>
          }
        </div>

        <!-- Controls: Search, Filter, Sort, View toggle -->
        @if (!isAdmin) {
          <div class="mb-6 space-y-3">
            <!-- Search + Sort -->
            <div class="flex flex-col sm:flex-row gap-3">
              <label class="flex items-center gap-2 flex-1 border border-border rounded-md px-3 h-10 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow">
                <lucide-icon [img]="icons.Search" class="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true"></lucide-icon>
                <input
                  type="search"
                  [(ngModel)]="searchQuery"
                  (input)="applyFilters()"
                  placeholder="Search events..."
                  class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
                  aria-label="Search events"
                />
              </label>
              <select
                [(ngModel)]="sortBy"
                (change)="applyFilters()"
                class="input h-10 sm:w-40"
                aria-label="Sort events"
              >
                <option value="date">Date (newest)</option>
                <option value="registrations">Most registrations</option>
                <option value="checkin">Check-in rate</option>
                <option value="capacity">Capacity filled</option>
              </select>
            </div>

            <!-- Tabs: Upcoming / Past / Drafts -->
            <div class="flex items-center gap-2 border-b border-border">
              <button
                (click)="setTab('upcoming')"
                [class]="currentTab === 'upcoming'
                  ? 'px-4 py-2 text-sm font-medium text-primary border-b-2 border-primary -mb-px'
                  : 'px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground'"
              >
                Upcoming ({{ upcomingCount }})
              </button>
              <button
                (click)="setTab('past')"
                [class]="currentTab === 'past'
                  ? 'px-4 py-2 text-sm font-medium text-primary border-b-2 border-primary -mb-px'
                  : 'px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground'"
              >
                Past ({{ pastCount }})
              </button>
              <button
                (click)="setTab('drafts')"
                [class]="currentTab === 'drafts'
                  ? 'px-4 py-2 text-sm font-medium text-primary border-b-2 border-primary -mb-px'
                  : 'px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground'"
              >
                Drafts ({{ draftCount }})
              </button>
              <div class="flex-1"></div>
              <!-- View toggle: List / Calendar -->
              <div class="flex items-center gap-1 border-l border-border pl-2">
                <button
                  (click)="viewMode = 'list'"
                  [class]="viewMode === 'list' ? 'px-2 py-2 text-primary' : 'px-2 py-2 text-muted-foreground hover:text-foreground'"
                  title="List view"
                  aria-label="List view"
                >
                  ≡
                </button>
                <button
                  (click)="viewMode = 'calendar'"
                  [class]="viewMode === 'calendar' ? 'px-2 py-2 text-primary' : 'px-2 py-2 text-muted-foreground hover:text-foreground'"
                  title="Calendar view"
                  aria-label="Calendar view"
                >
                  <lucide-icon [img]="icons.Calendar" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                </button>
              </div>
            </div>
          </div>
        }

        <!-- Loading / Empty state -->
        @if (loading) {
          <div class="flex items-center justify-center py-20 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading dashboard...</span>
          </div>
        } @else if (filteredEvents.length === 0) {
          <div class="card p-12 flex flex-col items-center text-center">
            <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.BarChart2" class="w-5 h-5 text-muted-foreground" aria-hidden="true"></lucide-icon>
            </div>
            <h3 class="text-base font-semibold text-foreground mb-1">
              {{ isAdmin ? 'No pending events' : tabEmptyLabel }}
            </h3>
            <p class="text-sm text-muted-foreground mb-5 max-w-xs">
              {{ tabEmptyMessage }}
            </p>
            @if (!isAdmin && currentTab === 'drafts') {
              <a routerLink="/create-event" class="btn btn-primary btn-sm flex items-center gap-1.5">
                <lucide-icon [img]="icons.Plus" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                Create event
              </a>
            }
          </div>
        } @else {
          <!-- LIST VIEW -->
          @if (viewMode === 'list') {
            <div class="space-y-4">
              @for (event of filteredEvents; track event.id) {
                <div class="card p-5 hover:border-primary/30 transition-colors">

                  <!-- Event header -->
                  <div class="flex flex-col sm:flex-row sm:items-start gap-4 mb-4">
                    <!-- Left: title + meta -->
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2 mb-2">
                        <span class="badge {{ statusBadgeClass(event.status) }}">{{ event.status }}</span>
                        <!-- Status timeline mini -->
                        <span class="text-xs text-muted-foreground">
                          {{ statusTimeline(event) }}
                        </span>
                      </div>
                      <p class="text-base font-semibold text-foreground truncate">{{ event.title }}</p>
                      <div class="flex flex-wrap items-center gap-3 mt-2 text-xs text-muted-foreground">
                        <span class="flex items-center gap-1">
                          <lucide-icon [img]="icons.Calendar" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                          {{ event.date | date:'MMM d, y · HH:mm' }}
                        </span>
                        <span class="flex items-center gap-1 truncate">
                          <lucide-icon [img]="icons.MapPin" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                          {{ event.location }}
                        </span>
                      </div>
                    </div>

                    <!-- Right: quick actions menu -->
                    @if (!isAdmin) {
                      <div class="flex items-start gap-2 flex-shrink-0">
                        <a
                          [routerLink]="['/organizer/events', event.id, 'attendees']"
                          class="btn btn-sm btn-secondary flex items-center gap-1"
                        >
                          <lucide-icon [img]="icons.Users" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                          Attendees
                        </a>
                        <!-- Quick actions menu (·××) -->
                        <div class="relative" [@.disabled]="true">
                          <button
                            (click)="toggleMenu(event.id)"
                            class="btn btn-sm btn-ghost p-2"
                            [attr.aria-label]="'Menu for ' + event.title"
                          >
                            <lucide-icon [img]="icons.MoreHorizontal" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                          </button>
                          @if (openMenuId === event.id) {
                            <div class="absolute right-0 mt-1 bg-background border border-border rounded-md shadow-lg z-10 min-w-40 animate-fade-in">
                              <a
                                [routerLink]="['/edit-event', event.id]"
                                (click)="openMenuId = null"
                                class="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                              >
                                <lucide-icon [img]="icons.Edit3" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                                Edit event
                              </a>
                              <button
                                (click)="duplicateEvent(event.id)"
                                class="w-full text-left flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                              >
                                <lucide-icon [img]="icons.Copy" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                                Duplicate
                              </button>
                              <button
                                (click)="deleteEvent(event.id)"
                                class="w-full text-left flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-[color:var(--destructive-50)] transition-colors"
                              >
                                <lucide-icon [img]="icons.Trash2" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                                Delete
                              </button>
                            </div>
                          }
                        </div>
                      </div>
                    }
                  </div>

                  <!-- Metrics row: capacity + registration + checkin + revenue -->
                  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                    <!-- Capacity -->
                    <div>
                      <div class="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>Capacity</span>
                        <span class="font-semibold text-foreground">{{ event.stats?.total_registrations }}/{{ event.max_participants }}</span>
                      </div>
                      <div class="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          class="h-full bg-primary rounded-full"
                          [style.width.%]="event.capacityPercent || 0"
                        ></div>
                      </div>
                      <p class="text-xs text-muted-foreground mt-1">{{ event.capacityPercent || 0 }}% filled</p>
                    </div>

                    <!-- Registrations -->
                    <div>
                      <p class="text-xs text-muted-foreground mb-1">Registrations</p>
                      <p class="text-lg font-bold text-foreground">{{ event.stats?.total_registrations || 0 }}</p>
                      <p class="text-xs text-muted-foreground mt-1">
                        {{ (event.stats?.total_registrations || 0) > 0
                          ? ((event.stats?.checked_in || 0) / (event.stats?.total_registrations || 1) * 100 | number:'1.0-0') + '% checked in'
                          : 'No registrations' }}
                      </p>
                    </div>

                    <!-- Check-in -->
                    <div>
                      <p class="text-xs text-muted-foreground mb-1">Check-in Rate</p>
                      <p class="text-lg font-bold text-foreground">{{ event.stats?.check_in_rate || 0 }}%</p>
                      <p class="text-xs text-muted-foreground mt-1">{{ event.stats?.checked_in || 0 }} checked in</p>
                    </div>

                    <!-- Revenue (if paid) -->
                    @if (!event.is_free && event.revenue !== null) {
                      <div>
                        <div class="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                          <lucide-icon [img]="icons.DollarSign" class="w-3 h-3" aria-hidden="true"></lucide-icon>
                          <span>Revenue</span>
                        </div>
                        <p class="text-lg font-bold text-foreground">{{ event.revenue | number:'1.0-0' }}</p>
                        <p class="text-xs text-muted-foreground mt-1">{{ event.price }} × {{ event.stats?.total_registrations || 0 }}</p>
                      </div>
                    }
                  </div>

                  <!-- Bottom: Preview link -->
                  <a [routerLink]="['/events', event.id]" class="text-xs text-primary hover:underline flex items-center gap-1">
                    View event →
                  </a>
                </div>
              }
            </div>

            <!-- Activity feed (bottom) -->
            @if (activityFeed.length > 0) {
              <div class="mt-8">
                <h2 class="text-sm font-semibold text-foreground mb-4">Recent activity</h2>
                <div class="space-y-2">
                  @for (item of activityFeed.slice(0, 5); track item.id) {
                    <div class="flex gap-3 text-sm text-muted-foreground">
                      <span class="text-xs text-muted-foreground flex-shrink-0">
                        {{ item.timestamp | date:'short' }}
                      </span>
                      <p>{{ item.message }}</p>
                    </div>
                  }
                </div>
              </div>
            }
          }

          <!-- CALENDAR VIEW (placeholder) -->
          @if (viewMode === 'calendar') {
            <div class="card p-8 text-center text-muted-foreground">
              <p class="text-sm">Calendar view coming soon. Use list view for now.</p>
            </div>
          }
        }
      </div>
    </div>
  `,
})
export class DashboardComponent implements OnInit {
  events: EventWithStats[] = [];
  filteredEvents: EventWithStats[] = [];
  activityFeed: ActivityItem[] = [];

  // Filter state
  searchQuery = '';
  sortBy: SortKey = 'date';
  currentTab: EventTab = 'upcoming';
  viewMode: 'list' | 'calendar' = 'list';
  openMenuId: number | null = null;

  // UI state
  isAdmin = false;
  loading = true;

  // Counters
  upcomingCount = 0;
  pastCount = 0;
  draftCount = 0;

  // Stats
  totalRegistrations = 0;
  totalCheckinRate = 0;
  totalRevenue = 0;
  eventsTrend = '+0';
  regTrend = '+0';

  readonly icons = {
    Plus,
    Calendar,
    MapPin,
    Users,
    CheckCircle,
    BarChart2,
    ScanLine,
    Search,
    Edit3,
    Copy,
    Trash2,
    MoreHorizontal,
    TrendingUp,
    DollarSign,
  };

  constructor(
    private eventService: EventService,
    private authService: AuthService,
    private modalService: ModalService,
    private toastService: ToastService,
  ) {}

  ngOnInit(): void {
    this.authService.getProfile().subscribe({
      next: user => {
        this.isAdmin = !!user?.is_superuser;
        this.isAdmin ? this.loadPendingEvents() : this.loadMyEvents();
      },
      error: () => {
        this.isAdmin = !!this.authService.currentUser?.is_superuser;
        this.loading = false;
      },
    });
  }

  private loadPendingEvents(): void {
    this.eventService.getEvents({ status: 'pending' }).subscribe({
      next: res => {
        this.events = res.results;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  private loadMyEvents(): void {
    this.eventService.getMyEvents().subscribe({
      next: res => {
        this.events = (res.results ?? (res as any)) || [];
        this.loadStats();
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  private loadStats(): void {
    if (!this.events.length) {
      this.loading = false;
      this.applyFilters();
      return;
    }
    forkJoin(this.events.map(e => this.eventService.getEventStats(e.id))).subscribe({
      next: statsList => {
        statsList.forEach((s, i) => {
          this.events[i].stats = s;
          this.events[i].capacityPercent = Math.round(
            ((s.total_registrations || 0) / this.events[i].max_participants) * 100
          );
          this.events[i].revenue = (Number(this.events[i].price) || 0) * (s.total_registrations || 0);
        });
        this.applyFilters();
        this.buildActivityFeed();
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  setTab(tab: EventTab): void {
    this.currentTab = tab;
    this.applyFilters();
  }

  applyFilters(): void {
    const now = new Date();

    // Split by date
    const upcoming = this.events.filter(e => new Date(e.date) > now);
    const past = this.events.filter(e => new Date(e.date) <= now);
    const drafts = this.events.filter(e => e.status === 'draft');

    // Count tabs
    this.upcomingCount = upcoming.length;
    this.pastCount = past.length;
    this.draftCount = drafts.length;

    // Get current tab events
    let tabEvents: EventWithStats[] = [];
    if (this.currentTab === 'upcoming') tabEvents = upcoming;
    else if (this.currentTab === 'past') tabEvents = past;
    else if (this.currentTab === 'drafts') tabEvents = drafts;

    // Apply search
    if (this.searchQuery.trim()) {
      tabEvents = tabEvents.filter(e =>
        e.title.toLowerCase().includes(this.searchQuery.toLowerCase())
      );
    }

    // Apply sort
    tabEvents = this.sortEvents(tabEvents);

    this.filteredEvents = tabEvents;
    this.updateStats();
  }

  private sortEvents(events: EventWithStats[]): EventWithStats[] {
    const sorted = [...events];
    switch (this.sortBy) {
      case 'registrations':
        return sorted.sort(
          (a, b) => (b.stats?.total_registrations || 0) - (a.stats?.total_registrations || 0)
        );
      case 'checkin':
        return sorted.sort((a, b) => (b.stats?.check_in_rate || 0) - (a.stats?.check_in_rate || 0));
      case 'capacity':
        return sorted.sort(
          (a, b) => (b.capacityPercent || 0) - (a.capacityPercent || 0)
        );
      case 'date':
      default:
        return sorted.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    }
  }

  private updateStats(): void {
    this.totalRegistrations = this.filteredEvents.reduce(
      (sum, e) => sum + (e.stats?.total_registrations || 0),
      0
    );
    const totalCheckins = this.filteredEvents.reduce(
      (sum, e) => sum + (e.stats?.checked_in || 0),
      0
    );
    this.totalCheckinRate = this.totalRegistrations > 0
      ? Math.round((totalCheckins / this.totalRegistrations) * 100)
      : 0;
    this.totalRevenue = this.filteredEvents.reduce((sum, e) => sum + (e.revenue || 0), 0);
  }

  private buildActivityFeed(): void {
    const feed: ActivityItem[] = [];
    this.events.forEach(e => {
      if (e.stats?.total_registrations) {
        feed.push({
          id: `reg-${e.id}`,
          message: `${e.stats.total_registrations} attendees registered for "${e.title}"`,
          timestamp: new Date(e.created_at),
          type: 'registration',
        });
      }
      if (e.status === 'published') {
        feed.push({
          id: `pub-${e.id}`,
          message: `"${e.title}" published and is live`,
          timestamp: new Date(e.created_at),
          type: 'approval',
        });
      }
    });
    this.activityFeed = feed.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
  }

  statusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      published: 'badge-published',
      pending: 'badge-pending',
      draft: 'badge-pending',
      rejected: 'badge-rejected',
      cancelled: 'badge-rejected',
      completed: 'badge-completed',
    };
    return map[status] ?? 'badge-pending';
  }

  statusTimeline(event: Event): string {
    const statusMap: Record<string, string> = {
      draft: 'Draft',
      pending: 'Pending approval',
      published: 'Published',
      completed: 'Completed',
      rejected: 'Rejected',
      cancelled: 'Cancelled',
    };
    return statusMap[event.status] ?? event.status;
  }

  get tabEmptyLabel(): string {
    const map = { upcoming: 'No upcoming events', past: 'No past events', drafts: 'No drafts' };
    return map[this.currentTab];
  }

  get tabEmptyMessage(): string {
    const map = {
      upcoming: 'Create your first event to get started.',
      past: 'Your completed events will appear here.',
      drafts: 'Save event drafts before publishing.',
    };
    return map[this.currentTab];
  }

  toggleMenu(eventId: number): void {
    this.openMenuId = this.openMenuId === eventId ? null : eventId;
  }

  duplicateEvent(id: number): void {
    const event = this.events.find(e => e.id === id);
    if (!event) return;
    this.toastService.success(`Event "${event.title}" duplicated (feature coming soon)`);
    this.openMenuId = null;
  }

  async deleteEvent(id: number): Promise<void> {
    const event = this.events.find(e => e.id === id);
    if (!event) return;
    const ok = await this.modalService.open({
      title: 'Delete Event',
      message: `Delete "${event.title}"? This cannot be undone.`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
      isDestructive: true,
    });
    if (!ok) return;
    this.eventService.deleteEvent(id).subscribe({
      next: () => {
        this.events = this.events.filter(e => e.id !== id);
        this.applyFilters();
        this.toastService.success('Event deleted.');
      },
      error: () => this.toastService.error('Failed to delete event.'),
    });
    this.openMenuId = null;
  }
}
