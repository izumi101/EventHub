import { DestroyRef, Injectable, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { distinctUntilChanged, map } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { NotificationPreferencesService } from '../services/notification-preferences.service';
import { LanguageService } from './language.service';
import { Lang } from './languages';

/**
 * Keeps the server-side notification language (emails, in-app notifications)
 * in step with the UI language of a signed-in user:
 *
 * - when the user switches the language, it is saved;
 * - once per sign-in (or page load with a session), the stored language is
 *   compared with the UI one and saved if it differs.
 *
 * Fire-and-forget: it never blocks the UI and failures are ignored (the next
 * switch or sign-in tries again).
 */
@Injectable({ providedIn: 'root' })
export class LanguageSyncService {
  private readonly auth = inject(AuthService);
  private readonly language = inject(LanguageService);
  private readonly preferences = inject(NotificationPreferencesService);
  private readonly destroyRef = inject(DestroyRef);
  private started = false;

  start(): void {
    if (this.started) return;
    this.started = true;

    this.language.switched$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((lang) => {
      if (this.auth.isLoggedIn) this.save(lang);
    });

    this.auth.currentUser$
      .pipe(
        map((user) => user?.id ?? null),
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((userId) => {
        if (userId !== null && this.auth.isLoggedIn) this.reconcile();
      });
  }

  private reconcile(): void {
    this.preferences.get().subscribe({
      next: (prefs) => {
        const current = this.language.lang();
        if (prefs.language !== current) this.save(current);
      },
      error: () => undefined,
    });
  }

  private save(lang: Lang): void {
    this.preferences.setLanguage(lang).subscribe({ error: () => undefined });
  }
}
