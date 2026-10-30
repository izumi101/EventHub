import { Injectable, Signal, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable, catchError, distinctUntilChanged, map, of, switchMap } from 'rxjs';
import type { components } from '../api/openapi';
import { AuthService } from './auth.service';
import { environment } from '../../environments/environment';

/** Client-visible flags, generated from the backend registry via the OpenAPI schema. */
export type FeatureFlags = components['schemas']['FeatureFlags'];
export type FeatureFlagName = keyof FeatureFlags;
type FeatureFlagsResponse = components['schemas']['FeatureFlagsResponse'];

/**
 * Feature flags for the signed-in user, evaluated by the backend
 * (GET /feature-flags/) — the browser never talks to Unleash and holds no
 * Unleash token. Loaded once per signed-in user (after login, or at start-up
 * with a stored session) and cleared on logout.
 *
 * Every flag is off until the backend says otherwise, and stays off when the
 * request fails: new features must not appear because something broke.
 */
@Injectable({ providedIn: 'root' })
export class FeatureFlagService {
  private http = inject(HttpClient);
  private auth = inject(AuthService);
  private readonly url = `${environment.apiUrl}/feature-flags/`;

  private readonly state = signal<Partial<FeatureFlags>>({});
  private readonly loadedState = signal(false);

  /** The flags as the backend answered them (missing = off). */
  readonly flags = this.state.asReadonly();
  /** True once the backend answered for the current user. */
  readonly loaded = this.loadedState.asReadonly();

  constructor() {
    this.auth.currentUser$
      .pipe(
        map((user) => user?.id ?? null),
        distinctUntilChanged(),
        switchMap((userId) => (userId === null ? of(null) : this.fetch())),
        takeUntilDestroyed(),
      )
      .subscribe((flags) => {
        this.state.set(flags ?? {});
        this.loadedState.set(flags !== null);
      });
  }

  /** Whether `name` is on for the current user. Reactive inside templates,
   *  computed() and effect(). */
  isEnabled(name: FeatureFlagName): boolean {
    return this.state()[name] === true;
  }

  /** A signal for one flag, e.g. `readonly offlineScanner = flags.flag('checkin.offline_scanner')`. */
  flag(name: FeatureFlagName): Signal<boolean> {
    return computed(() => this.isEnabled(name));
  }

  /** Re-read the flags (e.g. after a role change). Failures keep the current values. */
  refresh(): void {
    if (!this.auth.currentUser) return;
    this.fetch().subscribe((flags) => {
      if (flags !== null) {
        this.state.set(flags);
        this.loadedState.set(true);
      }
    });
  }

  private fetch(): Observable<Partial<FeatureFlags> | null> {
    return this.http.get<FeatureFlagsResponse>(this.url).pipe(
      // Spread rather than `res.flags ?? {}`: the schema says `flags` is
      // always present, but a malformed answer must still not break lookups.
      map((res) => ({ ...res.flags })),
      catchError(() => of(null)),
    );
  }
}
