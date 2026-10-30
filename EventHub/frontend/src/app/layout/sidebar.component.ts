import { Component, HostListener, type Signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, isActive as isUrlActive } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { ThemeService } from '../services/theme.service';
import { ModalService } from '../services/modal.service';
import { LayoutService } from './layout.service';
import { NAV, NavSection, NavItem, Role, LucideIcon } from './nav.config';
import { User } from '../models/models';
import {
  LucideAngularModule,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  Moon,
  LogOut,
  User as UserIcon,
  ChevronDown,
  ChevronRight,
} from 'lucide-angular';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <aside
      class="sidebar"
      [class.sidebar-collapsed]="layout.collapsed()"
      [class.sidebar-mobile-open]="layout.mobileOpen()"
      aria-label="Main navigation"
    >
      <!-- Header: logo + collapse toggle -->
      <div class="sidebar-header">
        @if (!layout.collapsed()) {
          <a routerLink="/" class="sidebar-logo focus-ring rounded" (click)="layout.closeMobile()">
            <span class="ember-mark" aria-hidden="true"></span>
            <span class="font-display font-semibold text-foreground text-base tracking-tight"
              >EventHub</span
            >
          </a>
        } @else {
          <a
            routerLink="/"
            class="flex justify-center w-full focus-ring rounded"
            (click)="layout.closeMobile()"
          >
            <span class="ember-mark" aria-hidden="true"></span>
          </a>
        }
        <button
          (click)="layout.toggleCollapsed()"
          class="sidebar-collapse-btn focus-ring"
          [title]="layout.collapsed() ? 'Expand sidebar' : 'Collapse sidebar'"
          [attr.aria-expanded]="!layout.collapsed()"
          aria-label="Toggle sidebar"
        >
          <lucide-icon
            [img]="layout.collapsed() ? icons.PanelLeftOpen : icons.PanelLeftClose"
            class="w-4 h-4"
            aria-hidden="true"
          />
        </button>
      </div>

      <!-- Nav sections -->
      <nav class="sidebar-nav" role="navigation">
        @for (section of visibleSections(); track section.id) {
          <!-- Section header -->
          @if (section.title && !layout.collapsed()) {
            @if (section.collapsible) {
              <button
                class="sidebar-section-header"
                (click)="layout.toggleGroup(section.id)"
                [attr.aria-expanded]="layout.isGroupOpen(section.id)"
              >
                <span>{{
                  section.id === 'event-context'
                    ? layout.eventContext()?.title || 'Event'
                    : section.title
                }}</span>
                <lucide-icon
                  [img]="layout.isGroupOpen(section.id) ? icons.ChevronDown : icons.ChevronRight"
                  class="w-3.5 h-3.5 flex-shrink-0"
                  aria-hidden="true"
                />
              </button>
            } @else {
              <div class="sidebar-section-label">
                {{ section.title }}
              </div>
            }
          }

          <!-- Context event title in collapsed mode -->
          @if (section.id === 'event-context' && layout.collapsed()) {
            <div class="sidebar-divider"></div>
          }

          <!-- Items (hidden if group collapsed) -->
          @if (!section.collapsible || layout.isGroupOpen(section.id, section.defaultOpen)) {
            @for (item of visibleItems(section); track item.label) {
              <a
                [routerLink]="getRoute(item)"
                [title]="layout.collapsed() ? item.label : ''"
                class="sidebar-item focus-ring"
                [class.sidebar-item-active]="isActive(item)"
                (click)="layout.closeMobile()"
                [attr.aria-current]="isActive(item) ? 'page' : null"
              >
                <lucide-icon
                  [img]="asIcon(item.icon)"
                  class="sidebar-item-icon"
                  aria-hidden="true"
                />
                @if (!layout.collapsed()) {
                  <span class="sidebar-item-label">{{ item.label }}</span>
                }
              </a>
            }
          }

          <!-- Divider between sections -->
          <div class="sidebar-divider"></div>
        }
      </nav>

      <div class="sidebar-spacer"></div>

      <!-- Footer -->
      <div class="sidebar-footer">
        <!-- Theme toggle -->
        <button
          (click)="theme.toggle()"
          class="sidebar-item focus-ring"
          [title]="theme.isDark() ? 'Switch to light mode' : 'Switch to dark mode'"
          [attr.aria-label]="theme.isDark() ? 'Switch to light mode' : 'Switch to dark mode'"
        >
          <lucide-icon
            [img]="theme.isDark() ? icons.Sun : icons.Moon"
            class="sidebar-item-icon"
            aria-hidden="true"
          />
          @if (!layout.collapsed()) {
            <span class="sidebar-item-label">{{
              theme.isDark() ? 'Light mode' : 'Dark mode'
            }}</span>
          }
        </button>

        <!-- Profile / auth buttons -->
        @if (user) {
          <div class="relative">
            <button
              (click)="profileOpen = !profileOpen; $event.stopPropagation()"
              class="sidebar-item focus-ring w-full"
              [title]="layout.collapsed() ? user.username : ''"
            >
              <span class="sidebar-avatar flex-shrink-0">{{
                user.username.charAt(0).toUpperCase()
              }}</span>
              @if (!layout.collapsed()) {
                <span class="sidebar-item-label truncate min-w-0">{{ user.username }}</span>
                <lucide-icon
                  [img]="icons.ChevronDown"
                  class="w-3.5 h-3.5 flex-shrink-0 ml-auto text-muted-foreground"
                  aria-hidden="true"
                />
              }
            </button>

            @if (profileOpen) {
              <!-- Clicks inside the menu must not reach the document listener that closes it. -->
              <div class="profile-dropdown" role="presentation" (click)="$event.stopPropagation()">
                <a
                  routerLink="/profile"
                  (click)="profileOpen = false; layout.closeMobile()"
                  class="profile-dropdown-item focus-ring"
                >
                  <lucide-icon [img]="icons.UserIcon" class="w-4 h-4" aria-hidden="true" />
                  Profile
                </a>
                <button
                  (click)="logout()"
                  class="profile-dropdown-item profile-dropdown-item-danger focus-ring w-full text-left"
                >
                  <lucide-icon [img]="icons.LogOut" class="w-4 h-4" aria-hidden="true" />
                  Sign Out
                </button>
              </div>
            }
          </div>
        } @else {
          @if (!layout.collapsed()) {
            <a
              routerLink="/login"
              (click)="layout.closeMobile()"
              class="sidebar-item focus-ring text-primary"
            >
              <lucide-icon [img]="icons.UserIcon" class="sidebar-item-icon" aria-hidden="true" />
              <span class="sidebar-item-label">Sign In</span>
            </a>
          }
        }
      </div>
    </aside>
  `,
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class SidebarComponent {
  layout = inject(LayoutService);
  theme = inject(ThemeService);
  private authService = inject(AuthService);
  private modalService = inject(ModalService);
  private router = inject(Router);

  user: User | null = null;
  isOrganizer = false;
  isAdmin = false;
  isAttendee = false;
  profileOpen = false;

  /** One router-backed signal per nav target, created on first use. */
  private readonly activeRoutes = new Map<string, Signal<boolean>>();

  readonly icons = {
    PanelLeftClose,
    PanelLeftOpen,
    Sun,
    Moon,
    LogOut,
    UserIcon,
    ChevronDown,
    ChevronRight,
  };

  constructor() {
    this.authService.currentUser$.subscribe((user) => {
      this.user = user;
      // Self-registered organizers carry profile.role === 'organizer';
      // staff/superuser flags come from Django admin.
      this.isOrganizer = user?.is_staff || user?.is_superuser || user?.profile.role === 'organizer';
      this.isAdmin = !!user?.is_superuser;
      this.isAttendee = !!user && !this.isOrganizer;
    });
  }

  @HostListener('document:click')
  onDocumentClick(): void {
    this.profileOpen = false;
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.profileOpen = false;
    if (this.layout.mobileOpen()) this.layout.closeMobile();
  }

  /** Returns the effective roles the current user has. */
  private get userRoles(): Set<Role> {
    const roles = new Set<Role>(['public'] as Role[]);
    if (this.user) {
      roles.add('auth');
      if (this.isAttendee) roles.add('attendee');
      if (this.isOrganizer) roles.add('organizer');
      if (this.isAdmin) roles.add('admin');
    }
    return roles;
  }

  private hasRole(required: Role[]): boolean {
    const ur = this.userRoles;
    return required.some((r) => ur.has(r));
  }

  visibleSections(): NavSection[] {
    return NAV.filter((section) => {
      if (!this.hasRole(section.roles)) return false;
      if (section.context === 'event' && !this.layout.eventContext()) return false;
      return true;
    });
  }

  visibleItems(section: NavSection): NavItem[] {
    return section.items.filter((item) => this.hasRole(item.roles));
  }

  getRoute(item: NavItem): string | null {
    if (item.routeFn) {
      const ctx = this.layout.eventContext();
      return ctx ? item.routeFn(ctx.id) : null;
    }
    return item.route ?? null;
  }

  isActive(item: NavItem): boolean {
    const route = this.getRoute(item);
    if (!route) return false;
    const exact = item.exact ?? !!item.routeFn;
    const key = `${exact ? 'exact' : 'subset'}:${route}`;
    let active = this.activeRoutes.get(key);
    if (!active) {
      active = isUrlActive(route, this.router, {
        paths: exact ? 'exact' : 'subset',
        queryParams: 'ignored',
        fragment: 'ignored',
        matrixParams: 'ignored',
      });
      this.activeRoutes.set(key, active);
    }
    return active();
  }

  // Cast helper so template bindings satisfy Angular strict template checks
  asIcon(icon: LucideIcon): LucideIcon {
    return icon;
  }

  async logout(): Promise<void> {
    this.profileOpen = false;
    const confirmed = await this.modalService.open({
      title: 'Sign Out',
      message: 'Are you sure you want to sign out of EventHub?',
      confirmText: 'Sign Out',
      cancelText: 'Cancel',
      isDestructive: true,
    });
    if (confirmed) {
      this.authService.logout();
      void this.router.navigate(['/login']);
    }
  }
}
