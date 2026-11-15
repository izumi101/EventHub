import { Component, HostListener, type Signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router, isActive as isUrlActive } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { LayoutService } from './layout.service';
import { NAV, NavSection, NavItem, Role, LucideIcon } from './nav.config';
import { User } from '../models/models';
import { isAdmin, isOrganizer } from '../utils/roles';
import {
  LucideAngularModule,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronDown,
  ChevronRight,
} from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';

/**
 * Sidebar of the organizer/admin workspace only. Consumer pages use the top
 * nav; profile, theme and sign-out live in the account menu of the topbar.
 */
@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule, TranslocoPipe],
  template: `
    <aside
      class="sidebar"
      [class.sidebar-collapsed]="layout.collapsed()"
      [class.sidebar-mobile-open]="layout.mobileOpen()"
      [attr.aria-label]="'nav.workspaceNavigation' | transloco"
    >
      <!-- Header: logo + collapse toggle -->
      <div class="sidebar-header">
        @if (!layout.collapsed()) {
          <a routerLink="/" class="sidebar-logo focus-ring rounded" (click)="layout.closeMobile()">
            <span class="ember-mark" aria-hidden="true"></span>
            <span class="font-display text-foreground text-base tracking-tight"
              >Event<span class="font-bold">Hub</span></span
            >
          </a>
        } @else {
          <a
            routerLink="/"
            class="flex justify-center w-full focus-ring rounded"
            [attr.aria-label]="'nav.backToDiscover' | transloco"
            (click)="layout.closeMobile()"
          >
            <span class="ember-mark" aria-hidden="true"></span>
          </a>
        }
        <button
          (click)="layout.toggleCollapsed()"
          class="sidebar-collapse-btn focus-ring"
          [title]="(layout.collapsed() ? 'nav.expandSidebar' : 'nav.collapseSidebar') | transloco"
          [attr.aria-expanded]="!layout.collapsed()"
          [attr.aria-label]="'nav.toggleSidebar' | transloco"
        >
          <lucide-icon
            [img]="layout.collapsed() ? icons.PanelLeftOpen : icons.PanelLeftClose"
            class="w-4 h-4"
            aria-hidden="true"
          />
        </button>
      </div>

      <!-- Nav sections -->
      <nav class="sidebar-nav">
        @for (section of visibleSections(); track section.id) {
          <!-- Section header -->
          @if (section.titleKey && !layout.collapsed()) {
            @if (section.collapsible) {
              <button
                class="sidebar-section-header"
                (click)="layout.toggleGroup(section.id)"
                [attr.aria-expanded]="layout.isGroupOpen(section.id)"
              >
                <span>{{
                  section.id === 'event-context'
                    ? layout.eventContext()?.title || ('nav.event' | transloco)
                    : (section.titleKey | transloco)
                }}</span>
                <lucide-icon
                  [img]="layout.isGroupOpen(section.id) ? icons.ChevronDown : icons.ChevronRight"
                  class="w-3.5 h-3.5 flex-shrink-0"
                  aria-hidden="true"
                />
              </button>
            } @else {
              <div class="sidebar-section-label">
                {{ section.titleKey | transloco }}
              </div>
            }
          }

          <!-- Context event title in collapsed mode -->
          @if (section.id === 'event-context' && layout.collapsed()) {
            <div class="sidebar-divider"></div>
          }

          <!-- Items (hidden if group collapsed) -->
          @if (!section.collapsible || layout.isGroupOpen(section.id, section.defaultOpen)) {
            @for (item of visibleItems(section); track item.labelKey) {
              <a
                [routerLink]="getRoute(item)"
                [title]="layout.collapsed() ? (item.labelKey | transloco) : ''"
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
                  <span class="sidebar-item-label">{{ item.labelKey | transloco }}</span>
                }
              </a>
            }
          }

          <!-- Divider between sections -->
          <div class="sidebar-divider"></div>
        }
      </nav>

      <div class="sidebar-spacer"></div>
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
  private authService = inject(AuthService);
  private router = inject(Router);

  user: User | null = null;
  isOrganizer = false;
  isAdmin = false;
  isAttendee = false;

  /** One router-backed signal per nav target, created on first use. */
  private readonly activeRoutes = new Map<string, Signal<boolean>>();

  readonly icons = { PanelLeftClose, PanelLeftOpen, ChevronDown, ChevronRight };

  constructor() {
    this.authService.currentUser$.subscribe((user) => {
      this.user = user;
      this.isOrganizer = isOrganizer(user);
      this.isAdmin = isAdmin(user);
      this.isAttendee = !!user && !this.isOrganizer;
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
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
}
