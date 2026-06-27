import { Component, HostListener, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Subscription } from 'rxjs';
import { LayoutService } from './layout.service';
import { AuthService } from '../services/auth.service';
import { NotificationService } from '../services/notification.service';
import { User } from '../models/models';
import {
  LucideAngularModule,
  Menu, Bell, ChevronRight,
} from 'lucide-angular';

interface Crumb { label: string; route?: string; }

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <header class="topbar">
      <div class="topbar-inner">

        <!-- Mobile: burger + logo -->
        <div class="flex items-center gap-3 md:hidden">
          <button
            (click)="layout.toggleMobile()"
            class="topbar-icon-btn focus-ring"
            aria-label="Open navigation"
          >
            <lucide-icon [img]="icons.Menu" class="w-5 h-5" aria-hidden="true"></lucide-icon>
          </button>
          <a routerLink="/" class="flex items-center gap-2 focus-ring rounded">
            <img src="assets/logo.png" alt="EventHub" class="w-6 h-6 rounded object-cover" />
            <span class="font-semibold text-foreground text-sm">EventHub</span>
          </a>
        </div>

        <!-- Desktop: breadcrumbs -->
        <nav class="hidden md:flex items-center gap-1 text-sm min-w-0" aria-label="Breadcrumb">
          @for (crumb of breadcrumbs; track $index; let last = $last) {
            @if (!last) {
              @if (crumb.route) {
                <a [routerLink]="crumb.route"
                  class="text-muted-foreground hover:text-foreground transition-colors truncate max-w-[180px] focus-ring rounded">
                  {{ crumb.label }}
                </a>
              } @else {
                <span class="text-muted-foreground truncate max-w-[180px]">{{ crumb.label }}</span>
              }
              <lucide-icon [img]="icons.ChevronRight" class="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" aria-hidden="true"></lucide-icon>
            } @else {
              <span class="font-medium text-foreground truncate max-w-[220px]">{{ crumb.label }}</span>
            }
          }
        </nav>

        <div class="topbar-spacer"></div>

        <!-- Right side: ⌘K stub + bell -->
        <div class="topbar-actions">

          <!-- ⌘K search stub (desktop only) -->
          <button
            class="hidden md:flex items-center gap-2 text-xs text-muted-foreground border border-border rounded-md px-2.5 py-1.5 hover:bg-muted transition-colors focus-ring"
            title="Quick search (coming soon)"
            aria-label="Quick search"
          >
            <span>Search</span>
            <kbd class="text-[10px] bg-muted px-1 rounded">⌘K</kbd>
          </button>

          <!-- Notification bell (authenticated only) -->
          @if (user) {
            <div class="relative">
              <button
                (click)="toggleNotif($event)"
                class="topbar-icon-btn focus-ring relative"
                [attr.aria-label]="'Notifications' + (notifService.unreadCount() > 0 ? ' (' + notifService.unreadCount() + ' unread)' : '')"
              >
                <lucide-icon [img]="icons.Bell" class="w-5 h-5" aria-hidden="true"></lucide-icon>
                @if (notifService.unreadCount() > 0) {
                  <span class="absolute -top-0.5 -right-0.5 w-[14px] h-[14px] bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center leading-none">
                    {{ notifService.unreadCount() > 9 ? '9+' : notifService.unreadCount() }}
                  </span>
                }
              </button>

              @if (notifOpen) {
                <div
                  class="topbar-notif-dropdown"
                  (click)="$event.stopPropagation()"
                >
                  <div class="flex items-center justify-between px-4 py-3 border-b border-border">
                    <span class="font-semibold text-foreground text-sm">Notifications</span>
                    @if (notifService.unreadCount() > 0) {
                      <button (click)="notifService.markRead(); notifOpen = false"
                        class="text-xs text-primary hover:underline">
                        Mark all read
                      </button>
                    }
                  </div>
                  <div class="max-h-80 overflow-y-auto divide-y divide-border">
                    @if (notifService.notifications().length === 0) {
                      <div class="px-4 py-8 text-center text-sm text-muted-foreground">No notifications</div>
                    }
                    @for (n of notifService.notifications(); track n.id) {
                      <div
                        class="px-4 py-3 text-sm cursor-pointer transition-colors"
                        [class]="n.is_read ? 'hover:bg-muted/50' : 'bg-primary/5 hover:bg-primary/10'"
                        (click)="notifService.markRead(n.id); notifOpen = false"
                      >
                        @if (n.title?.trim()) {
                          <p class="font-medium text-foreground leading-tight">{{ n.title }}</p>
                        }
                        @if (n.body?.trim()) {
                          <p class="text-muted-foreground mt-0.5 text-xs leading-relaxed">{{ n.body }}</p>
                        }
                        <p class="text-muted-foreground text-[10px] mt-1">{{ n.created_at | date:'MMM d, HH:mm' }}</p>
                      </div>
                    }
                  </div>
                </div>
              }
            </div>
          }
        </div>
      </div>
    </header>
  `,
  styles: [`:host { display: contents; }`],
})
export class TopbarComponent implements OnInit, OnDestroy {
  user: User | null = null;
  breadcrumbs: Crumb[] = [];
  notifOpen = false;
  private sub?: Subscription;

  readonly icons = { Menu, Bell, ChevronRight };

  constructor(
    public layout: LayoutService,
    private authService: AuthService,
    public notifService: NotificationService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.authService.currentUser$.subscribe(u => this.user = u);
    this.sub = this.router.events
      .pipe(filter(e => e instanceof NavigationEnd))
      .subscribe(e => this.buildBreadcrumbs((e as NavigationEnd).urlAfterRedirects));
    this.buildBreadcrumbs(this.router.url);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  @HostListener('document:click')
  onDocumentClick(): void { this.notifOpen = false; }

  @HostListener('document:keydown.escape')
  onEscape(): void { this.notifOpen = false; }

  toggleNotif(event: MouseEvent): void {
    event.stopPropagation();
    this.notifOpen = !this.notifOpen;
    if (this.notifOpen) this.notifService.load();
  }

  private buildBreadcrumbs(url: string): void {
    const ctx = this.layout.eventContext();
    const path = url.split('?')[0];

    if (ctx) {
      const section = this.eventSection(path);
      this.breadcrumbs = [
        { label: 'Dashboard', route: '/organizer/dashboard' },
        { label: ctx.title, route: `/organizer/events/${ctx.id}/attendees` },
        ...(section ? [{ label: section }] : []),
      ];
      return;
    }

    this.breadcrumbs = [{ label: this.pageLabel(path) }];
  }

  private pageLabel(path: string): string {
    if (path === '/' || path === '') return 'Discover';
    if (path.startsWith('/organizer/dashboard')) return 'Dashboard';
    if (path.startsWith('/my-events')) return 'My Events';
    if (path.startsWith('/my-registrations')) return 'My Tickets';
    if (path.startsWith('/my-bookings')) return 'My Bookings';
    if (path.startsWith('/admin/moderation')) return 'Moderation';
    if (path.startsWith('/create-event')) return 'Create Event';
    if (path.startsWith('/scan')) return 'Scan Tickets';
    if (path.startsWith('/profile')) return 'Profile';
    if (path.startsWith('/favorites')) return 'Favorites';
    if (path.startsWith('/validate')) return 'Validate Ticket';
    if (path.startsWith('/payment/success')) return 'Payment Success';
    if (path.startsWith('/payment/cancel')) return 'Payment Cancelled';
    if (path.startsWith('/events/')) return 'Event';
    return 'EventHub';
  }

  private eventSection(path: string): string | null {
    if (path.includes('/attendees')) return 'Attendees';
    if (path.includes('/analytics')) return 'Analytics';
    if (path.includes('/ticket-types')) return 'Tickets';
    if (path.includes('/promo-codes')) return 'Promo Codes';
    if (path.includes('/questions')) return 'Questions';
    if (path.includes('/checkin-lists')) return 'Check-in Lists';
    if (path.includes('/waitlist')) return 'Waitlist';
    if (path.includes('/settings')) return 'Settings';
    if (path.includes('/edit-event/')) return 'Edit Event';
    return null;
  }
}
