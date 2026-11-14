import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import type { components } from '../api/openapi';

// API shapes come from the backend's OpenAPI schema (see models/models.ts).
export type NotificationPreferences = components['schemas']['NotificationPreferences'];
export type NotificationTypePreference = components['schemas']['NotificationTypePreference'];

/** Email on/off per notification type (in-app notifications are always on). */
@Injectable({ providedIn: 'root' })
export class NotificationPreferencesService {
  private http = inject(HttpClient);

  private url = `${environment.apiUrl}/auth/profile/notifications/`;

  get(): Observable<NotificationPreferences> {
    return this.http.get<NotificationPreferences>(this.url);
  }

  /** Only the types sent are changed; the others keep their setting. */
  setEmail(changes: Record<string, boolean>): Observable<NotificationPreferences> {
    return this.http.patch<NotificationPreferences>(this.url, { email: changes });
  }
}
