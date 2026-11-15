import {
  Component,
  ElementRef,
  HostListener,
  Input,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, ChevronDown, LogOut, Moon, Sun } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { AuthService } from '../services/auth.service';
import { ThemeService } from '../services/theme.service';
import { SignOutService, accountLinks } from './account-links';

let nextId = 0;

/**
 * Avatar button + account menu (disclosure pattern: a button with
 * aria-expanded that shows a list of links and buttons). Used by the consumer
 * top nav and the workspace topbar. Guests get a theme toggle and "Sign in".
 *
 * The trigger's accessible name contains the username, and "Sign Out" is a
 * plain button — the e2e sign-out helper relies on both.
 */
@Component({
  selector: 'app-account-menu',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe],
  template: `
    @if (user(); as u) {
      <div class="relative">
        <button
          #trigger
          type="button"
          class="account-trigger focus-ring"
          [class.account-trigger-compact]="compact"
          aria-haspopup="true"
          [attr.aria-expanded]="open()"
          [attr.aria-controls]="panelId"
          [attr.aria-label]="'nav.accountMenu' | transloco: { name: u.username }"
          (click)="toggle($event)"
          (keydown.arrowDown)="openFromKeyboard($event)"
        >
          <span class="account-avatar" aria-hidden="true">{{ initial() }}</span>
          @if (!compact) {
            <span class="account-name">{{ u.username }}</span>
          }
          <lucide-icon
            [img]="icons.ChevronDown"
            class="w-4 h-4 text-muted-foreground flex-shrink-0"
            aria-hidden="true"
          />
        </button>

        @if (open()) {
          <div
            #panel
            [id]="panelId"
            class="account-panel"
            role="presentation"
            (click)="$event.stopPropagation()"
            (keydown)="onPanelKey($event)"
          >
            <div class="px-3.5 py-3 border-b border-border">
              <p class="text-sm font-semibold text-foreground truncate">{{ u.username }}</p>
              @if (u.email) {
                <p class="text-xs text-muted-foreground truncate">{{ u.email }}</p>
              }
            </div>
            <ul class="py-1">
              @for (link of links(); track link.route) {
                <li>
                  <a
                    [routerLink]="link.route"
                    class="account-item focus-ring"
                    (click)="close(false)"
                  >
                    <lucide-icon [img]="link.icon" class="w-4 h-4" aria-hidden="true" />
                    {{ link.labelKey | transloco }}
                  </a>
                </li>
              }
            </ul>
            <div class="border-t border-border py-1">
              <button type="button" class="account-item focus-ring" (click)="theme.toggle()">
                <lucide-icon
                  [img]="theme.isDark() ? icons.Sun : icons.Moon"
                  class="w-4 h-4"
                  aria-hidden="true"
                />
                {{ (theme.isDark() ? 'nav.lightMode' : 'nav.darkMode') | transloco }}
              </button>
              <button
                type="button"
                class="account-item account-item-danger focus-ring"
                (click)="signOut()"
              >
                <lucide-icon [img]="icons.LogOut" class="w-4 h-4" aria-hidden="true" />
                {{ 'nav.signOut' | transloco }}
              </button>
            </div>
          </div>
        }
      </div>
    } @else {
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="nav-icon-btn focus-ring"
          (click)="theme.toggle()"
          [attr.aria-label]="
            (theme.isDark() ? 'nav.switchToLight' : 'nav.switchToDark') | transloco
          "
        >
          <lucide-icon
            [img]="theme.isDark() ? icons.Sun : icons.Moon"
            class="w-[18px] h-[18px]"
            aria-hidden="true"
          />
        </button>
        <a routerLink="/login" class="btn btn-primary btn-sm h-10 rounded-full px-4">
          {{ 'nav.signIn' | transloco }}
        </a>
      </div>
    }
  `,
})
export class AccountMenuComponent {
  /** Avatar only (no username text) — for the narrower workspace topbar. */
  @Input() compact = false;

  readonly theme = inject(ThemeService);
  private auth = inject(AuthService);
  private signOutService = inject(SignOutService);

  readonly user = toSignal(this.auth.currentUser$, { initialValue: this.auth.currentUser });
  readonly links = computed(() => {
    const u = this.user();
    return u ? accountLinks(u) : [];
  });
  readonly initial = computed(() => (this.user()?.username.charAt(0) ?? '?').toUpperCase());

  readonly open = signal(false);
  readonly panelId = `account-panel-${++nextId}`;
  readonly icons = { ChevronDown, LogOut, Moon, Sun };

  @ViewChild('trigger') private trigger?: ElementRef<HTMLButtonElement>;
  @ViewChild('panel') private panel?: ElementRef<HTMLElement>;

  @HostListener('document:click')
  onDocumentClick(): void {
    this.open.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.open()) this.close(true);
  }

  toggle(event: MouseEvent): void {
    event.stopPropagation();
    this.open.set(!this.open());
  }

  openFromKeyboard(event: Event): void {
    event.preventDefault();
    this.open.set(true);
    setTimeout(() => this.items()[0]?.focus());
  }

  close(returnFocus: boolean): void {
    this.open.set(false);
    if (returnFocus) this.trigger?.nativeElement.focus();
  }

  /** Arrow keys, Home and End move between the menu entries. */
  onPanelKey(event: KeyboardEvent): void {
    const items = this.items();
    const index = items.indexOf(document.activeElement as HTMLElement);
    let next: number | null = null;
    if (event.key === 'ArrowDown') next = (index + 1) % items.length;
    else if (event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    if (next === null) return;
    event.preventDefault();
    items[next]?.focus();
  }

  async signOut(): Promise<void> {
    this.open.set(false);
    await this.signOutService.confirmAndSignOut();
  }

  private items(): HTMLElement[] {
    const panel = this.panel?.nativeElement;
    return panel ? Array.from(panel.querySelectorAll<HTMLElement>('.account-item')) : [];
  }
}
