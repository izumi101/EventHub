import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import {
  Armchair,
  BellRing,
  Heart,
  LayoutDashboard,
  Search,
  Shield,
  ShieldCheck,
  Ticket,
  User as UserIcon,
  type LucideIconData,
} from 'lucide-angular';
import { AuthService } from '../services/auth.service';
import { ModalService } from '../services/modal.service';
import { LanguageService } from '../i18n/language.service';
import type { User } from '../models/models';
import { isAdmin, isOrganizer } from '../utils/roles';

export interface NavLink {
  /** Translation key of the label. */
  labelKey: string;
  icon: LucideIconData;
  route: string;
  /** Active only on an exact path match (Discover). */
  exact?: boolean;
}

/** The consumer site's primary destinations (top nav, mobile menu). */
export function primaryLinks(user: User | null): NavLink[] {
  const links: NavLink[] = [{ labelKey: 'nav.discover', icon: Search, route: '/', exact: true }];
  if (user) {
    links.push(
      { labelKey: 'nav.myTickets', icon: Ticket, route: '/my-registrations' },
      { labelKey: 'nav.favorites', icon: Heart, route: '/favorites' },
    );
  }
  return links;
}

/** Everything behind the avatar: account pages, then the role areas. */
export function accountLinks(user: User): NavLink[] {
  const links: NavLink[] = [
    { labelKey: 'nav.profile', icon: UserIcon, route: '/profile' },
    { labelKey: 'nav.myBookings', icon: Armchair, route: '/my-bookings' },
    { labelKey: 'nav.security', icon: ShieldCheck, route: '/profile/security' },
    { labelKey: 'nav.notificationSettings', icon: BellRing, route: '/profile/notifications' },
  ];
  if (isOrganizer(user)) {
    links.push({
      labelKey: 'nav.organizerArea',
      icon: LayoutDashboard,
      route: '/organizer/dashboard',
    });
  }
  if (isAdmin(user)) {
    links.push({ labelKey: 'nav.adminArea', icon: Shield, route: '/admin/moderation' });
  }
  return links;
}

/** Sign-out with the confirmation dialog, shared by the avatar menu and the mobile menu. */
@Injectable({ providedIn: 'root' })
export class SignOutService {
  private auth = inject(AuthService);
  private modal = inject(ModalService);
  private router = inject(Router);
  private i18n = inject(LanguageService);

  async confirmAndSignOut(): Promise<void> {
    const confirmed = await this.modal.open({
      title: this.i18n.t('nav.signOutTitle'),
      message: this.i18n.t('nav.signOutMessage'),
      confirmText: this.i18n.t('nav.signOut'),
      cancelText: this.i18n.t('common.cancel'),
      isDestructive: true,
    });
    if (confirmed) {
      this.auth.logout();
      void this.router.navigate(['/login']);
    }
  }
}
