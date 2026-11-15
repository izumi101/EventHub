import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Subscription } from 'rxjs';
import { LayoutService } from './layout.service';
import { AuthService } from '../services/auth.service';
import { User } from '../models/models';
import { LucideAngularModule, Menu, ChevronRight } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageSwitcherComponent } from '../i18n/language-switcher.component';
import { NotificationBellComponent } from './notification-bell.component';
import { AccountMenuComponent } from './account-menu.component';

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
    NotificationBellComponent,
    AccountMenuComponent,
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
            <img src="assets/brand/symbol.svg?v=2" alt="" aria-hidden="true" class="w-7 h-7" />
            <span class="font-display text-foreground text-sm tracking-tight"
              >Event<span class="font-bold">Hub</span></span
            >
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

        <!-- Right side: language, bell, account menu -->
        <div class="topbar-actions">
          <div class="hidden sm:block"><app-language-switcher /></div>
          @if (user) {
            <app-notification-bell />
          }
          <app-account-menu [compact]="true" />
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
  private router = inject(Router);

  user: User | null = null;
  breadcrumbs: Crumb[] = [];
  private sub?: Subscription;

  readonly icons = { Menu, ChevronRight };

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
