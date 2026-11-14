import { Component, HostListener, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Subscription } from 'rxjs';
import { LayoutService } from './layout.service';
import { AuthService } from '../services/auth.service';
import { NotificationService } from '../services/notification.service';
import { User } from '../models/models';
import { LucideAngularModule, Menu, Bell, ChevronRight } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageSwitcherComponent } from '../i18n/language-switcher.component';
import { LocalDatePipe } from '../i18n/locale.pipes';

interface Crumb {
  /** Event titles are data, everything else is a translation key. */
  label?: string;
  labelKey?: string;
  route?: string;
}

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LanguageSwitcherComponent,
    LocalDatePipe,
  ],
  template: `
    <header class="topbar">
      <div class="topbar-inner">
        <!-- Mobile: burger + logo -->
        <div class="flex items-center gap-3 md:hidden">
          <button
            (click)="layout.toggleMobile()"
            class="topbar-icon-btn focus-ring"
            [attr.aria-label]="'nav.openNavigation' | transloco"
          >
            <lucide-icon [img]="icons.Menu" class="w-5 h-5" aria-hidden="true" />
          </button>
          <a routerLink="/" class="flex items-center gap-2 focus-ring rounded">
            <img src="assets/logo.png" alt="EventHub" class="w-6 h-6 rounded object-cover" />
            <span class="font-semibold text-foreground text-sm">EventHub</span>
          </a>
        </div>

        <!-- Desktop: breadcrumbs -->
        <nav
          class="hidden md:flex items-center gap-1 text-sm min-w-0"
          [attr.aria-label]="'nav.breadcrumb' | transloco"
        >
          @for (crumb of breadcrumbs; track $index) {
            @if (!$last) {
              @if (crumb.route) {
                <a
                  [routerLink]="crumb.route"
                  class="text-muted-foreground hover:text-foreground transition-colors truncate max-w-[180px] focus-ring rounded"
                >
                  {{ crumb.labelKey ? (crumb.labelKey | transloco) : crumb.label }}
                </a>
              } @else {
                <span class="text-muted-foreground truncate max-w-[180px]">{{
                  crumb.labelKey ? (crumb.labelKey | transloco) : crumb.label
                }}</span>
              }
              <lucide-icon
                [img]="icons.ChevronRight"
                class="w-3.5 h-3.5 text-muted-foreground flex-shrink-0"
                aria-hidden="true"
              />
            } @else {
              <span class="font-medium text-foreground truncate max-w-[220px]">{{
                crumb.labelKey ? (crumb.labelKey | transloco) : crumb.label
              }}</span>
            }
          }
        </nav>

        <div class="topbar-spacer"></div>

        <!-- Right side: ⌘K stub + bell -->
        <div class="topbar-actions">
          <app-language-switcher />

          <!-- ⌘K search stub (desktop only) -->
          <button
            class="hidden md:flex items-center gap-2 text-xs text-muted-foreground border border-border rounded-md px-2.5 py-1.5 hover:bg-muted transition-colors focus-ring"
            [title]="'nav.quickSearchSoon' | transloco"
            [attr.aria-label]="'nav.quickSearch' | transloco"
          >
            <span>{{ 'nav.search' | transloco }}</span>
            <kbd class="text-[10px] bg-muted px-1 rounded">⌘K</kbd>
          </button>

          <!-- Notification bell (authenticated only) -->
          @if (user) {
            <div class="relative">
              <button
                (click)="toggleNotif($event)"
                class="topbar-icon-btn focus-ring relative"
                [attr.aria-label]="
                  notifService.unreadCount() > 0
                    ? ('nav.notificationsUnread' | transloco: { count: notifService.unreadCount() })
                    : ('nav.notifications' | transloco)
                "
              >
                <lucide-icon [img]="icons.Bell" class="w-5 h-5" aria-hidden="true" />
                @if (notifService.unreadCount() > 0) {
                  <span
                    class="absolute -top-0.5 -right-0.5 w-[14px] h-[14px] bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center leading-none"
                  >
                    {{ notifService.unreadCount() > 9 ? '9+' : notifService.unreadCount() }}
                  </span>
                }
              </button>

              @if (notifOpen) {
                <!-- Clicks inside the panel must not reach the document listener that closes it. -->
                <div
                  class="topbar-notif-dropdown"
                  role="presentation"
                  (click)="$event.stopPropagation()"
                >
                  <div class="flex items-center justify-between px-4 py-3 border-b border-border">
                    <span class="font-semibold text-foreground text-sm">{{
                      'nav.notifications' | transloco
                    }}</span>
                    @if (notifService.unreadCount() > 0) {
                      <button
                        (click)="notifService.markRead(); notifOpen = false"
                        class="text-xs text-primary hover:underline"
                      >
                        {{ 'nav.markAllRead' | transloco }}
                      </button>
                    }
                  </div>
                  <div class="max-h-80 overflow-y-auto divide-y divide-border">
                    @if (notifService.notifications().length === 0) {
                      <div class="px-4 py-8 text-center text-sm text-muted-foreground">
                        {{ 'nav.noNotifications' | transloco }}
                      </div>
                    }
                    @for (n of notifService.notifications(); track n.id) {
                      <button
                        type="button"
                        class="block w-full text-left px-4 py-3 text-sm cursor-pointer transition-colors"
                        [class]="
                          n.is_read ? 'hover:bg-muted/50' : 'bg-primary/5 hover:bg-primary/10'
                        "
                        (click)="notifService.markRead(n.id); notifOpen = false"
                      >
                        @if (n.title.trim()) {
                          <span class="block font-medium text-foreground leading-tight">{{
                            n.title
                          }}</span>
                        }
                        @if (n.body.trim()) {
                          <span class="block text-muted-foreground mt-0.5 text-xs leading-relaxed">
                            {{ n.body }}
                          </span>
                        }
                        <span class="block text-muted-foreground text-[10px] mt-1">
                          {{ n.created_at | localDate: 'MMM d, HH:mm' }}
                        </span>
                      </button>
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
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class TopbarComponent implements OnInit, OnDestroy {
  layout = inject(LayoutService);
  private authService = inject(AuthService);
  notifService = inject(NotificationService);
  private router = inject(Router);

  user: User | null = null;
  breadcrumbs: Crumb[] = [];
  notifOpen = false;
  private sub?: Subscription;

  readonly icons = { Menu, Bell, ChevronRight };

  ngOnInit(): void {
    this.authService.currentUser$.subscribe((u) => (this.user = u));
    this.sub = this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe((e) => this.buildBreadcrumbs(e.urlAfterRedirects));
    this.buildBreadcrumbs(this.router.url);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.notifOpen = false;
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.notifOpen = false;
  }

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
        { labelKey: 'nav.dashboard', route: '/organizer/dashboard' },
        { label: ctx.title, route: `/organizer/events/${ctx.id}/attendees` },
        ...(section ? [{ labelKey: section }] : []),
      ];
      return;
    }

    this.breadcrumbs = [{ labelKey: this.pageLabel(path) }];
  }

  private pageLabel(path: string): string {
    if (path === '/' || path === '') return 'nav.discover';
    if (path.startsWith('/organizer/dashboard')) return 'nav.dashboard';
    if (path.startsWith('/my-events')) return 'nav.myEvents';
    if (path.startsWith('/my-registrations')) return 'nav.myTickets';
    if (path.startsWith('/my-bookings')) return 'nav.myBookings';
    if (path.startsWith('/admin/moderation')) return 'nav.moderation';
    if (path.startsWith('/create-event')) return 'nav.createEvent';
    if (path.startsWith('/scan')) return 'nav.scanTickets';
    if (path.startsWith('/profile')) return 'nav.profile';
    if (path.startsWith('/favorites')) return 'nav.favorites';
    if (path.startsWith('/validate')) return 'nav.validateTicket';
    if (path.startsWith('/payment/success')) return 'nav.paymentSuccess';
    if (path.startsWith('/payment/cancel')) return 'nav.paymentCancelled';
    if (path.startsWith('/events/')) return 'nav.event';
    return 'nav.brand';
  }

  private eventSection(path: string): string | null {
    if (path.includes('/attendees')) return 'nav.attendees';
    if (path.includes('/analytics')) return 'nav.analytics';
    if (path.includes('/ticket-types')) return 'nav.tickets';
    if (path.includes('/promo-codes')) return 'nav.promoCodes';
    if (path.includes('/questions')) return 'nav.questions';
    if (path.includes('/checkin-lists')) return 'nav.checkinLists';
    if (path.includes('/waitlist')) return 'nav.waitlist';
    if (path.includes('/settings')) return 'nav.settings';
    if (path.includes('/edit-event/')) return 'nav.editEvent';
    return null;
  }
}
