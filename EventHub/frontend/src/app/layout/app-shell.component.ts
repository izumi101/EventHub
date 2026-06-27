import { Component, OnInit, OnDestroy, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { Subscription } from 'rxjs';
import { SidebarComponent } from './sidebar.component';
import { TopbarComponent } from './topbar.component';
import { FooterComponent } from '../components/footer/footer.component';
import { LayoutService } from './layout.service';

const BARE_ROUTES = ['/login', '/register', '/forgot-password', '/payment/', '/booking/'];

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterOutlet, SidebarComponent, TopbarComponent, FooterComponent],
  // ONE router-outlet, always in the DOM — toggling two outlets caused post-login navigation failure
  template: `
    <!-- Mobile overlay (only in shell mode) -->
    @if (!isBare && layout.mobileOpen()) {
      <div class="sidebar-overlay" (click)="layout.closeMobile()" aria-hidden="true"></div>
    }

    <!-- Sidebar (hidden for bare routes: login/register/payment/…) -->
    @if (!isBare) {
      <app-sidebar></app-sidebar>
    }

    <!-- Right column — always present so the single router-outlet never moves -->
    <div
      class="shell-right"
      [class.shell-right-collapsed]="!isBare && layout.collapsed()"
      [class.shell-right-mobile]="!isBare && isMobileWidth"
      [class.shell-right-bare]="isBare"
    >
      @if (!isBare) {
        <app-topbar></app-topbar>
      }

      <main class="shell-main">
        <router-outlet />
      </main>

      @if (!isBare) {
        <app-footer></app-footer>
      }
    </div>
  `,
  styles: [`:host { display: contents; }`],
})
export class AppShellComponent implements OnInit, OnDestroy {
  isBare = false;
  isMobileWidth = false;
  private sub?: Subscription;

  constructor(public layout: LayoutService, private router: Router) {}

  ngOnInit(): void {
    this.checkWidth();
    this.sub = this.router.events
      .pipe(filter(e => e instanceof NavigationEnd))
      .subscribe(e => this.checkBare((e as NavigationEnd).urlAfterRedirects));
    this.checkBare(this.router.url);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  @HostListener('window:resize')
  checkWidth(): void {
    this.isMobileWidth = window.innerWidth < 640;
  }

  private checkBare(url: string): void {
    const path = url.split('?')[0];
    this.isBare = BARE_ROUTES.some(r => path === r || path.startsWith(r));
  }
}
