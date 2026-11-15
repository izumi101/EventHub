import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { distinctUntilChanged, map } from 'rxjs';
import { AuthService } from './auth.service';
import { EventService } from './event.service';
import { ToastService } from './toast.service';
import { LanguageService } from '../i18n/language.service';

/**
 * Which events the signed-in user favourited, for the hearts on cards.
 * Loaded once per session from `/favorites/ids/`; toggles are optimistic and
 * roll back when the API refuses. Guests are sent to sign in instead.
 */
@Injectable({ providedIn: 'root' })
export class FavoritesStore {
  private auth = inject(AuthService);
  private events = inject(EventService);
  private toast = inject(ToastService);
  private router = inject(Router);
  private i18n = inject(LanguageService);

  private readonly ids = signal<ReadonlySet<number>>(new Set());
  private readonly pending = new Set<number>();

  constructor() {
    this.auth.currentUser$
      .pipe(
        map((u) => u?.id ?? null),
        distinctUntilChanged(),
      )
      .subscribe((userId) => {
        this.ids.set(new Set());
        if (userId !== null) this.load();
      });
  }

  has(eventId: number): boolean {
    return this.ids().has(eventId);
  }

  toggle(eventId: number): void {
    if (!this.auth.isLoggedIn) {
      void this.router.navigate(['/login'], { queryParams: { returnUrl: this.router.url } });
      return;
    }
    if (this.pending.has(eventId)) return;
    const was = this.has(eventId);
    this.set(eventId, !was);
    this.pending.add(eventId);
    this.events.toggleFavorite(eventId).subscribe({
      next: (res) => {
        this.pending.delete(eventId);
        this.set(eventId, res.favorited);
      },
      error: () => {
        this.pending.delete(eventId);
        this.set(eventId, was);
        this.toast.error(this.i18n.t('event.favoriteError'));
      },
    });
  }

  private load(): void {
    this.events.getFavoriteIds().subscribe({
      next: (ids) => {
        this.ids.set(new Set(ids));
      },
      error: () => {
        // Hearts just show as empty; toggling still works.
      },
    });
  }

  private set(eventId: number, on: boolean): void {
    const next = new Set(this.ids());
    if (on) next.add(eventId);
    else next.delete(eventId);
    this.ids.set(next);
  }
}
