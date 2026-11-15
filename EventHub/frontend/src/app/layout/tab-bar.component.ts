import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { IsActiveMatchOptions, RouterModule } from '@angular/router';
import { LucideAngularModule, Heart, Search, Ticket, User as UserIcon } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { AuthService } from '../services/auth.service';
import { NavLink } from './account-links';

const EXACT: IsActiveMatchOptions = {
  paths: 'exact',
  queryParams: 'ignored',
  fragment: 'ignored',
  matrixParams: 'ignored',
};
const SUBSET: IsActiveMatchOptions = { ...EXACT, paths: 'subset' };

/** Mobile (<768px) bottom tab bar of the consumer layout. */
@Component({
  selector: 'app-tab-bar',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe],
  template: `
    <nav class="tab-bar md:hidden" [attr.aria-label]="'nav.mainNavigation' | transloco">
      @for (tab of tabs(); track tab.labelKey) {
        <a
          [routerLink]="tab.route"
          routerLinkActive="tab-bar-item-active"
          [routerLinkActiveOptions]="tab.exact ? exact : subset"
          ariaCurrentWhenActive="page"
          class="tab-bar-item focus-ring"
        >
          <lucide-icon [img]="tab.icon" class="w-5 h-5" aria-hidden="true" />
          <span>{{ tab.labelKey | transloco }}</span>
        </a>
      }
    </nav>
  `,
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class TabBarComponent {
  private auth = inject(AuthService);
  private readonly user = toSignal(this.auth.currentUser$, { initialValue: this.auth.currentUser });

  readonly exact = EXACT;
  readonly subset = SUBSET;

  /** Guests are sent to sign in by the guards of the signed-in tabs. */
  readonly tabs = computed<NavLink[]>(() => [
    { labelKey: 'nav.discover', icon: Search, route: '/', exact: true },
    { labelKey: 'nav.tabTickets', icon: Ticket, route: '/my-registrations' },
    { labelKey: 'nav.favorites', icon: Heart, route: '/favorites' },
    { labelKey: 'nav.tabProfile', icon: UserIcon, route: this.user() ? '/profile' : '/login' },
  ]);
}
