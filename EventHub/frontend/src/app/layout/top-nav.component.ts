import { Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { IsActiveMatchOptions, NavigationEnd, Router, RouterModule } from '@angular/router';
import { Subscription, filter } from 'rxjs';
import { LucideAngularModule, LogIn, LogOut, Menu, Moon, Search, Sun, X } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { AuthService } from '../services/auth.service';
import { ThemeService } from '../services/theme.service';
import { LayoutService } from './layout.service';
import { DialogDirective } from '../directives/dialog.directive';
import { LanguageSwitcherComponent } from '../i18n/language-switcher.component';
import { NotificationBellComponent } from './notification-bell.component';
import { AccountMenuComponent } from './account-menu.component';
import { NavLink, SignOutService, accountLinks, primaryLinks } from './account-links';

/** id of the Discover search field that the nav search button focuses. */
export const DISCOVER_SEARCH_ID = 'discover-search';

const EXACT: IsActiveMatchOptions = {
  paths: 'exact',
  queryParams: 'ignored',
  fragment: 'ignored',
  matrixParams: 'ignored',
};
const SUBSET: IsActiveMatchOptions = { ...EXACT, paths: 'subset' };

/**
 * Consumer header (Concept A): logo, Discover / My Tickets / Favorites,
 * language, search, bell and the account menu. Below 768px it collapses to
 * logo + bell + a menu button that opens a sheet; the bottom tab bar
 * (app-tab-bar) carries the main destinations there.
 */
@Component({
  selector: 'app-top-nav',
  standalone: true,
  imports: [
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    DialogDirective,
    LanguageSwitcherComponent,
    NotificationBellComponent,
    AccountMenuComponent,
  ],
  template: `
    <header class="top-nav" [class.top-nav-transparent]="ui.navOverHero() && !menuOpen()">
      <div class="container top-nav-inner">
        <a routerLink="/" class="top-nav-brand focus-ring" aria-label="EventHub">
          <img src="assets/brand/symbol.svg?v=2" alt="" aria-hidden="true" class="w-8 h-8" />
          <span class="font-display text-foreground text-lg tracking-tight" aria-hidden="true"
            >Event<span class="font-bold">Hub</span></span
          >
        </a>

        <nav
          class="hidden md:flex items-center gap-1 ml-6"
          [attr.aria-label]="'nav.mainNavigation' | transloco"
        >
          @for (link of links(); track link.route) {
            <a
              [routerLink]="link.route"
              routerLinkActive="top-nav-link-active"
              [routerLinkActiveOptions]="link.exact ? exact : subset"
              ariaCurrentWhenActive="page"
              class="top-nav-link focus-ring"
              >{{ link.labelKey | transloco }}</a
            >
          }
        </nav>

        <div class="flex-1"></div>

        <!-- Desktop actions -->
        <div class="hidden md:flex items-center gap-2">
          <app-language-switcher />
          <button
            type="button"
            class="nav-icon-btn focus-ring"
            (click)="focusSearch()"
            [attr.aria-label]="'nav.searchEvents' | transloco"
            [title]="('nav.searchEvents' | transloco) + ' (⌘K)'"
          >
            <lucide-icon [img]="icons.Search" class="w-[18px] h-[18px]" aria-hidden="true" />
          </button>
          @if (user()) {
            <app-notification-bell />
          }
          <app-account-menu />
        </div>

        <!-- Mobile actions -->
        <div class="flex md:hidden items-center gap-1.5">
          @if (user()) {
            <app-notification-bell />
          }
          <button
            type="button"
            class="nav-icon-btn focus-ring"
            [attr.aria-expanded]="menuOpen()"
            [attr.aria-label]="'nav.openMenu' | transloco"
            (click)="menuOpen.set(true)"
          >
            <lucide-icon [img]="icons.Menu" class="w-5 h-5" aria-hidden="true" />
          </button>
        </div>
      </div>
    </header>

    @if (menuOpen()) {
      <div class="fixed inset-0 z-50 bg-black/50 md:hidden animate-fade-in">
        <div class="mobile-sheet" appDialog dismissOnBackdrop (dismiss)="closeMenu()">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold text-foreground">{{ 'nav.menu' | transloco }}</h2>
            <button
              type="button"
              class="nav-icon-btn focus-ring"
              [attr.aria-label]="'nav.closeMenu' | transloco"
              (click)="closeMenu()"
            >
              <lucide-icon [img]="icons.X" class="w-5 h-5" aria-hidden="true" />
            </button>
          </div>

          <app-language-switcher />

          <nav class="mt-4" [attr.aria-label]="'nav.mainNavigation' | transloco">
            <ul class="space-y-0.5">
              @for (link of links(); track link.route) {
                <li>
                  <a
                    [routerLink]="link.route"
                    routerLinkActive="sheet-item-active"
                    [routerLinkActiveOptions]="link.exact ? exact : subset"
                    ariaCurrentWhenActive="page"
                    class="sheet-item focus-ring"
                    (click)="closeMenu()"
                  >
                    <lucide-icon [img]="link.icon" class="w-5 h-5" aria-hidden="true" />
                    {{ link.labelKey | transloco }}
                  </a>
                </li>
              }
            </ul>
          </nav>

          @if (user(); as u) {
            <p class="kicker mt-5 mb-1.5 px-3">{{ u.username }}</p>
            <ul class="space-y-0.5">
              @for (link of accountLinks(); track link.route) {
                <li>
                  <a
                    [routerLink]="link.route"
                    routerLinkActive="sheet-item-active"
                    class="sheet-item focus-ring"
                    (click)="closeMenu()"
                  >
                    <lucide-icon [img]="link.icon" class="w-5 h-5" aria-hidden="true" />
                    {{ link.labelKey | transloco }}
                  </a>
                </li>
              }
            </ul>
          }

          <div class="mt-4 pt-4 border-t border-border space-y-0.5">
            <button type="button" class="sheet-item focus-ring" (click)="theme.toggle()">
              <lucide-icon
                [img]="theme.isDark() ? icons.Sun : icons.Moon"
                class="w-5 h-5"
                aria-hidden="true"
              />
              {{ (theme.isDark() ? 'nav.lightMode' : 'nav.darkMode') | transloco }}
            </button>
            @if (user()) {
              <button
                type="button"
                class="sheet-item sheet-item-danger focus-ring"
                (click)="signOut()"
              >
                <lucide-icon [img]="icons.LogOut" class="w-5 h-5" aria-hidden="true" />
                {{ 'nav.signOut' | transloco }}
              </button>
            } @else {
              <a routerLink="/login" class="sheet-item focus-ring" (click)="closeMenu()">
                <lucide-icon [img]="icons.LogIn" class="w-5 h-5" aria-hidden="true" />
                {{ 'nav.signIn' | transloco }}
              </a>
            }
          </div>
        </div>
      </div>
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
export class TopNavComponent implements OnDestroy {
  readonly theme = inject(ThemeService);
  readonly ui = inject(LayoutService);
  private auth = inject(AuthService);
  private router = inject(Router);
  private signOutService = inject(SignOutService);

  readonly user = toSignal(this.auth.currentUser$, { initialValue: this.auth.currentUser });
  readonly links = computed<NavLink[]>(() => primaryLinks(this.user() ?? null));
  readonly accountLinks = computed<NavLink[]>(() => {
    const u = this.user();
    return u ? accountLinks(u) : [];
  });
  readonly menuOpen = signal(false);

  readonly exact = EXACT;
  readonly subset = SUBSET;
  readonly icons = { LogIn, LogOut, Menu, Moon, Search, Sun, X };

  private navSub: Subscription = this.router.events
    .pipe(filter((e) => e instanceof NavigationEnd))
    .subscribe(() => this.menuOpen.set(false));

  ngOnDestroy(): void {
    this.navSub.unsubscribe();
  }

  /** ⌘K / Ctrl+K jumps to the Discover search, like the search button. */
  @HostListener('document:keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.focusSearch();
    }
  }

  /** Focus the Discover search field, going to Discover first when elsewhere. */
  focusSearch(): void {
    const focus = () => document.getElementById(DISCOVER_SEARCH_ID)?.focus();
    if (this.router.url.split(/[?#]/)[0] === '/') {
      focus();
    } else {
      void this.router.navigate(['/']).then(() => setTimeout(focus));
    }
  }

  closeMenu(): void {
    this.menuOpen.set(false);
  }

  async signOut(): Promise<void> {
    this.menuOpen.set(false);
    await this.signOutService.confirmAndSignOut();
  }
}
