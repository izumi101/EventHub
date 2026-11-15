import { Component, OnInit, OnDestroy, HostListener, inject } from '@angular/core';
import { RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Subscription } from 'rxjs';
import { TranslocoPipe } from '@jsverse/transloco';
import { SidebarComponent } from './sidebar.component';
import { TopbarComponent } from './topbar.component';
import { TopNavComponent } from './top-nav.component';
import { TabBarComponent } from './tab-bar.component';
import { FooterComponent } from '../components/footer/footer.component';
import { LayoutService } from './layout.service';
import { ViewportScroller } from '@angular/common';

export type ShellLayout = 'bare' | 'workspace' | 'consumer';

const BARE_ROUTES = ['/login', '/register', '/forgot-password', '/payment/', '/booking/'];
/** Organizer / admin tools keep the sidebar + topbar workspace. */
const WORKSPACE_ROUTES = [
  '/organizer/',
  '/my-events',
  '/create-event',
  '/edit-event/',
  '/scan',
  '/validate/',
  '/admin/',
];
/** The event page puts its purchase bar where the tab bar would be (phase 4). */
const NO_TAB_BAR = /^\/events\/[^/]+$/;

export function shellLayout(url: string): ShellLayout {
  const path = url.split(/[?#]/)[0];
  const matches = (r: string) => path === r || path.startsWith(r);
  if (BARE_ROUTES.some(matches)) return 'bare';
  if (WORKSPACE_ROUTES.some((r) => matches(r) || path === r.replace(/\/$/, ''))) {
    return 'workspace';
  }
  return 'consumer';
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    RouterOutlet,
    TranslocoPipe,
    SidebarComponent,
    TopbarComponent,
    TopNavComponent,
    TabBarComponent,
    FooterComponent,
  ],
  // ONE router-outlet, always in the DOM — toggling two outlets caused post-login navigation failure
  template: `
    <a href="#main-content" class="skip-link" (click)="skipToContent($event)">{{
      'nav.skipToContent' | transloco
    }}</a>

    @if (layout === 'workspace') {
      @if (ui.mobileOpen()) {
        <div class="sidebar-overlay" (click)="ui.closeMobile()" aria-hidden="true"></div>
      }
      <app-sidebar />
    }

    <!-- Right column — always present so the single router-outlet never moves -->
    <div
      class="shell-right"
      [class.shell-right-collapsed]="layout === 'workspace' && ui.collapsed()"
      [class.shell-right-mobile]="layout === 'workspace' && isMobileWidth"
      [class.shell-right-bare]="layout !== 'workspace'"
      [class.shell-right-tabbar]="showTabBar"
    >
      @if (layout === 'consumer') {
        <app-top-nav />
      } @else if (layout === 'workspace') {
        <app-topbar />
      }

      <main id="main-content" class="shell-main" tabindex="-1">
        <router-outlet />
      </main>

      @if (layout !== 'bare') {
        <app-footer />
      }
    </div>

    @if (showTabBar) {
      <app-tab-bar />
    }
  `,
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class AppShellComponent implements OnInit, OnDestroy {
  ui = inject(LayoutService);

  constructor() {
    // Anchor jumps land below the sticky 64px header, not under it.
    inject(ViewportScroller).setOffset([0, 80]);
  }
  private router = inject(Router);

  layout: ShellLayout = 'consumer';
  showTabBar = false;
  isMobileWidth = false;
  private sub?: Subscription;

  ngOnInit(): void {
    this.checkWidth();
    this.sub = this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe((e) => this.applyUrl(e.urlAfterRedirects));
    this.applyUrl(this.router.url);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  @HostListener('window:resize')
  checkWidth(): void {
    this.isMobileWidth = window.innerWidth < 640;
  }

  /** In-page jump; a plain #hash href would resolve against <base href="/">. */
  skipToContent(event: Event): void {
    event.preventDefault();
    document.getElementById('main-content')?.focus();
  }

  private applyUrl(url: string): void {
    this.layout = shellLayout(url);
    const path = url.split(/[?#]/)[0];
    this.showTabBar = this.layout === 'consumer' && !NO_TAB_BAR.test(path);
  }
}
